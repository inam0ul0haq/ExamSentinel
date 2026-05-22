"""Incident Pipeline — reliable offline-queued incident shipping.

Owns an in-memory deque of queued incidents and a background flusher
thread that attempts a bulk POST to /sessions/<id>/incidents every 5
seconds with exponential backoff on transport failure.

Provides flush_now() for synchronous flush at submit/abort time.
Handles 409 (session in terminal state) by discarding the batch.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, Optional

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_S = 5
_BACKOFF_BASE_S = 1.0
_BACKOFF_MAX_S = 30.0


class IncidentPipeline:
    """Reliable incident shipping with offline queuing and bulk flush."""

    def __init__(self, api: Any, session_id: int) -> None:
        self._api = api
        self._session_id = session_id
        self._queue: Deque[Dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._shutdown = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._backoff = _BACKOFF_BASE_S

    # -- Lifecycle ----------------------------------------------------------

    def start(self) -> None:
        """Start the background flusher thread."""
        self._thread = threading.Thread(
            target=self._flusher_loop,
            name="incident_pipeline_flusher",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the background flusher. Does NOT flush — call flush_now() first."""
        self._shutdown.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    # -- Public API ---------------------------------------------------------

    def post(self, type: str, severity: str,
             description: str = "", **forensics: Any) -> None:
        """Post an incident — try direct first, queue on transport failure."""
        body: Dict[str, Any] = {
            "type": type,
            "severity": severity,
            "description": description,
        }
        body.update(forensics)

        ok, _payload, err = self._api.post(
            f"/sessions/{self._session_id}/incident",
            body=body,
        )
        if not ok and err and getattr(err, "code", "") in ("TRANSPORT", "TIMEOUT"):
            with self._lock:
                self._queue.append(body)
            logger.debug(f"Incident queued (transport error): {type}")

    def flush_now(self) -> bool:
        """Synchronous flush of the entire queue. Returns True if empty after."""
        with self._lock:
            if not self._queue:
                return True
            items = list(self._queue)

        ok, _payload, err = self._api.post(
            f"/sessions/{self._session_id}/incidents",
            body={"incidents": items},
        )

        if ok:
            with self._lock:
                # Remove only the items we flushed
                for _ in range(min(len(items), len(self._queue))):
                    self._queue.popleft()
            self._backoff = _BACKOFF_BASE_S
            return len(self._queue) == 0

        # Handle 409 — session in terminal state
        if err and getattr(err, "status", 0) == 409:
            logger.warning(
                "Bulk incident POST returned 409 (session terminal). "
                "Discarding batch."
            )
            with self._lock:
                for _ in range(min(len(items), len(self._queue))):
                    self._queue.popleft()
            return True

        return False

    @property
    def queue_size(self) -> int:
        with self._lock:
            return len(self._queue)

    # -- Background flusher -------------------------------------------------

    def _flusher_loop(self) -> None:
        """Background loop: flush every 5 seconds with exponential backoff."""
        while not self._shutdown.wait(_FLUSH_INTERVAL_S):
            if self._queue:
                success = self.flush_now()
                if success:
                    self._backoff = _BACKOFF_BASE_S
                else:
                    time.sleep(self._backoff)
                    self._backoff = min(self._backoff * 2, _BACKOFF_MAX_S)


__all__ = ["IncidentPipeline"]
