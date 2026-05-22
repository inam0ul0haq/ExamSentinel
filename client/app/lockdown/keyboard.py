"""Keyboard Lockdown subsystem — blocks dangerous key combos during exams.

Installs a Windows low-level keyboard hook (WH_KEYBOARD_LL) via
SetWindowsHookExW. The hook runs on a dedicated thread with its own
Windows message loop so the main UI thread stays responsive.

Blocked combinations:
    - Alt+Tab, Alt+Esc, Alt+F4
    - Ctrl+Esc (Start menu), Ctrl+Shift+Esc (Task Manager)
    - Win key (left/right), with or without modifiers
    - Print Screen (vk 0x2C)
    - Ctrl+Win+any (generic Win combos)

Allowed:
    - All typing keys, arrows, home/end, backspace, enter, plain Tab

Note: This hook requires Administrator privileges to be fully reliable on
locked-down corporate Windows installs. PyInstaller manifest (Part 28) will
request elevation. If the hook cannot be installed, the subsystem records an
UNAVAILABLE incident and gracefully degrades (is_started stays False).

Cross-version: WH_KEYBOARD_LL is identical on Windows 10 and 11.
Only documented user32 functions are used.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import logging
import platform
import threading
import time
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

VK_TAB = 0x09
VK_ESCAPE = 0x1B
VK_F4 = 0x73
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_SNAPSHOT = 0x2C  # Print Screen
VK_LSHIFT = 0xA0
VK_RSHIFT = 0xA1
VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LMENU = 0xA4  # Left Alt
VK_RMENU = 0xA5  # Right Alt

# For GetAsyncKeyState / modifier tracking
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

# Hook callback type
HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,       # LRESULT
    ctypes.c_int,        # nCode
    wintypes.WPARAM,     # wParam
    wintypes.LPARAM,     # lParam
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


# ---------------------------------------------------------------------------
# KeyboardLockdown
# ---------------------------------------------------------------------------

class KeyboardLockdown:
    """Low-level keyboard hook subsystem implementing the LockdownManager protocol."""

    def __init__(
        self,
        manager: Any,
        shutdown_event: threading.Event,
    ) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._started = False
        self._hook_handle: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None

        # Modifier state tracking
        self._alt_down = False
        self._ctrl_down = False
        self._shift_down = False
        self._win_down = False

        # Throttle: {description: last_report_time}
        self._throttle_map: dict[str, float] = {}
        self._throttle_seconds = 2.0

        # Keep reference to prevent GC
        self._hook_proc: Optional[HOOKPROC] = None

    # -- Protocol properties ------------------------------------------------

    @property
    def name(self) -> str:
        return "keyboard_hook"

    @property
    def is_started(self) -> bool:
        return self._started

    # -- Start / Stop -------------------------------------------------------

    def start(self) -> None:
        """Install the low-level keyboard hook on a dedicated thread."""
        if platform.system() != "Windows":
            logger.warning("KeyboardLockdown: non-Windows, skipping.")
            return

        self._thread = threading.Thread(
            target=self._hook_thread_main,
            name="keyboard_hook_thread",
            daemon=True,
        )
        self._thread.start()

        # Wait briefly for the hook to install
        deadline = time.time() + 3.0
        while not self._started and time.time() < deadline:
            time.sleep(0.05)

        if not self._started:
            # Hook installation failed — subsystem reports unavailable
            self._manager.report(
                "KEYBOARD_HOOK_UNAVAILABLE",
                "warning",
                "Failed to install low-level keyboard hook. "
                "Administrator privileges may be required.",
                subsystem_name=self.name,
            )

    def stop(self) -> None:
        """Remove the hook and join the message-loop thread."""
        if not self._started and self._thread is None:
            return

        # Signal the message loop to exit
        if self._thread_id is not None:
            try:
                user32 = ctypes.windll.user32
                user32.PostThreadMessageW(
                    wintypes.DWORD(self._thread_id), WM_QUIT, 0, 0
                )
            except Exception as e:
                logger.debug(f"PostThreadMessage failed: {e}")

        # Join the thread with timeout
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning(
                    "Keyboard hook thread did not exit within 2s timeout."
                )

        self._started = False
        self._thread = None
        self._thread_id = None

    # -- Hook thread --------------------------------------------------------

    def _hook_thread_main(self) -> None:
        """Dedicated thread: install hook, run message loop, unhook on exit."""
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Store thread ID for PostThreadMessage
            self._thread_id = kernel32.GetCurrentThreadId()

            # Create the hook callback (prevent GC by storing reference)
            self._hook_proc = HOOKPROC(self._hook_callback)

            # Install the hook
            self._hook_handle = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL,
                self._hook_proc,
                None,  # hMod — None for thread hook on LL hooks
                0,     # dwThreadId — 0 = all threads (required for LL)
            )

            if not self._hook_handle:
                error_code = kernel32.GetLastError()
                logger.error(
                    f"SetWindowsHookExW failed with error code {error_code}"
                )
                return

            self._started = True
            logger.info("Keyboard hook installed successfully.")

            # Message loop — required for LL hooks to receive callbacks
            msg = wintypes.MSG()
            while not self._shutdown_event.is_set():
                # Use PeekMessage with a short timeout to stay responsive
                result = user32.PeekMessageW(
                    ctypes.byref(msg), None, 0, 0, 1  # PM_REMOVE = 1
                )
                if result:
                    if msg.message == WM_QUIT:
                        break
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                else:
                    # No message — sleep briefly to avoid busy-wait
                    time.sleep(0.01)

        except Exception as e:
            logger.error(f"Keyboard hook thread error: {e}", exc_info=True)
        finally:
            # Unhook
            if self._hook_handle:
                try:
                    user32 = ctypes.windll.user32
                    user32.UnhookWindowsHookEx(self._hook_handle)
                    logger.info("Keyboard hook removed.")
                except Exception as e:
                    logger.error(f"UnhookWindowsHookEx failed: {e}")
                self._hook_handle = None

    # -- Hook callback ------------------------------------------------------

    def _hook_callback(
        self, nCode: int, wParam: int, lParam: int
    ) -> int:
        """Low-level keyboard hook callback.

        Returns 1 to block the keystroke, or calls CallNextHookEx to pass it.
        """
        user32 = ctypes.windll.user32

        if nCode < 0:
            return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

        # Parse the key event
        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kb.vkCode

        is_down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = wParam in (WM_KEYUP, WM_SYSKEYUP)

        # --- Update modifier state ---
        self._update_modifiers(vk, is_down, is_up)

        # --- Check if this key should be blocked ---
        block_reason = self._should_block(vk, is_down)

        if block_reason:
            self._report_blocked(block_reason)
            return 1  # Consume the keystroke

        return user32.CallNextHookEx(self._hook_handle, nCode, wParam, lParam)

    # -- Modifier tracking --------------------------------------------------

    def _update_modifiers(self, vk: int, is_down: bool, is_up: bool) -> None:
        """Track modifier key state."""
        if vk in (VK_LMENU, VK_RMENU):
            if is_down:
                self._alt_down = True
            elif is_up:
                self._alt_down = False
        elif vk in (VK_LCONTROL, VK_RCONTROL):
            if is_down:
                self._ctrl_down = True
            elif is_up:
                self._ctrl_down = False
        elif vk in (VK_LSHIFT, VK_RSHIFT):
            if is_down:
                self._shift_down = True
            elif is_up:
                self._shift_down = False
        elif vk in (VK_LWIN, VK_RWIN):
            if is_down:
                self._win_down = True
            elif is_up:
                self._win_down = False

    # -- Block decision -----------------------------------------------------

    def _should_block(self, vk: int, is_down: bool) -> Optional[str]:
        """Return a description string if the key should be blocked, else None.

        Only blocks on key-down events (not key-up) to avoid inconsistencies.
        """
        if not is_down:
            return None

        # --- Win key alone (left or right) ---
        if vk in (VK_LWIN, VK_RWIN):
            return "Win key"

        # --- Print Screen ---
        if vk == VK_SNAPSHOT:
            return "PrintScreen"

        # --- Alt combos ---
        if self._alt_down:
            if vk == VK_TAB:
                return "Alt+Tab"
            if vk == VK_F4:
                return "Alt+F4"
            if vk == VK_ESCAPE:
                return "Alt+Esc"

        # --- Ctrl combos ---
        if self._ctrl_down:
            if vk == VK_ESCAPE:
                if self._shift_down:
                    return "Ctrl+Shift+Esc"
                return "Ctrl+Esc"

            # Ctrl+Win+any
            if self._win_down:
                return "Ctrl+Win combo"

        # --- Win+any (Win is down and another key is pressed) ---
        if self._win_down and vk not in (VK_LWIN, VK_RWIN):
            return "Win+key combo"

        return None

    # -- Incident reporting with throttle -----------------------------------

    def _report_blocked(self, description: str) -> None:
        """Report a blocked key event, throttled to 1 per description per 2 seconds."""
        now = time.time()
        last_report = self._throttle_map.get(description, 0.0)

        if now - last_report < self._throttle_seconds:
            return  # Throttled

        self._throttle_map[description] = now
        self._manager.report(
            "KEYBOARD_BLOCKED",
            "warning",
            description,
            subsystem_name=self.name,
        )


__all__ = ["KeyboardLockdown"]
