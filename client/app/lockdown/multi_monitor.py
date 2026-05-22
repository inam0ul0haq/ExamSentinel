"""Multi-Monitor subsystem — detects and blocks multi-monitor setups.

On start: counts monitors. If more than one, posts MULTI_MONITOR_DETECTED
with severity critical and triggers request_abort on the manager.

A background thread re-checks every 3 seconds to catch hot-plugged monitors.

Uses screeninfo.get_monitors() with ctypes EnumDisplayMonitors fallback.

Cross-version: EnumDisplayMonitors is stable across Windows 10 and 11.
"""

from __future__ import annotations

import ctypes
import logging
import platform
import threading
import time
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def _count_monitors() -> int:
    """Count the number of connected monitors."""
    # Try screeninfo first
    try:
        from screeninfo import get_monitors
        return len(get_monitors())
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"screeninfo failed: {e}")

    # Fallback: ctypes EnumDisplayMonitors
    if platform.system() == "Windows":
        try:
            monitors: List[Any] = []

            def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                monitors.append(hMonitor)
                return True

            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_ulong,
                ctypes.c_ulong,
                ctypes.POINTER(ctypes.wintypes.RECT),
                ctypes.c_double,
            )
            ctypes.windll.user32.EnumDisplayMonitors(
                None, None, MONITORENUMPROC(callback), 0
            )
            return len(monitors)
        except Exception as e:
            logger.debug(f"EnumDisplayMonitors fallback failed: {e}")

    return 1  # Assume single monitor if detection fails


class MultiMonitorSubsystem:
    """Detects multi-monitor setups and triggers exam abort."""

    def __init__(
        self,
        manager: Any,
        shutdown_event: threading.Event,
    ) -> None:
        self._manager = manager
        self._shutdown_event = shutdown_event
        self._started = False
        self._thread: Optional[threading.Thread] = None
        self._aborted = False

    @property
    def name(self) -> str:
        return "multi_monitor"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True

        # Initial check
        count = _count_monitors()
        if count > 1:
            self._trigger_abort(count)
            return

        # Start background polling thread
        self._thread = threading.Thread(
            target=self._monitor_loop,
            name="multi_monitor_thread",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._started = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _monitor_loop(self) -> None:
        while not self._shutdown_event.is_set() and self._started:
            try:
                count = _count_monitors()
                if count > 1 and not self._aborted:
                    self._trigger_abort(count)
            except Exception as e:
                logger.debug(f"Monitor check error: {e}")

            self._shutdown_event.wait(timeout=3.0)

    def _trigger_abort(self, count: int) -> None:
        self._aborted = True
        self._manager.report(
            "MULTI_MONITOR_DETECTED",
            "critical",
            f"Multiple monitors detected ({count}). Exam will be aborted.",
            subsystem_name=self.name,
            monitor_count=count,
        )
        # Signal the manager to abort the exam
        self._manager.request_abort("multi_monitor")


__all__ = ["MultiMonitorSubsystem"]
