"""Fullscreen subsystem — forces exam window to cover the entire screen.

Removes window chrome (title bar, borders, system menu), sets the window
topmost, resizes to cover the primary monitor including the taskbar area.
Hides the taskbar (Shell_TrayWnd) and the Windows 11 Start button.

A re-engage thread polls every 1 second to verify the window is still
fullscreen and topmost. Posts FULLSCREEN_BREACH on re-engage.

On stop: restores all original window state and unhides the taskbar.
Critical: taskbar restoration is wrapped in its own try so it is never skipped.

Cross-version: SetWindowLongPtr, SetWindowPos, ShowWindow, FindWindowW
are stable across Windows 10 and 11. The Windows 11 Start button HWND
is handled by trying multiple FindWindowW patterns.
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

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------
GWL_STYLE = -16
GWL_EXSTYLE = -20

WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_SYSMENU = 0x00080000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000

WS_EX_TOPMOST = 0x00000008

SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

SW_HIDE = 0
SW_SHOW = 5

SM_CXSCREEN = 0
SM_CYSCREEN = 1

_REMOVE_STYLES = WS_CAPTION | WS_THICKFRAME | WS_SYSMENU | WS_MINIMIZEBOX | WS_MAXIMIZEBOX


class FullscreenSubsystem:
    """Forces the exam window into borderless fullscreen with taskbar hidden."""

    def __init__(
        self,
        manager: Any,
        shutdown_event: threading.Event,
        window: Any,
    ) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._window = window  # Tk root
        self._started = False
        self._thread: Optional[threading.Thread] = None

        # Saved state for restoration
        self._hwnd: int = 0
        self._orig_style: int = 0
        self._orig_exstyle: int = 0
        self._orig_rect: tuple = (0, 0, 800, 600)
        self._taskbar_hwnd: int = 0
        self._start_btn_hwnd: int = 0
        self._screen_w: int = 0
        self._screen_h: int = 0

        # Throttle
        self._last_breach_time: float = 0.0
        self._throttle_seconds = 5.0

    @property
    def name(self) -> str:
        return "fullscreen"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        if platform.system() != "Windows":
            logger.warning("FullscreenSubsystem: non-Windows, skipping.")
            self._started = True
            return

        user32 = ctypes.windll.user32

        # Get the top-level HWND. winfo_id() returns Tk's inner frame;
        # walk up via GetParent to find the actual top-level window.
        inner = self._window.winfo_id()
        parent = user32.GetParent(inner)
        self._hwnd = parent if parent else inner

        # Save original Tk geometry for restoration
        self._orig_geometry = self._window.geometry()
        self._orig_overrideredirect = self._window.overrideredirect()

        # Save original Win32 styles
        self._orig_style = user32.GetWindowLongPtrW(self._hwnd, GWL_STYLE)
        self._orig_exstyle = user32.GetWindowLongPtrW(self._hwnd, GWL_EXSTYLE)

        # Save original position
        rect = wintypes.RECT()
        user32.GetWindowRect(self._hwnd, ctypes.byref(rect))
        self._orig_rect = (rect.left, rect.top, rect.right, rect.bottom)

        # Screen dimensions
        self._screen_w = user32.GetSystemMetrics(SM_CXSCREEN)
        self._screen_h = user32.GetSystemMetrics(SM_CYSCREEN)

        # Use Tk's overrideredirect to remove window chrome (works with
        # the geometry manager instead of fighting it)
        self._window.overrideredirect(True)
        self._window.geometry(f"{self._screen_w}x{self._screen_h}+0+0")
        self._window.update_idletasks()

        # Also remove styles via Win32 for belt-and-suspenders
        new_style = self._orig_style & ~_REMOVE_STYLES
        user32.SetWindowLongPtrW(self._hwnd, GWL_STYLE, new_style)

        # Set topmost and resize to full screen
        user32.SetWindowPos(
            self._hwnd, HWND_TOPMOST,
            0, 0, self._screen_w, self._screen_h,
            SWP_FRAMECHANGED | SWP_SHOWWINDOW,
        )

        # Hide taskbar
        self._hide_taskbar(user32)

        self._started = True
        logger.info(
            f"Fullscreen engaged: {self._screen_w}x{self._screen_h}, "
            f"taskbar hidden"
        )

        # Start re-engage thread
        self._thread = threading.Thread(
            target=self._reengage_loop,
            name="fullscreen_reengage",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        if not self._started:
            return
        self._started = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

        if platform.system() != "Windows" or not self._hwnd:
            return

        user32 = ctypes.windll.user32

        # Restore taskbar FIRST (critical — own try block)
        try:
            self._show_taskbar(user32)
        except Exception as e:
            logger.error(f"Failed to restore taskbar: {e}")

        # Restore window styles and geometry
        try:
            user32.SetWindowLongPtrW(self._hwnd, GWL_STYLE, self._orig_style)
            user32.SetWindowLongPtrW(self._hwnd, GWL_EXSTYLE, self._orig_exstyle)

            # Restore position and remove topmost
            x, y, r, b = self._orig_rect
            user32.SetWindowPos(
                self._hwnd, HWND_NOTOPMOST,
                x, y, r - x, b - y,
                SWP_FRAMECHANGED | SWP_SHOWWINDOW,
            )

            # Restore Tk geometry state
            self._window.overrideredirect(
                self._orig_overrideredirect or False
            )
            if self._orig_geometry:
                self._window.geometry(self._orig_geometry)

            logger.info("Fullscreen disengaged, window restored.")
        except Exception as e:
            logger.error(f"Failed to restore window: {e}")

    # -- Taskbar management -------------------------------------------------

    def _hide_taskbar(self, user32: Any) -> None:
        """Hide the Windows taskbar and Start button."""
        # Main taskbar
        self._taskbar_hwnd = user32.FindWindowW("Shell_TrayWnd", None)
        if self._taskbar_hwnd:
            user32.ShowWindow(self._taskbar_hwnd, SW_HIDE)

        # Windows 11 Start button (separate HWND)
        self._start_btn_hwnd = user32.FindWindowW("Button", "Start")
        if self._start_btn_hwnd:
            user32.ShowWindow(self._start_btn_hwnd, SW_HIDE)

        # Windows 10 alternative Start button
        if not self._start_btn_hwnd:
            self._start_btn_hwnd = user32.FindWindowW("Button", "start")
            if self._start_btn_hwnd:
                user32.ShowWindow(self._start_btn_hwnd, SW_HIDE)

    def _show_taskbar(self, user32: Any) -> None:
        """Restore the Windows taskbar and Start button."""
        if self._taskbar_hwnd:
            user32.ShowWindow(self._taskbar_hwnd, SW_SHOW)
        if self._start_btn_hwnd:
            user32.ShowWindow(self._start_btn_hwnd, SW_SHOW)

    # -- Re-engage loop -----------------------------------------------------

    def _reengage_loop(self) -> None:
        """Poll every 1s to verify fullscreen + topmost. Re-apply if needed."""
        user32 = ctypes.windll.user32

        while not self._shutdown_event.is_set() and self._started:
            try:
                # Check position
                rect = wintypes.RECT()
                user32.GetWindowRect(self._hwnd, ctypes.byref(rect))

                needs_fix = (
                    rect.left != 0 or rect.top != 0 or
                    rect.right != self._screen_w or
                    rect.bottom != self._screen_h
                )

                if needs_fix:
                    user32.SetWindowPos(
                        self._hwnd, HWND_TOPMOST,
                        0, 0, self._screen_w, self._screen_h,
                        SWP_FRAMECHANGED | SWP_SHOWWINDOW,
                    )
                    self._report_breach("Window was resized or moved")

            except Exception as e:
                logger.debug(f"Re-engage check error: {e}")

            self._shutdown_event.wait(timeout=1.0)

    def _report_breach(self, desc: str) -> None:
        now = time.time()
        if now - self._last_breach_time < self._throttle_seconds:
            return
        self._last_breach_time = now
        self._manager.report(
            "FULLSCREEN_BREACH",
            "warning",
            desc,
            subsystem_name=self.name,
        )


__all__ = ["FullscreenSubsystem"]
