"""Clipboard Scrub subsystem — clears clipboard every 500ms during exams.

Uses win32clipboard (pywin32) to open, read formats, empty, and close the
clipboard. Posts CLIPBOARD_SCRUB incident (warning) the first time data is
found, then suppresses further incidents for 10 seconds.

Resilience: clipboard access can be temporarily denied by another app
holding it open — catch and skip silently, retry next tick.

Cross-version: pywin32 works identically on Windows 10 and 11.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Standard clipboard format names
_CF_NAMES = {
    1: "CF_TEXT",
    2: "CF_BITMAP",
    3: "CF_METAFILEPICT",
    4: "CF_SYLK",
    5: "CF_DIF",
    6: "CF_TIFF",
    7: "CF_OEMTEXT",
    8: "CF_DIB",
    13: "CF_UNICODETEXT",
    14: "CF_ENHMETAFILE",
    15: "CF_HDROP",
    16: "CF_LOCALE",
    17: "CF_DIBV5",
}


class ClipboardScrubSubsystem:
    """Clears the system clipboard on a 500ms polling loop."""

    def __init__(self, manager: Any, shutdown_event: threading.Event) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._started = False
        self._thread: Optional[threading.Thread] = None
        # Throttle: suppress incidents for 10s after posting one
        self._last_incident_time: float = 0.0
        self._incident_suppress_seconds = 10.0

    @property
    def name(self) -> str:
        return "clipboard_scrub"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True
        self._thread = threading.Thread(
            target=self._scrub_loop, name="clipboard_scrub_thread", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    # -- scrub loop ---------------------------------------------------------

    def _scrub_loop(self) -> None:
        try:
            import win32clipboard
        except ImportError:
            logger.error("win32clipboard not available — clipboard scrub disabled")
            self._started = False
            return

        while not self._shutdown_event.is_set():
            try:
                win32clipboard.OpenClipboard()
                try:
                    # Enumerate formats present
                    formats = self._enum_formats(win32clipboard)

                    if formats:
                        # Data present — clear it
                        win32clipboard.EmptyClipboard()

                        # Post incident (throttled)
                        now = time.time()
                        if now - self._last_incident_time >= self._incident_suppress_seconds:
                            self._last_incident_time = now
                            format_names = [
                                _CF_NAMES.get(f, f"CF_{f}") for f in formats
                            ]
                            self._manager.report(
                                "CLIPBOARD_SCRUB",
                                "warning",
                                f"Clipboard cleared. Formats present: {', '.join(format_names)}",
                                subsystem_name=self.name,
                                clipboard_formats=format_names,
                            )
                finally:
                    win32clipboard.CloseClipboard()

            except Exception:
                # Clipboard held by another app — skip silently
                pass

            # Poll every 500ms
            self._shutdown_event.wait(timeout=0.5)

    def _enum_formats(self, win32clipboard: Any) -> List[int]:
        """Enumerate all clipboard formats currently present."""
        formats: List[int] = []
        try:
            fmt = win32clipboard.EnumClipboardFormats(0)
            while fmt:
                formats.append(fmt)
                fmt = win32clipboard.EnumClipboardFormats(fmt)
        except Exception:
            pass
        return formats


__all__ = ["ClipboardScrubSubsystem"]
