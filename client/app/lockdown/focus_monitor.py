"""Focus Monitor subsystem — yanks focus back if user switches windows.

Polls GetForegroundWindow every 500ms. On mismatch with the exam HWND,
posts FOCUS_LOST with the foreign window's title, then calls
SetForegroundWindow to reclaim focus.

Uses the AllowSetForegroundWindow + AttachThreadInput workaround for
modern Windows restrictions on SetForegroundWindow. This is necessary
because Windows only allows a process to steal focus if it is the
foreground process — the attach-input trick satisfies this constraint.

Cross-version: GetForegroundWindow, SetForegroundWindow, GetWindowTextW
are stable across Windows 10 and 11.
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


class FocusMonitorSubsystem:
    """Monitors and enforces focus on the exam window."""

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
        self._hwnd: int = 0

        # Throttle
        self._last_incident_time: float = 0.0
        self._throttle_seconds = 2.0

    @property
    def name(self) -> str:
        return "focus_monitor"

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
        self._started = True

        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="focus_monitor_thread",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _monitor_loop(self) -> None:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        while not self._shutdown_event.is_set() and self._started:
            try:
                fg = user32.GetForegroundWindow()
                if fg and fg != self._hwnd:
                    # Get the title of the foreign window
                    title_buf = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(fg, title_buf, 256)
                    title = title_buf.value or "<unknown>"

                    # Report
                    self._report_focus_lost(title)

                    # Yank focus back using AttachThreadInput workaround
                    self._force_foreground(user32, kernel32, fg)

            except Exception as e:
                logger.debug(f"Focus monitor error: {e}")

            self._shutdown_event.wait(timeout=0.5)

    def _force_foreground(
        self, user32: Any, kernel32: Any, foreign_hwnd: int
    ) -> None:
        """Force our window to foreground using AttachThreadInput trick.

        Modern Windows prevents SetForegroundWindow unless the calling
        thread is attached to the foreground window's thread input queue.
        We temporarily attach, set foreground, then detach.
        """
        try:
            our_tid = kernel32.GetCurrentThreadId()
            fg_tid = user32.GetWindowThreadProcessId(foreign_hwnd, None)

            if our_tid != fg_tid:
                user32.AttachThreadInput(our_tid, fg_tid, True)
                user32.SetForegroundWindow(self._hwnd)
                user32.AttachThreadInput(our_tid, fg_tid, False)
            else:
                user32.SetForegroundWindow(self._hwnd)
        except Exception as e:
            logger.debug(f"Force foreground failed: {e}")

    def _report_focus_lost(self, window_title: str) -> None:
        now = time.time()
        if now - self._last_incident_time < self._throttle_seconds:
            return
        self._last_incident_time = now
        self._manager.report(
            "FOCUS_LOST",
            "warning",
            f"Focus lost to: {window_title}",
            subsystem_name=self.name,
            foreign_window=window_title,
        )


__all__ = ["FocusMonitorSubsystem"]
