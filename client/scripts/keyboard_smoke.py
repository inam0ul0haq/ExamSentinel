"""Smoke test for KeyboardLockdown (Part 24 Definition of Done).

Tests:
1. Hook installs successfully
2. Hook uninstalls cleanly on stop
3. Idempotent stop
4. Incident throttling works
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk
from client.app.lockdown.manager import LockdownManager
from client.app.lockdown.keyboard import KeyboardLockdown


violations: list = []


def report_violation(type: str, severity: str, description: str = "", **kw):
    violations.append({"type": type, "severity": severity, "desc": description, **kw})
    print(f"  [INCIDENT] {type} ({severity}): {description}")


def main():
    print("=" * 60)
    print("KeyboardLockdown Smoke Test")
    print("=" * 60)

    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()

    # --- Test 1: Hook installs and starts ---
    print("\n--- Test 1: Hook installation ---")
    mgr = LockdownManager(root, report_violation, shutdown_event=shutdown)
    kb = KeyboardLockdown(mgr, shutdown)
    mgr.register(kb)
    mgr.start()

    assert kb.is_started, "Keyboard hook should be started"
    print(f"  is_started: {kb.is_started}")
    print(f"  Manager active: {mgr.is_active}")

    # Check LOCKDOWN_ENGAGED was posted
    engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
    assert len(engaged) == 1
    assert "keyboard_hook" in engaged[0].get("active_subsystems", [])
    print(f"  LOCKDOWN_ENGAGED active_subsystems: {engaged[0].get('active_subsystems')}")

    # --- Test 2: Throttle mechanism ---
    print("\n--- Test 2: Throttle test ---")
    violations.clear()
    # Simulate rapid blocked events
    kb._report_blocked("Alt+Tab")
    kb._report_blocked("Alt+Tab")  # Should be throttled
    kb._report_blocked("Alt+Tab")  # Should be throttled
    kb._report_blocked("Win key")  # Different key - should go through

    blocked = [v for v in violations if v["type"] == "KEYBOARD_BLOCKED"]
    assert len(blocked) == 2, f"Expected 2 (1 Alt+Tab + 1 Win key), got {len(blocked)}"
    print(f"  Rapid Alt+Tab x3 + Win key x1 → {len(blocked)} incidents posted (throttled correctly)")

    # --- Test 3: Clean stop ---
    print("\n--- Test 3: Clean stop + unhook ---")
    violations.clear()
    mgr.stop()

    assert not kb.is_started, "Hook should be uninstalled"
    disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(disengaged) == 1
    print(f"  is_started after stop: {kb.is_started}")
    print(f"  LOCKDOWN_DISENGAGED posted: Yes")

    # --- Test 4: Idempotent stop ---
    print("\n--- Test 4: Idempotent stop ---")
    violations.clear()
    mgr.stop()  # second call
    extra = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(extra) == 0
    print(f"  Second stop: no-op (0 extra incidents)")

    # --- Test 5: After stop, Alt+Tab should work again ---
    print("\n--- Test 5: Post-stop verification ---")
    print("  Hook removed — keyboard restored to normal.")
    print("  (Manual verification: Alt+Tab works after this test)")

    print("\n" + "=" * 60)
    print("ALL KEYBOARD TESTS PASSED")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
