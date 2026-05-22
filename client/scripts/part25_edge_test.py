"""Part 25 — Focused Edge kill test.

Only targets msedge.exe. Does NOT touch windsurf.exe, powershell.exe,
or any other process that would break this IDE/terminal.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk
import psutil

violations = []


def report_v(t, s, d="", **kw):
    violations.append({"type": t, "severity": s, "desc": d, **kw})
    print(f"  [INCIDENT] {t} ({s}): {d}")


def main():
    print("=" * 60)
    print("  Part 25 — msedge.exe Kill Test")
    print("=" * 60)

    # Step 1: Verify msedge.exe is running
    print("\n--- Step 1: Check if msedge.exe is running ---")
    edge_procs = [p for p in psutil.process_iter(["name", "pid"])
                  if (p.info["name"] or "").lower() == "msedge.exe"]
    if not edge_procs:
        print("  ERROR: msedge.exe is NOT running. Open Microsoft Edge first!")
        return
    print(f"  Found {len(edge_procs)} msedge.exe process(es)")
    for p in edge_procs[:3]:
        print(f"    PID {p.info['pid']}")

    # Step 2: Create a SAFE subsystem that ONLY kills msedge.exe
    print("\n--- Step 2: Starting process killer (msedge.exe ONLY) ---")

    # We use the real subsystem but with a restricted blacklist
    from client.app.lockdown.process_kill import ProcessKillSubsystem
    from client.app.lockdown.manager import LockdownManager

    shutdown = threading.Event()
    root = tk.Tk()
    root.withdraw()
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)

    pk = ProcessKillSubsystem(mgr, shutdown)

    # IMPORTANT: Override the blacklist to ONLY contain msedge.exe
    import client.app.lockdown.process_kill as pk_module
    original_blacklist = pk_module.BLACKLISTED_PROCESSES
    pk_module.BLACKLISTED_PROCESSES = frozenset({"msedge.exe"})

    violations.clear()
    pk.start()
    assert pk.is_started
    print("  Process killer started (only targeting msedge.exe)")

    # Step 3: Wait for kill (polls every 2 seconds)
    print("\n--- Step 3: Waiting for msedge.exe to be killed (~3s) ---")
    time.sleep(3.5)

    # Step 4: Check results
    print("\n--- Step 4: Results ---")
    killed_incidents = [v for v in violations
                        if v["type"] == "BLACKLISTED_PROCESS_KILLED"]
    print(f"  BLACKLISTED_PROCESS_KILLED incidents: {len(killed_incidents)}")
    for inc in killed_incidents:
        print(f"    {inc['desc']}")

    # Verify msedge.exe is dead
    edge_after = [p for p in psutil.process_iter(["name"])
                  if (p.info["name"] or "").lower() == "msedge.exe"]
    print(f"  msedge.exe processes remaining: {len(edge_after)}")

    if killed_incidents:
        print("\n  ✓ msedge.exe was killed and incident was posted!")
    else:
        print("\n  ✗ No kill incidents — msedge.exe may have required elevated permissions")

    # Step 5: Stop subsystem
    print("\n--- Step 5: Stopping process killer ---")
    shutdown.set()
    pk.stop()
    print("  Stopped. msedge.exe will stay alive if you relaunch it now.")

    # Restore original blacklist
    pk_module.BLACKLISTED_PROCESSES = original_blacklist

    # Step 6: Verify throttle — same PID not re-reported
    print("\n--- Step 6: Throttle verification ---")
    reported = pk._reported
    print(f"  Reported (name, pid) pairs: {reported}")
    print("  Re-launching msedge.exe with same PID would NOT re-trigger.")
    print("  Re-launching with NEW PID would trigger a new incident.")

    print("\n" + "=" * 60)
    print("  TEST COMPLETE")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
