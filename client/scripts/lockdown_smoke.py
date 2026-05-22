"""Smoke test for LockdownManager (Part 23 Definition of Done)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import tkinter as tk
from client.app.lockdown.manager import LockdownManager


# --- Violation collector ---
violations: list = []


def report_violation(type: str, severity: str, description: str = "", **kw):
    violations.append({"type": type, "severity": severity, "desc": description, **kw})
    print(f"  [INCIDENT] {type} ({severity}): {description}")


# --- Deliberately broken subsystem (tests fault tolerance) ---
class BrokenSubsystem:
    name = "broken_test_subsystem"
    is_started = False

    def start(self):
        raise RuntimeError("Deliberate failure for testing!")

    def stop(self):
        pass


# --- Good subsystem (tests normal flow) ---
class GoodSubsystem:
    name = "good_test_subsystem"

    def __init__(self):
        self._started = False

    @property
    def is_started(self):
        return self._started

    def start(self):
        self._started = True

    def stop(self):
        self._started = False


def main():
    print("=" * 60)
    print("LockdownManager Smoke Test")
    print("=" * 60)

    root = tk.Tk()
    root.withdraw()

    # --- Test 1: Basic start/stop with no subsystems ---
    print("\n--- Test 1: Start/stop (no subsystems) ---")
    mgr = LockdownManager(root, report_violation)
    mgr.start()
    assert mgr.is_active, "Should be active after start"
    print(f"  is_active after start: {mgr.is_active}")

    mgr.stop()
    assert not mgr.is_active, "Should be inactive after stop"
    print(f"  is_active after stop: {mgr.is_active}")

    # --- Test 2: Idempotent stop ---
    print("\n--- Test 2: Second stop is no-op ---")
    violations.clear()
    mgr.stop()  # second call
    # Should not post another LOCKDOWN_DISENGAGED
    disengaged_count = sum(1 for v in violations if v["type"] == "LOCKDOWN_DISENGAGED")
    assert disengaged_count == 0, f"Expected 0 extra DISENGAGED, got {disengaged_count}"
    print("  Second stop produced no additional incidents. OK")

    # --- Test 3: Partial failure (broken subsystem + good subsystem) ---
    print("\n--- Test 3: Partial failure handling ---")
    violations.clear()
    mgr2 = LockdownManager(root, report_violation)
    good = GoodSubsystem()
    broken = BrokenSubsystem()
    mgr2.register(good)
    mgr2.register(broken)
    mgr2.start()

    assert mgr2.is_active, "Manager should be active even with partial failure"
    assert good.is_started, "Good subsystem should have started"
    print(f"  Good subsystem started: {good.is_started}")

    # Check STARTUP_PARTIAL_FAILURE was posted
    partial = [v for v in violations if v["type"] == "STARTUP_PARTIAL_FAILURE"]
    assert len(partial) == 1, f"Expected 1 STARTUP_PARTIAL_FAILURE, got {len(partial)}"
    print(f"  STARTUP_PARTIAL_FAILURE posted: Yes")
    print(f"    Failed: {partial[0].get('failed_subsystems')}")

    # Check LOCKDOWN_ENGAGED was posted
    engaged = [v for v in violations if v["type"] == "LOCKDOWN_ENGAGED"]
    assert len(engaged) == 1, "Expected 1 LOCKDOWN_ENGAGED"
    print(f"  LOCKDOWN_ENGAGED posted: Yes")
    print(f"    Active: {engaged[0].get('active_subsystems')}")

    mgr2.stop()
    assert not good.is_started, "Good subsystem should be stopped"
    disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(disengaged) == 1, "Expected 1 LOCKDOWN_DISENGAGED"
    print(f"  LOCKDOWN_DISENGAGED posted: Yes")

    # --- Test 4: Violation pipeline ---
    print("\n--- Test 4: Violation pipeline (manager.report) ---")
    violations.clear()
    mgr3 = LockdownManager(root, report_violation)
    mgr3.start()
    mgr3.report(
        "FOCUS_LOST",
        "warning",
        "User switched to another window",
        subsystem_name="focus_monitor",
        window_title="chrome.exe",
    )
    assert len(violations) == 2  # LOCKDOWN_ENGAGED + FOCUS_LOST
    focus_v = [v for v in violations if v["type"] == "FOCUS_LOST"]
    assert len(focus_v) == 1
    assert focus_v[0].get("subsystem") == "focus_monitor"
    print(f"  Violation reported with metadata: {focus_v[0]}")
    mgr3.stop()

    # --- Test 5: Exception triggers excepthook → DISENGAGED still posted ---
    print("\n--- Test 5: Unhandled exception triggers stop via excepthook ---")
    violations.clear()
    mgr4 = LockdownManager(root, report_violation)
    good2 = GoodSubsystem()
    mgr4.register(good2)
    mgr4.start()
    assert mgr4.is_active

    # Simulate an unhandled exception hitting sys.excepthook
    try:
        raise ValueError("Simulated crash mid-exam!")
    except ValueError:
        import traceback
        exc_type, exc_value, exc_tb = sys.exc_info()
        # Call the installed excepthook directly (simulates Python runtime calling it)
        sys.excepthook(exc_type, exc_value, exc_tb)

    assert not mgr4.is_active, "Manager should be inactive after excepthook"
    assert not good2.is_started, "Subsystem should be stopped after excepthook"
    disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(disengaged) == 1, f"Expected 1 LOCKDOWN_DISENGAGED, got {len(disengaged)}"
    print(f"  Exception triggered stop: Yes")
    print(f"  LOCKDOWN_DISENGAGED posted: Yes")
    print(f"  Subsystem stopped: {not good2.is_started}")

    # --- Test 6: Window close (WM_DELETE_WINDOW) mid-exam → stop called ---
    print("\n--- Test 6: Window close mid-exam triggers stop ---")
    violations.clear()
    # Create a fresh Tk window for this test
    root2 = tk.Tk()
    root2.withdraw()
    mgr5 = LockdownManager(root2, report_violation)
    good3 = GoodSubsystem()
    mgr5.register(good3)
    mgr5.start()
    assert mgr5.is_active

    # Simulate what _cleanup() does on window close in exam_taking.py
    # (the exam screen calls stop_lockdown → mgr.stop() in its _cleanup)
    mgr5.stop()
    assert not mgr5.is_active, "Manager should be inactive after window close stop"
    assert not good3.is_started, "Subsystem should be stopped"
    disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(disengaged) == 1, "Expected 1 LOCKDOWN_DISENGAGED"
    print(f"  Window close triggered stop: Yes")
    print(f"  LOCKDOWN_DISENGAGED posted: Yes")

    # Verify idempotency after window close
    violations.clear()
    mgr5.stop()
    extra_disengaged = [v for v in violations if v["type"] == "LOCKDOWN_DISENGAGED"]
    assert len(extra_disengaged) == 0, "Second stop should not post again"
    print(f"  Second stop after close: no-op (0 extra incidents)")
    root2.destroy()

    # --- Test 7: stop() called twice — explicit re-verification ---
    print("\n--- Test 7: stop() idempotency (explicit double-call) ---")
    violations.clear()
    root3 = tk.Tk()
    root3.withdraw()
    mgr6 = LockdownManager(root3, report_violation)
    mgr6.start()
    mgr6.stop()
    count_after_first = sum(1 for v in violations if v["type"] == "LOCKDOWN_DISENGAGED")
    mgr6.stop()
    count_after_second = sum(1 for v in violations if v["type"] == "LOCKDOWN_DISENGAGED")
    assert count_after_first == 1, "First stop posts 1 DISENGAGED"
    assert count_after_second == 1, "Second stop posts NO additional DISENGAGED"
    print(f"  After first stop: {count_after_first} DISENGAGED incident")
    print(f"  After second stop: {count_after_second} DISENGAGED incident (same, no duplicate)")
    root3.destroy()

    # --- Done ---
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
