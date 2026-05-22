"""Clipboard scrub real-time demo."""

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import tkinter as tk
import win32clipboard as cb

from client.app.lockdown.manager import LockdownManager
from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem


def report_v(t, s, d="", **kw):
    print(f"  [INCIDENT] {t} ({s}): {d}")


def get_clip():
    try:
        cb.OpenClipboard()
        try:
            data = cb.GetClipboardData()
            return repr(data)
        except Exception:
            return "<EMPTY>"
        finally:
            cb.CloseClipboard()
    except Exception:
        return "<locked>"


def set_clip(text):
    cb.OpenClipboard()
    cb.EmptyClipboard()
    cb.SetClipboardText(text)
    cb.CloseClipboard()


def main():
    root = tk.Tk()
    root.withdraw()
    shutdown = threading.Event()
    mgr = LockdownManager(root, report_v, shutdown_event=shutdown)
    cs = ClipboardScrubSubsystem(mgr, shutdown)
    mgr.register(cs)

    print("=" * 50)
    print("Step 1: Put 'EXAM CHEAT NOTES' in clipboard")
    print("=" * 50)
    set_clip("EXAM CHEAT NOTES")
    print(f"  Clipboard now: {get_clip()}")

    print("\n" + "=" * 50)
    print("Step 2: START clipboard scrub")
    print("=" * 50)
    mgr.start()
    time.sleep(1.0)

    print(f"  Clipboard after 1s: {get_clip()}")

    print("\n" + "=" * 50)
    print("Step 3: Try putting text again while scrub active")
    print("=" * 50)
    set_clip("TRY AGAIN")
    print(f"  Clipboard immediately: {get_clip()}")
    time.sleep(0.6)
    print(f"  Clipboard after 600ms: {get_clip()}")

    print("\n" + "=" * 50)
    print("Step 4: STOP clipboard scrub")
    print("=" * 50)
    mgr.stop()

    print("\n" + "=" * 50)
    print("Step 5: Put text AFTER stop — should PERSIST")
    print("=" * 50)
    set_clip("This text stays forever")
    time.sleep(1.0)
    print(f"  Clipboard after 1s: {get_clip()}")

    print("\n" + "=" * 50)
    print("DONE — clipboard is yours again")
    print("=" * 50)

    root.destroy()


if __name__ == "__main__":
    main()
