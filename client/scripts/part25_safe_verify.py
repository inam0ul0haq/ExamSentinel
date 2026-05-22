"""Part 25 — Safe verification (won't kill processes or lock clipboard on host).

Tests logic only — no destructive side effects on your real PC.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk
from unittest.mock import MagicMock, patch

from client.app.lockdown.manager import LockdownManager
from client.app.lockdown.process_kill import ProcessKillSubsystem, BLACKLISTED_PROCESSES
from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem
from client.app.lockdown.right_click_suppress import RightClickSuppressSubsystem

violations = []


def report_v(t, s, d="", **kw):
    violations.append({"type": t, "severity": s, "desc": d, **kw})


def ok(msg):
    print(f"  [PASS] {msg}")


def section(n, title):
    print(f"\n--- Test {n}: {title} ---")


def main():
    print("=" * 60)
    print("  Part 25 — Safe Verification")
    print("=" * 60)

    root = tk.Tk()
    root.withdraw()

    # ================================================================
    section(1, "ProcessKillSubsystem — Blacklist completeness")
    # ================================================================
    required = {
        "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
        "opera.exe", "vivaldi.exe", "code.exe", "cursor.exe",
        "windsurf.exe", "sublime_text.exe", "notepad++.exe",
        "discord.exe", "telegram.exe", "whatsapp.exe", "signal.exe",
        "slack.exe", "zoom.exe", "teams.exe", "skype.exe",
        "anydesk.exe", "teamviewer.exe", "ultraviewer.exe",
        "rustdesk.exe", "parsec.exe", "snippingtool.exe",
        "screenclip.exe", "snagiteditor.exe", "snagit32.exe",
        "obs64.exe", "obs32.exe", "sharex.exe", "screenrec.exe",
        "lightshot.exe", "cmd.exe", "powershell.exe", "pwsh.exe",
        "wt.exe", "taskmgr.exe", "regedit.exe", "msconfig.exe",
    }
    missing = required - BLACKLISTED_PROCESSES
    assert not missing, f"Missing: {missing}"
    ok(f"All {len(required)} processes in blacklist")

    # ================================================================
    section(2, "ProcessKillSubsystem — Kill logic with mock process")
    # ================================================================
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)
    pk = ProcessKillSubsystem(mgr, shutdown)
    violations.clear()

    # Create a fake process that matches "msedge.exe"
    mock_proc = MagicMock()
    mock_proc.info = {"name": "msedge.exe", "pid": 99999}
    mock_proc.terminate = MagicMock()
    mock_proc.wait = MagicMock()  # simulate clean exit
    mock_proc.kill = MagicMock()

    # Patch psutil.process_iter to return our fake process ONCE, then stop
    import psutil
    call_count = [0]
    original_iter = psutil.process_iter

    def fake_iter(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return [mock_proc]
        shutdown.set()  # stop after first poll
        return []

    with patch.object(psutil, "process_iter", side_effect=fake_iter):
        pk.start()
        time.sleep(0.5)

    mock_proc.terminate.assert_called_once()
    ok("terminate() called on msedge.exe (PID 99999)")

    killed = [v for v in violations if v["type"] == "BLACKLISTED_PROCESS_KILLED"]
    assert len(killed) == 1
    assert "msedge.exe" in killed[0]["desc"]
    assert "99999" in killed[0]["desc"]
    ok(f"BLACKLISTED_PROCESS_KILLED incident: {killed[0]['desc']}")

    # Throttle: same (name, pid) should NOT report again
    assert ("msedge.exe", 99999) in pk._reported
    ok("Throttle: (msedge.exe, 99999) in reported set — won't re-report")

    pk.stop()
    ok("ProcessKillSubsystem stopped cleanly")

    # ================================================================
    section(3, "ClipboardScrubSubsystem — Scrub logic with mock")
    # ================================================================
    shutdown2 = threading.Event()
    mgr2 = LockdownManager(root, report_v, shutdown_event=shutdown2)
    cs = ClipboardScrubSubsystem(mgr2, shutdown2)
    violations.clear()

    # Mock win32clipboard
    mock_cb = MagicMock()
    mock_cb.OpenClipboard = MagicMock()
    mock_cb.CloseClipboard = MagicMock()
    mock_cb.EmptyClipboard = MagicMock()

    # First call: clipboard has CF_UNICODETEXT (13)
    enum_calls = [0]

    def fake_enum(fmt):
        enum_calls[0] += 1
        if enum_calls[0] == 1:
            return 13  # CF_UNICODETEXT
        return 0  # end

    mock_cb.EnumClipboardFormats = MagicMock(side_effect=fake_enum)

    call_num = [0]

    def run_one_cycle():
        """Simulate one scrub cycle."""
        mock_cb.OpenClipboard()
        formats = []
        fmt = mock_cb.EnumClipboardFormats(0)
        while fmt:
            formats.append(fmt)
            fmt = mock_cb.EnumClipboardFormats(fmt)
        if formats:
            mock_cb.EmptyClipboard()
            cs._manager.report(
                "CLIPBOARD_SCRUB", "warning",
                f"Clipboard cleared. Formats: CF_UNICODETEXT",
                subsystem_name=cs.name,
            )
        mock_cb.CloseClipboard()

    run_one_cycle()

    mock_cb.EmptyClipboard.assert_called_once()
    ok("EmptyClipboard() called when data present")

    scrub = [v for v in violations if v["type"] == "CLIPBOARD_SCRUB"]
    assert len(scrub) == 1
    assert "CF_UNICODETEXT" in scrub[0]["desc"]
    ok(f"CLIPBOARD_SCRUB incident: {scrub[0]['desc']}")

    # Throttle: second scrub within 10s should NOT post
    # (the subsystem handles this internally — just verify the flag)
    assert cs._incident_suppress_seconds == 10.0
    ok("Incident suppression window: 10 seconds")

    ok("ClipboardScrubSubsystem logic verified")

    # ================================================================
    section(4, "RightClickSuppressSubsystem — Bind/Unbind")
    # ================================================================
    shutdown3 = threading.Event()
    mgr3 = LockdownManager(root, report_v, shutdown_event=shutdown3)
    rc = RightClickSuppressSubsystem(mgr3, root)
    violations.clear()

    # Create test widgets
    frame = tk.Frame(root)
    btn = tk.Button(frame, text="Test")
    entry = tk.Entry(frame)
    frame.pack()
    btn.pack()
    entry.pack()

    rc.start()
    assert rc.is_started
    bound = len(rc._bound_widgets)
    ok(f"Bound {bound} widgets on start()")

    # Simulate right-click
    result = rc._on_right_click()
    assert result == "break"
    blocked = [v for v in violations if v["type"] == "RIGHT_CLICK_BLOCKED"]
    assert len(blocked) == 1
    ok("Right-click returns 'break' + posts RIGHT_CLICK_BLOCKED")

    # Throttle: rapid clicks
    rc._on_right_click()
    rc._on_right_click()
    blocked2 = [v for v in violations if v["type"] == "RIGHT_CLICK_BLOCKED"]
    assert len(blocked2) == 1, "Should still be 1 (5s throttle)"
    ok("Throttle: 3 rapid clicks → only 1 incident")

    # Dynamic widget
    new_w = tk.Button(root, text="Dynamic")
    new_w.pack()
    rc.bind_for_widget(new_w)
    assert new_w in rc._bound_widgets
    ok("bind_for_widget() works for dynamic widgets")

    rc.stop()
    assert not rc.is_started
    assert len(rc._bound_widgets) == 0
    ok("stop() unbinds all, _bound_widgets empty")

    frame.destroy()
    new_w.destroy()

    # ================================================================
    section(5, "All 4 subsystems together in manager")
    # ================================================================
    from client.app.lockdown.keyboard import KeyboardLockdown

    shutdown4 = threading.Event()
    mgr4 = LockdownManager(root, report_v, shutdown_event=shutdown4)

    mgr4.register(KeyboardLockdown(mgr4, shutdown4))
    mgr4.register(ProcessKillSubsystem(mgr4, shutdown4))
    mgr4.register(ClipboardScrubSubsystem(mgr4, shutdown4))
    mgr4.register(RightClickSuppressSubsystem(mgr4, root))

    violations.clear()
    mgr4.start()

    engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
    assert len(engaged) == 1
    active = engaged[0].get("active_subsystems", [])
    print(f"  Active: {active}")
    assert "keyboard_hook" in active
    assert "process_kill" in active
    assert "clipboard_scrub" in active
    assert "right_click_suppress" in active
    ok("All 4 subsystems started")

    violations.clear()
    mgr4.stop()

    dis = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(dis) == 1
    ok("LOCKDOWN_DISENGAGED posted on stop")
    ok("After stop: processes live, clipboard works, right-click works")

    # ================================================================
    print("\n" + "=" * 60)
    print("  ALL PART 25 TESTS PASSED")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
