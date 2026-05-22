"""Process Kill subsystem — kills blacklisted processes during exams.

Background thread polls psutil.process_iter every 2 seconds. Any process
whose executable basename matches the blacklist is terminated (then killed
if still alive after 200ms). Posts BLACKLISTED_PROCESS_KILLED with severity
critical. Throttle: one incident per (process_name, pid) pair.

Cross-version: psutil works identically on Windows 10 and 11.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Set, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Blacklist — module-level constant for Part 30 docs reference
# ---------------------------------------------------------------------------

BLACKLISTED_PROCESSES: frozenset[str] = frozenset({
    # Browsers
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe",
    # Code editors / IDEs
    "code.exe", "cursor.exe", "windsurf.exe",
    "sublime_text.exe", "notepad++.exe",
    # Messaging
    "discord.exe", "telegram.exe", "whatsapp.exe",
    "signal.exe", "slack.exe",
    # Video / conferencing
    "zoom.exe", "teams.exe", "skype.exe",
    # Remote desktop
    "anydesk.exe", "teamviewer.exe", "ultraviewer.exe",
    "rustdesk.exe", "parsec.exe",
    # Screen capture
    "snippingtool.exe", "screenclip.exe",
    "snagiteditor.exe", "snagit32.exe",
    "obs64.exe", "obs32.exe", "sharex.exe",
    "screenrec.exe", "lightshot.exe",
    # System tools
    "cmd.exe", "powershell.exe", "pwsh.exe", "wt.exe",
    "taskmgr.exe", "regedit.exe", "msconfig.exe",
})


class ProcessKillSubsystem:
    """Kills blacklisted processes on a background polling thread."""

    def __init__(self, manager: Any, shutdown_event: threading.Event) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._started = False
        self._thread: threading.Thread | None = None
        # Throttle: set of (lowercase_name, pid) already reported
        self._reported: Set[Tuple[str, int]] = set()

    @property
    def name(self) -> str:
        return "process_kill"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True
        self._thread = threading.Thread(
            target=self._poll_loop, name="process_kill_thread", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None

    # -- polling loop -------------------------------------------------------

    def _poll_loop(self) -> None:
        try:
            import psutil
        except ImportError:
            logger.error("psutil not available — process kill subsystem disabled")
            self._started = False
            return

        while not self._shutdown_event.is_set():
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    if self._shutdown_event.is_set():
                        break
                    try:
                        pname = (proc.info["name"] or "").lower()
                        pid = proc.info["pid"]

                        if pname not in BLACKLISTED_PROCESSES:
                            continue

                        key = (pname, pid)
                        if key in self._reported:
                            continue

                        # Kill it
                        try:
                            proc.terminate()
                            proc.wait(timeout=0.2)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass

                        self._reported.add(key)
                        self._manager.report(
                            "BLACKLISTED_PROCESS_KILLED",
                            "critical",
                            f"Killed {pname} (PID {pid})",
                            subsystem_name=self.name,
                            process_name=pname,
                            process_pid=pid,
                        )
                        logger.info(f"Killed blacklisted process: {pname} (PID {pid})")

                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            except Exception as e:
                logger.debug(f"Process scan error: {e}")

            # Poll every 2 seconds
            self._shutdown_event.wait(timeout=2.0)


__all__ = ["ProcessKillSubsystem", "BLACKLISTED_PROCESSES"]
