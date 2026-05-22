"""Mouse Boundary subsystem — confines cursor to the exam window.

Calls ClipCursor with the exam window's screen rectangle on start.
A background thread re-applies every 500ms (Windows can release the
clip on certain UI events). Posts MOUSE_ESCAPE if the cursor is detected
outside the rect.

On stop: ClipCursor(NULL) to release.

Cross-version: ClipCursor is stable across Windows 10 and 11.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import platform
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class MouseBoundarySubsystem:
    """Confines the mouse cursor to the exam window region."""

    def __init__(
        self,
        manager: Any,
        shutdown_event: threading.Event,
        window: Any,
    ) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._window = window
        self._started = False
        self._thread: Optional[threading.Thread] = None
        self._clip_rect: Optional[wintypes.RECT] = None
        self._hwnd: int = 0

        # Throttle
        self._last_escape_time: float = 0.0
        self._throttle_seconds = 2.0

    @property
    def name(self) -> str:
        return "mouse_boundary"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        if platform.system() != "Windows":
            self._started = True
            return

        user32 = ctypes.windll.user32
        inner = self._window.winfo_id()
        parent = user32.GetParent(inner)
        self._hwnd = parent if parent else inner

        # Get the window rect
        self._clip_rect = wintypes.RECT()
        user32.GetWindowRect(self._hwnd, ctypes.byref(self._clip_rect))

        # Apply clip
        user32.ClipCursor(ctypes.byref(self._clip_rect))
        self._started = True

        logger.info(
            f"Mouse boundary set: ({self._clip_rect.left}, {self._clip_rect.top}) - "
            f"({self._clip_rect.right}, {self._clip_rect.bottom})"
        )

        self._thread = threading.Thread(
            target=self._enforce_loop,
            name="mouse_boundary_thread",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        if platform.system() != "Windows":
            return

        # Release cursor clip
        try:
            ctypes.windll.user32.ClipCursor(None)
            logger.info("Mouse boundary released.")
        except Exception as e:
            logger.error(f"Failed to release ClipCursor: {e}")

    def _enforce_loop(self) -> None:
        user32 = ctypes.windll.user32

        while not self._shutdown_event.is_set() and self._started:
            try:
                if self._clip_rect:
                    # Re-apply clip (Windows can release it)
                    user32.ClipCursor(ctypes.byref(self._clip_rect))

                    # Check if cursor is outside bounds
                    pt = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(pt))

                    if (pt.x < self._clip_rect.left or
                        pt.x > self._clip_rect.right or
                        pt.y < self._clip_rect.top or
                        pt.y > self._clip_rect.bottom):
                        self._report_escape(pt.x, pt.y)

            except Exception as e:
                logger.debug(f"Mouse boundary check error: {e}")

            self._shutdown_event.wait(timeout=0.5)

    def _report_escape(self, x: int, y: int) -> None:
        now = time.time()
        if now - self._last_escape_time < self._throttle_seconds:
            return
        self._last_escape_time = now
        self._manager.report(
            "MOUSE_ESCAPE",
            "warning",
            f"Cursor detected outside exam boundary at ({x}, {y})",
            subsystem_name=self.name,
            cursor_x=x,
            cursor_y=y,
        )


__all__ = ["MouseBoundarySubsystem"]
