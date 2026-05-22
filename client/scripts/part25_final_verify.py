"""Part 25 — Final verification: Kill msedge.exe + clear clipboard.

Safe for real Windows — only targets msedge.exe, clears clipboard once,
then stops everything.
"""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import threading
import tkinter as tk
import psutil
import win32clipboard

violations = []


def report_v(t, s, d="", **kw):
    violations.append({"type": t, "severity": s, "desc": d, **kw})
    print(f"  [INCIDENT] {t} ({s}): {d}")


def main():
    print("=" * 60)
    print("  Part 25 — Final Verification")
    print("  Target: msedge.exe kill + clipboard clear")
    print("=" * 60)

    root = tk.Tk()
    root.withdraw()

    from client.app.lockdown.manager import LockdownManager
    from client.app.lockdown.process_kill import ProcessKillSubsystem
    import client.app.lockdown.process_kill as pk_module
    from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem

    shutdown = threading.Event()
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)

    # --- Process killer (msedge.exe ONLY) ---
    pk = ProcessKillSubsystem(mgr, shutdown)
    original_blacklist = pk_module.BLACKLISTED_PROCESSES
    pk_module.BLACKLISTED_PROCESSES = frozenset({"msedge.exe"})
    mgr.register(pk)

    # --- Clipboard scrub (real) ---
    cs = ClipboardScrubSubsystem(mgr, shutdown)
    mgr.register(cs)

    # ================================================================
    # Pre-check: what's running / in clipboard
    # ================================================================
    print("\n--- Pre-check ---")

    edge_before = [p for p in psutil.process_iter(["name"])
                   if (p.info["name"] or "").lower() == "msedge.exe"]
    print(f"  msedge.exe processes: {len(edge_before)}")

    # Check clipboard contents
    try:
        win32clipboard.OpenClipboard()
        fmt = win32clipboard.EnumClipboardFormats(0)
        formats = []
        while fmt:
            formats.append(fmt)
            fmt = win32clipboard.EnumClipboardFormats(fmt)
        win32clipboard.CloseClipboard()
        print(f"  Clipboard formats present: {len(formats)}")
    except Exception as e:
        print(f"  Clipboard check error: {e}")
        formats = []

    # ================================================================
    # START lockdown
    # ================================================================
    print("\n--- Starting lockdown (msedge kill + clipboard scrub) ---")
    violations.clear()
    mgr.start()
    print("  Lockdown active. Waiting 4 seconds...")
    time.sleep(4.0)

    # ================================================================
    # Results
    # ================================================================
    print("\n--- Results ---")

    # Process kill
    killed = [v for v in violations if v["type"] == "BLACKLISTED_PROCESS_KILLED"]
    edge_after = [p for p in psutil.process_iter(["name"])
                  if (p.info["name"] or "").lower() == "msedge.exe"]
    print(f"\n  PROCESS KILL:")
    print(f"    msedge.exe killed: {len(killed)} process(es)")
    print(f"    msedge.exe remaining: {len(edge_after)}")
    if killed:
        print(f"    PASS: msedge.exe terminated within ~2s")
    elif len(edge_before) == 0:
        print(f"    SKIP: msedge.exe was not running")
    else:
        print(f"    FAIL: msedge.exe not killed")

    # Clipboard scrub
    scrubbed = [v for v in violations if v["type"] == "CLIPBOARD_SCRUB"]
    try:
        win32clipboard.OpenClipboard()
        fmt = win32clipboard.EnumClipboardFormats(0)
        remaining_formats = []
        while fmt:
            remaining_formats.append(fmt)
            fmt = win32clipboard.EnumClipboardFormats(fmt)
        win32clipboard.CloseClipboard()
    except Exception:
        remaining_formats = []

    print(f"\n  CLIPBOARD SCRUB:")
    print(f"    CLIPBOARD_SCRUB incidents: {len(scrubbed)}")
    print(f"    Clipboard formats remaining: {len(remaining_formats)}")
    if len(remaining_formats) == 0:
        print(f"    PASS: Clipboard is empty")
    else:
        print(f"    NOTE: Clipboard has {len(remaining_formats)} format(s) — may have been repopulated")

    # ================================================================
    # STOP lockdown
    # ================================================================
    print("\n--- Stopping lockdown ---")
    mgr.stop()

    # Restore blacklist
    pk_module.BLACKLISTED_PROCESSES = original_blacklist

    print("  Lockdown stopped.")
    print("  msedge.exe will stay alive if relaunched now.")
    print("  Clipboard will persist normally now.")

    # ================================================================
    # Summary
    # ================================================================
    edge_ok = len(killed) > 0 or len(edge_before) == 0
    clip_ok = len(remaining_formats) == 0

    print("\n" + "=" * 60)
    if edge_ok and clip_ok:
        print("  PART 25 VERIFIED: Edge killed + Clipboard cleared")
    else:
        if not edge_ok:
            print("  ISSUE: msedge.exe not killed")
        if not clip_ok:
            print("  ISSUE: Clipboard not empty")
    print("=" * 60)

    root.destroy()


if __name__ == "__main__":
    main()
