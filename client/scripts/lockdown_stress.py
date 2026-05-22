"""Lockdown stress test — simulates a 10-second exam with all subsystems.

Verifies that after simulated submit, all subsystems report is_started=False,
taskbar is visible, no topmost flag, ClipCursor is released.

Safe for real PC: process kill restricted to a fake name.
"""

import sys
import os
import time
import ctypes
import ctypes.wintypes as wintypes

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk

from client.app.lockdown.manager import LockdownManager
import client.app.lockdown.process_kill as pk_mod

violations = []
EXAM_DURATION_S = 5  # shortened for CI


def report_v(t, s, d="", **kw):
    violations.append({"type": t, "severity": s, "desc": d, **kw})


def main():
    user32 = ctypes.windll.user32

    print("=" * 60)
    print("  Lockdown Stress Test — Simulated Exam")
    print("=" * 60)

    # Restrict process kill to fake process so we don't kill anything
    orig_bl = pk_mod.BLACKLISTED_PROCESSES
    pk_mod.BLACKLISTED_PROCESSES = frozenset({"fake_proc_12345.exe"})

    root = tk.Tk()
    root.title("ExamSentinel Stress Test")
    root.geometry("800x600+50+50")
    root.update()

    shutdown = threading.Event()
    violations.clear()

    # --- START LOCKDOWN ---
    print("\n--- Starting lockdown (all 8 subsystems) ---")
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)
    mgr.register_all(root, shutdown)
    mgr.start()

    engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
    assert len(engaged) == 1
    active = engaged[0].get("active_subsystems", [])
    print(f"  Active subsystems ({len(active)}): {active}")

    expected_names = [
        "multi_monitor", "keyboard_hook", "process_kill", "clipboard_scrub",
        "right_click_suppress", "fullscreen", "focus_monitor", "mouse_boundary",
    ]
    for name in expected_names:
        assert name in active, f"Missing: {name}"
    print("  All 8 subsystems active: PASS")

    # --- SIMULATE EXAM (5 seconds) ---
    print(f"\n--- Simulating exam ({EXAM_DURATION_S}s) ---")
    for i in range(EXAM_DURATION_S):
        time.sleep(1)
        print(f"  Exam second {i+1}/{EXAM_DURATION_S}...")

    # --- SUBMIT (stop lockdown) ---
    print("\n--- Simulating submit → stopping lockdown ---")
    violations.clear()
    mgr.stop()

    disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(disengaged) == 1
    print("  LOCKDOWN_DISENGAGED: PASS")

    # --- POST-SUBMIT VERIFICATION ---
    print("\n--- Post-submit verification ---")
    results = []

    # 1. All subsystems is_started == False
    all_stopped = True
    for sub in mgr._subsystems:
        if sub.is_started:
            print(f"  FAIL: {sub.name} still started!")
            all_stopped = False
    if all_stopped:
        print("  All subsystems is_started=False: PASS")
        results.append(True)
    else:
        results.append(False)

    # 2. Taskbar visible
    taskbar = user32.FindWindowW("Shell_TrayWnd", None)
    if taskbar:
        visible = user32.IsWindowVisible(taskbar)
        print(f"  Taskbar visible: {'PASS' if visible else 'FAIL'}")
        results.append(visible)
    else:
        print("  Taskbar: N/A (no HWND found)")
        results.append(True)

    # 3. No topmost flag on our window
    hwnd = root.winfo_id()
    parent = user32.GetParent(hwnd)
    check_hwnd = parent if parent else hwnd
    exstyle = user32.GetWindowLongPtrW(check_hwnd, -20)  # GWL_EXSTYLE
    is_topmost = bool(exstyle & 0x00000008)  # WS_EX_TOPMOST
    print(f"  No topmost flag: {'PASS' if not is_topmost else 'FAIL'}")
    results.append(not is_topmost)

    # 4. ClipCursor released — check if cursor can move freely
    # Try to move cursor to (0,0) then check it's there
    user32.SetCursorPos(10, 10)
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    cursor_free = (pt.x == 10 and pt.y == 10)
    print(f"  ClipCursor released (cursor free): {'PASS' if cursor_free else 'FAIL'}")
    results.append(cursor_free)

    # 5. Second stop is no-op
    violations.clear()
    mgr.stop()
    extra = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    idempotent = len(extra) == 0
    print(f"  Second stop idempotent: {'PASS' if idempotent else 'FAIL'}")
    results.append(idempotent)

    # Restore blacklist
    pk_mod.BLACKLISTED_PROCESSES = orig_bl

    # --- SUMMARY ---
    all_pass = all(results)
    print("\n" + "=" * 60)
    if all_pass:
        print("  ALL STRESS TESTS PASSED")
    else:
        print("  SOME TESTS FAILED")
    print("=" * 60)

    root.destroy()
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
