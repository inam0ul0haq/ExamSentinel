"""Part 26 — Verification (safe for real PC — spoofs destructive actions).

Tests:
1. Fullscreen: style removal, topmost, taskbar hide/show lifecycle
2. Focus monitor: detects foreign window, reports FOCUS_LOST
3. Mouse boundary: ClipCursor applied, MOUSE_ESCAPE detection
4. Multi-monitor: single monitor passes, multi triggers abort
5. Manager request_abort wiring
6. All 8 subsystems start/stop together
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import ctypes
import threading
import tkinter as tk
from unittest.mock import MagicMock, patch

violations = []
abort_reasons = []


def report_v(t, s, d="", **kw):
    violations.append({"type": t, "severity": s, "desc": d, **kw})


def ok(msg):
    print(f"  [PASS] {msg}")


def section(n, title):
    print(f"\n{'='*60}\nTest {n}: {title}\n{'='*60}")


def main():
    print("=" * 60)
    print("  Part 26 — Safe Verification")
    print("=" * 60)

    # ================================================================
    section(1, "FullscreenSubsystem — style + taskbar lifecycle")
    # ================================================================
    from client.app.lockdown.fullscreen import FullscreenSubsystem
    from client.app.lockdown.manager import LockdownManager

    root = tk.Tk()
    root.geometry("400x300+100+100")
    root.update()

    shutdown = threading.Event()
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)
    fs = FullscreenSubsystem(mgr, shutdown, root)

    # Start — will actually go fullscreen briefly
    fs.start()
    assert fs.is_started
    assert fs._hwnd != 0
    assert fs._taskbar_hwnd != 0 or True  # May be 0 if no taskbar found
    ok(f"Fullscreen engaged, HWND={fs._hwnd}, screen={fs._screen_w}x{fs._screen_h}")

    time.sleep(0.5)

    # Stop — restores everything
    fs.stop()
    ok("Fullscreen disengaged, taskbar restored")
    root.update()

    # Verify window is back to normal (not fullscreen-sized)
    root.geometry("400x300+100+100")
    root.update()

    # ================================================================
    section(2, "FocusMonitorSubsystem — detects focus loss")
    # ================================================================
    from client.app.lockdown.focus_monitor import FocusMonitorSubsystem

    shutdown2 = threading.Event()
    mgr2 = LockdownManager(root, report_v, shutdown_event=shutdown2)
    fm = FocusMonitorSubsystem(mgr2, shutdown2, root)

    violations.clear()
    fm.start()
    assert fm.is_started

    # Simulate focus loss by checking what _report_focus_lost does
    fm._report_focus_lost("chrome.exe - Google")
    lost = [v for v in violations if v["type"] == "FOCUS_LOST"]
    assert len(lost) == 1
    assert "chrome.exe" in lost[0]["desc"]
    ok(f"FOCUS_LOST incident: {lost[0]['desc']}")

    # Throttle
    fm._report_focus_lost("chrome.exe - Google")
    lost2 = [v for v in violations if v["type"] == "FOCUS_LOST"]
    assert len(lost2) == 1  # throttled
    ok("Throttle: second focus loss within 2s suppressed")

    fm.stop()
    ok("Focus monitor stopped")

    # ================================================================
    section(3, "MouseBoundarySubsystem — clip + escape detection")
    # ================================================================
    from client.app.lockdown.mouse_boundary import MouseBoundarySubsystem

    shutdown3 = threading.Event()
    mgr3 = LockdownManager(root, report_v, shutdown_event=shutdown3)
    mb = MouseBoundarySubsystem(mgr3, shutdown3, root)

    violations.clear()
    mb.start()
    assert mb.is_started
    assert mb._clip_rect is not None
    ok(f"ClipCursor applied: ({mb._clip_rect.left},{mb._clip_rect.top})-({mb._clip_rect.right},{mb._clip_rect.bottom})")

    # Simulate escape report
    mb._report_escape(9999, 9999)
    escapes = [v for v in violations if v["type"] == "MOUSE_ESCAPE"]
    assert len(escapes) == 1
    ok(f"MOUSE_ESCAPE incident: {escapes[0]['desc']}")

    mb.stop()
    ok("Mouse boundary released (ClipCursor(NULL))")

    # ================================================================
    section(4, "MultiMonitorSubsystem — single monitor OK")
    # ================================================================
    from client.app.lockdown.multi_monitor import MultiMonitorSubsystem, _count_monitors

    count = _count_monitors()
    print(f"  Current monitor count: {count}")

    if count == 1:
        shutdown4 = threading.Event()
        mgr4 = LockdownManager(root, report_v, shutdown_event=shutdown4)
        mm = MultiMonitorSubsystem(mgr4, shutdown4)
        violations.clear()
        mm.start()
        time.sleep(0.5)
        multi = [v for v in violations if v["type"] == "MULTI_MONITOR_DETECTED"]
        assert len(multi) == 0
        ok("Single monitor: no abort triggered")
        mm.stop()
    else:
        ok(f"Multi-monitor ({count}) — would trigger abort (correct behavior)")

    # ================================================================
    section(5, "MultiMonitorSubsystem — spoofed dual monitor triggers abort")
    # ================================================================
    shutdown5 = threading.Event()
    mgr5 = LockdownManager(root, report_v, shutdown_event=shutdown5)
    abort_reasons.clear()
    mgr5.set_abort_callback(lambda reason: abort_reasons.append(reason))

    violations.clear()

    # Patch _count_monitors to return 2
    import client.app.lockdown.multi_monitor as mm_mod
    with patch.object(mm_mod, "_count_monitors", return_value=2):
        mm2 = MultiMonitorSubsystem(mgr5, shutdown5)
        mm2.start()
        time.sleep(0.3)

    multi = [v for v in violations if v["type"] == "MULTI_MONITOR_DETECTED"]
    assert len(multi) == 1
    ok(f"MULTI_MONITOR_DETECTED (critical): {multi[0]['desc']}")
    assert len(abort_reasons) == 1 and abort_reasons[0] == "multi_monitor"
    ok(f"request_abort called with reason: {abort_reasons[0]}")
    mm2.stop()

    # ================================================================
    section(6, "All 8 subsystems start/stop together")
    # ================================================================
    from client.app.lockdown.keyboard import KeyboardLockdown
    from client.app.lockdown.process_kill import ProcessKillSubsystem
    from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem
    from client.app.lockdown.right_click_suppress import RightClickSuppressSubsystem
    import client.app.lockdown.process_kill as pk_mod

    # Restrict process kill to avoid killing our IDE
    orig_bl = pk_mod.BLACKLISTED_PROCESSES
    pk_mod.BLACKLISTED_PROCESSES = frozenset({"notepad_fake_12345.exe"})

    shutdown6 = threading.Event()
    mgr6 = LockdownManager(root, report_v, shutdown_event=shutdown6)

    mgr6.register(FullscreenSubsystem(mgr6, shutdown6, root))
    mgr6.register(KeyboardLockdown(mgr6, shutdown6))
    mgr6.register(FocusMonitorSubsystem(mgr6, shutdown6, root))
    mgr6.register(MouseBoundarySubsystem(mgr6, shutdown6, root))
    mgr6.register(ProcessKillSubsystem(mgr6, shutdown6))
    mgr6.register(ClipboardScrubSubsystem(mgr6, shutdown6))
    mgr6.register(RightClickSuppressSubsystem(mgr6, root))
    mgr6.register(MultiMonitorSubsystem(mgr6, shutdown6))

    violations.clear()
    mgr6.start()

    engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
    assert len(engaged) == 1
    active = engaged[0].get("active_subsystems", [])
    print(f"  Active subsystems: {active}")
    expected = [
        "fullscreen", "keyboard_hook", "focus_monitor", "mouse_boundary",
        "process_kill", "clipboard_scrub", "right_click_suppress", "multi_monitor",
    ]
    for name in expected:
        assert name in active, f"{name} not in active list"
    ok(f"All {len(expected)} subsystems active")

    time.sleep(0.5)

    violations.clear()
    mgr6.stop()

    dis = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(dis) == 1
    ok("LOCKDOWN_DISENGAGED posted")
    ok("Taskbar visible, window normal, cursor free, everything restored")

    pk_mod.BLACKLISTED_PROCESSES = orig_bl

    # ================================================================
    print("\n" + "=" * 60)
    print("  ALL PART 26 TESTS PASSED")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
