"""Part 24 Definition of Done verification.

Covers all four verification points:
  1. Block decision logic for Alt+Tab, Win, Ctrl+Esc, Ctrl+Shift+Esc, Alt+F4,
     PrintScreen — confirms hook would return 1 (block) for each.
  2. Throttle: rapid identical events → at most 1 incident per 2 seconds.
  3. stop() removes hook cleanly (is_started=False, no leaked state).
  4. UNAVAILABLE path: if SetWindowsHookExW fails, subsystem posts
     KEYBOARD_HOOK_UNAVAILABLE, is_started=False, manager continues with
     other subsystems.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk
from unittest.mock import patch, MagicMock

from client.app.lockdown.manager import LockdownManager
from client.app.lockdown.keyboard import (
    KeyboardLockdown,
    VK_TAB, VK_ESCAPE, VK_F4, VK_LWIN, VK_SNAPSHOT,
)


violations: list = []


def report_violation(type: str, severity: str, description: str = "", **kw):
    violations.append({"type": type, "severity": severity, "desc": description, **kw})


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


# ============================================================================
# Verification 1: Block decision logic
# ============================================================================
def verify_block_decisions():
    section("Verification 1: Block decision for all required combos")

    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_violation, shutdown_event=shutdown)
    kb = KeyboardLockdown(mgr, shutdown)

    # Test cases: (description, setup, vk, expected_block_reason)
    test_cases = [
        # Alt + Tab
        ("Alt+Tab",
         lambda: setattr(kb, "_alt_down", True),
         VK_TAB,
         "Alt+Tab"),
        # Alt + F4
        ("Alt+F4",
         lambda: setattr(kb, "_alt_down", True),
         VK_F4,
         "Alt+F4"),
        # Alt + Esc
        ("Alt+Esc",
         lambda: setattr(kb, "_alt_down", True),
         VK_ESCAPE,
         "Alt+Esc"),
        # Ctrl + Esc
        ("Ctrl+Esc (Start menu)",
         lambda: (setattr(kb, "_ctrl_down", True), setattr(kb, "_shift_down", False)),
         VK_ESCAPE,
         "Ctrl+Esc"),
        # Ctrl + Shift + Esc
        ("Ctrl+Shift+Esc (Task Manager)",
         lambda: (setattr(kb, "_ctrl_down", True), setattr(kb, "_shift_down", True)),
         VK_ESCAPE,
         "Ctrl+Shift+Esc"),
        # Win alone
        ("Win key alone",
         lambda: None,
         VK_LWIN,
         "Win key"),
        # PrintScreen
        ("PrintScreen",
         lambda: None,
         VK_SNAPSHOT,
         "PrintScreen"),
    ]

    allowed_cases = [
        # Plain Tab (no Alt)
        ("Plain Tab (allowed)", lambda: None, VK_TAB, None),
        # Plain Esc (no modifier)
        ("Plain Esc (allowed)", lambda: None, VK_ESCAPE, None),
        # Letter 'A' (vk 0x41)
        ("Letter 'A' (allowed)", lambda: None, 0x41, None),
    ]

    print("\nBLOCKED combos:")
    all_passed = True
    for desc, setup, vk, expected in test_cases:
        # Reset modifier state
        kb._alt_down = False
        kb._ctrl_down = False
        kb._shift_down = False
        kb._win_down = False
        if setup:
            setup()

        reason = kb._should_block(vk, is_down=True)
        ok = (reason == expected)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {desc:35s} → reason={reason!r}  (expected: {expected!r})")
        if not ok:
            all_passed = False

    print("\nALLOWED keys (should NOT block):")
    for desc, setup, vk, expected in allowed_cases:
        kb._alt_down = False
        kb._ctrl_down = False
        kb._shift_down = False
        kb._win_down = False
        if setup:
            setup()

        reason = kb._should_block(vk, is_down=True)
        ok = (reason == expected)
        marker = "✓" if ok else "✗"
        print(f"  {marker} {desc:35s} → reason={reason!r}  (expected: {expected!r})")
        if not ok:
            all_passed = False

    root.destroy()
    assert all_passed, "Some block decisions failed!"
    print("\nResult: All block/allow decisions correct ✓")


# ============================================================================
# Verification 2: Throttle (≤1 incident per 2 seconds per description)
# ============================================================================
def verify_throttle():
    section("Verification 2: Throttle (≤1 identical incident per 2 sec)")

    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_violation, shutdown_event=shutdown)
    kb = KeyboardLockdown(mgr, shutdown)

    violations.clear()

    # Burst 10 identical events
    for _ in range(10):
        kb._report_blocked("Alt+Tab")

    burst_count = sum(1 for v in violations if v["desc"] == "Alt+Tab")
    print(f"  10 rapid Alt+Tab → {burst_count} incident(s) posted")
    assert burst_count == 1, f"Expected 1 incident from burst, got {burst_count}"

    # Wait 2.1 seconds, try again
    print("  Waiting 2.1s for throttle window to expire...")
    time.sleep(2.1)
    kb._report_blocked("Alt+Tab")

    after_wait = sum(1 for v in violations if v["desc"] == "Alt+Tab")
    print(f"  After 2.1s + 1 more Alt+Tab → {after_wait} total incident(s)")
    assert after_wait == 2, f"Expected 2 total after wait, got {after_wait}"

    # Different key bypasses throttle
    kb._report_blocked("PrintScreen")
    ps_count = sum(1 for v in violations if v["desc"] == "PrintScreen")
    assert ps_count == 1
    print(f"  Different key (PrintScreen) → {ps_count} incident (independent throttle) ✓")

    root.destroy()
    print("\nResult: Throttle works correctly ✓")


# ============================================================================
# Verification 3: stop() removes hook, restores keyboard
# ============================================================================
def verify_clean_stop():
    section("Verification 3: stop() removes hook, restores keyboard")

    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_violation, shutdown_event=shutdown)
    kb = KeyboardLockdown(mgr, shutdown)
    mgr.register(kb)

    violations.clear()
    mgr.start()

    assert kb.is_started, "Hook should be installed after start"
    assert kb._hook_handle is not None, "Hook handle should be set"
    print(f"  Hook installed: is_started={kb.is_started}, handle set: {kb._hook_handle is not None}")

    mgr.stop()

    assert not kb.is_started, "Hook should be uninstalled after stop"
    assert kb._thread is None, "Hook thread should be cleared"
    print(f"  After stop: is_started={kb.is_started}, thread cleared: {kb._thread is None}")
    print(f"  Keyboard restored — Alt+Tab/Win key work again ✓")

    root.destroy()
    print("\nResult: Clean shutdown works ✓")


# ============================================================================
# Verification 4: UNAVAILABLE path (hook install fails)
# ============================================================================
def verify_unavailable_path():
    section("Verification 4: UNAVAILABLE path (no admin / hook blocked)")

    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_violation, shutdown_event=shutdown)

    # Simulate SetWindowsHookExW failure by mocking
    import ctypes

    original_windll = ctypes.windll

    class FakeUser32:
        @staticmethod
        def SetWindowsHookExW(*args, **kwargs):
            return 0  # NULL = failure

        @staticmethod
        def UnhookWindowsHookEx(*args, **kwargs):
            return 1

        @staticmethod
        def PostThreadMessageW(*args, **kwargs):
            return 1

        @staticmethod
        def PeekMessageW(*args, **kwargs):
            return 0

        @staticmethod
        def TranslateMessage(*args, **kwargs):
            return 1

        @staticmethod
        def DispatchMessageW(*args, **kwargs):
            return 0

        @staticmethod
        def CallNextHookEx(*args, **kwargs):
            return 0

    class FakeKernel32:
        @staticmethod
        def GetCurrentThreadId():
            return 12345

        @staticmethod
        def GetLastError():
            return 5  # ERROR_ACCESS_DENIED

    class FakeWindll:
        user32 = FakeUser32()
        kernel32 = FakeKernel32()

    # Add a "good" subsystem to verify lockdown continues despite keyboard failure
    class GoodSub:
        name = "good_subsystem"
        def __init__(self): self._s = False
        @property
        def is_started(self): return self._s
        def start(self): self._s = True
        def stop(self): self._s = False

    good = GoodSub()
    mgr.register(good)

    with patch.object(ctypes, "windll", FakeWindll()):
        kb = KeyboardLockdown(mgr, shutdown)
        mgr.register(kb)

        violations.clear()
        mgr.start()

        # Give hook thread a moment
        time.sleep(0.5)

        # Verify subsystem reports unavailable
        assert not kb.is_started, "Hook should not be started"
        unavailable = [v for v in violations if v["type"] == "KEYBOARD_HOOK_UNAVAILABLE"]
        assert len(unavailable) == 1, f"Expected 1 UNAVAILABLE incident, got {len(unavailable)}"
        print(f"  Keyboard hook failed: is_started={kb.is_started}")
        print(f"  KEYBOARD_HOOK_UNAVAILABLE posted: Yes")
        print(f"    Description: {unavailable[0]['desc']}")

        # Verify other subsystems continued
        assert good.is_started, "Good subsystem should still be active"
        print(f"  Other subsystem (good) still active: {good.is_started}")

        # Verify LOCKDOWN_ENGAGED was still posted
        engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
        assert len(engaged) == 1
        print(f"  LOCKDOWN_ENGAGED posted with active: {engaged[0].get('active_subsystems')}")
        print(f"  Failed subsystems: {engaged[0].get('failed_subsystems')}")

        mgr.stop()

    root.destroy()
    print("\nResult: UNAVAILABLE path works — lockdown gracefully degrades ✓")


# ============================================================================
def main():
    print("=" * 60)
    print("  Part 24 — Definition of Done Verification")
    print("=" * 60)

    verify_block_decisions()
    verify_throttle()
    verify_clean_stop()
    verify_unavailable_path()

    print("\n" + "=" * 60)
    print("  ALL PART 24 VERIFICATION POINTS PASSED ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
