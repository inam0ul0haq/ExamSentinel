"""Lockdown Manager — central coordinator for all exam lockdown subsystems.

Windows-targeted. Refuses to start on non-Windows platforms.

The manager owns an ordered list of subsystem objects, each implementing the
subsystem protocol:
    - name: str          (human-readable subsystem name)
    - start() -> None    (activate; may raise)
    - stop() -> None     (deactivate; idempotent)
    - is_started: bool   (current state)

Lifecycle contract:
    - start() invokes each subsystem's start() in order.
    - stop() invokes each subsystem's stop() in reverse order.
    - stop() MUST be called under ALL circumstances (submit, expire, cancel,
      window close, unhandled exception).
    - stop() is idempotent — calling twice is safe.

Threading model:
    - A shared threading.Event (shutdown_event) is passed to all subsystems.
    - Subsystems use daemon threads and poll shutdown_event for clean exit.

Violation pipeline:
    - Subsystems call manager.report(type, severity, description, **forensics)
    - Manager attaches subsystem metadata and forwards to the incident
      pipeline (or a direct callback fallback).

Subsystem registration order (startup):
    1. MultiMonitorSubsystem    — abort early before going fullscreen
    2. KeyboardLockdown          — block keys before fullscreen
    3. ProcessKillSubsystem      — kill blacklisted apps
    4. ClipboardScrubSubsystem   — clear clipboard
    5. RightClickSuppressSubsystem — bind right-click handlers
    6. FullscreenSubsystem       — go fullscreen + hide taskbar
    7. FocusMonitorSubsystem     — monitor focus
    8. MouseBoundarySubsystem    — clip cursor last (after fullscreen)

Shutdown order is reversed (mouse released before fullscreen reverts).
"""

from __future__ import annotations

import logging
import platform
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Protocol

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Subsystem protocol
# ---------------------------------------------------------------------------

class LockdownSubsystem(Protocol):
    """Protocol that every lockdown subsystem must implement."""

    @property
    def name(self) -> str: ...

    @property
    def is_started(self) -> bool: ...

    def start(self) -> None: ...

    def stop(self) -> None: ...


# ---------------------------------------------------------------------------
# LockdownManager
# ---------------------------------------------------------------------------

class LockdownManager:
    """Central coordinator for all lockdown subsystems.

    Parameters
    ----------
    window : tk.Tk
        The Tk root window (exam taking screen's top-level).
    report_violation : callable
        Callback with signature (type, severity, description, **forensics).
        Used for direct incident posting (lifecycle events).
    shutdown_event : threading.Event, optional
        Shared event for signalling shutdown to subsystems.
        If not provided, a new Event is created.
    """

    def __init__(
        self,
        window: tk.Tk,
        report_violation: Callable[..., Any],
        shutdown_event: Optional[threading.Event] = None,
    ) -> None:
        self._window = window
        self._report_violation = report_violation
        self._shutdown_event = shutdown_event or threading.Event()
        self._subsystems: List[Any] = []
        self._active = False
        self._stopped = False  # idempotency flag

        # Track failed subsystems
        self._failed_subsystems: List[str] = []

        # Abort callback — registered by the exam screen at start time
        self._abort_callback: Optional[Callable[[str], Any]] = None

        # Save original handlers for restoration
        self._orig_excepthook: Optional[Any] = None
        self._orig_tk_report_callback_exception: Optional[Any] = None

    # -- Registration -------------------------------------------------------

    def register(self, subsystem: Any) -> None:
        """Register a subsystem. Must be called before start()."""
        self._subsystems.append(subsystem)

    def register_all(
        self,
        window: tk.Tk,
        shutdown_event: threading.Event,
    ) -> None:
        """Register all subsystems in the canonical fixed order.

        Order matters:
        - MultiMonitor first: abort before going fullscreen
        - MouseBoundary last: clip after fullscreen is sized
        - Reverse for shutdown
        """
        from client.app.lockdown.clipboard_scrub import ClipboardScrubSubsystem
        from client.app.lockdown.focus_monitor import FocusMonitorSubsystem
        from client.app.lockdown.fullscreen import FullscreenSubsystem
        from client.app.lockdown.keyboard import KeyboardLockdown
        from client.app.lockdown.mouse_boundary import MouseBoundarySubsystem
        from client.app.lockdown.multi_monitor import MultiMonitorSubsystem
        from client.app.lockdown.process_kill import ProcessKillSubsystem
        from client.app.lockdown.right_click_suppress import RightClickSuppressSubsystem

        self.register(MultiMonitorSubsystem(self, shutdown_event))
        self.register(KeyboardLockdown(self, shutdown_event))
        self.register(ProcessKillSubsystem(self, shutdown_event))
        self.register(ClipboardScrubSubsystem(self, shutdown_event))
        self._right_click_sub = RightClickSuppressSubsystem(self, window)
        self.register(self._right_click_sub)
        self.register(FullscreenSubsystem(self, shutdown_event, window))
        self.register(FocusMonitorSubsystem(self, shutdown_event, window))
        self.register(MouseBoundarySubsystem(self, shutdown_event, window))

    def set_abort_callback(self, callback: Callable[[str], Any]) -> None:
        """Register an abort callback from the exam screen.

        The callback receives a reason string and should handle:
        stopping the timer, force-submitting or aborting the session,
        stopping the manager, and navigating to the dashboard.
        """
        self._abort_callback = callback

    def request_abort(self, reason: str) -> None:
        """Request an exam abort from a subsystem.

        Triggers the callback registered by the exam screen.
        """
        logger.warning(f"Abort requested by subsystem: {reason}")
        if self._abort_callback:
            try:
                self._abort_callback(reason)
            except Exception as e:
                logger.error(f"Abort callback failed: {e}")

    # -- Properties ---------------------------------------------------------

    @property
    def is_active(self) -> bool:
        """True if the lockdown is currently engaged."""
        return self._active

    @property
    def shutdown_event(self) -> threading.Event:
        """Shared shutdown event for subsystems."""
        return self._shutdown_event

    # -- Start --------------------------------------------------------------

    def start(self) -> None:
        """Start all registered subsystems.

        On non-Windows, logs a warning and posts LOCKDOWN_ENGAGED with an
        empty subsystem list (no-op mode for dev/testing).
        """
        if self._active:
            return

        if platform.system() != "Windows":
            logger.warning(
                "LockdownManager: non-Windows platform detected. "
                "Lockdown subsystems will NOT activate."
            )
            self._active = True
            self._report_violation(
                "LOCKDOWN_ENGAGED",
                "info",
                "Lockdown engaged (non-Windows — no subsystems active).",
            )
            self._install_exception_handlers()
            return

        # Install crash handlers BEFORE starting subsystems
        self._install_exception_handlers()

        active_names: List[str] = []
        self._failed_subsystems = []

        for sub in self._subsystems:
            try:
                sub.start()
                active_names.append(sub.name)
                logger.info(f"Lockdown subsystem started: {sub.name}")
            except Exception as e:
                self._failed_subsystems.append(sub.name)
                logger.error(
                    f"Lockdown subsystem FAILED to start: {sub.name} — {e}",
                    exc_info=True,
                )

        # Report partial failure if any subsystem failed
        if self._failed_subsystems:
            self._report_violation(
                "STARTUP_PARTIAL_FAILURE",
                "warning",
                f"Failed subsystems: {', '.join(self._failed_subsystems)}",
                failed_subsystems=self._failed_subsystems,
                active_subsystems=active_names,
            )

        self._active = True

        # Post LOCKDOWN_ENGAGED
        self._report_violation(
            "LOCKDOWN_ENGAGED",
            "info",
            f"Lockdown engaged. Active subsystems: {', '.join(active_names) or 'none'}.",
            active_subsystems=active_names,
            failed_subsystems=self._failed_subsystems,
        )

        logger.info(
            f"LockdownManager started. Active: {active_names}, "
            f"Failed: {self._failed_subsystems}"
        )

    # -- Stop ---------------------------------------------------------------

    def stop(self) -> None:
        """Stop all subsystems in reverse order. Idempotent.

        Posts LOCKDOWN_DISENGAGED on the first call. Second call is a no-op.
        """
        if self._stopped:
            return
        self._stopped = True

        # Signal shutdown to all subsystem threads
        self._shutdown_event.set()

        # Stop subsystems in reverse order
        for sub in reversed(self._subsystems):
            try:
                sub.stop()
                logger.info(f"Lockdown subsystem stopped: {sub.name}")
            except Exception as e:
                logger.error(
                    f"Lockdown subsystem FAILED to stop: {sub.name} — {e}",
                    exc_info=True,
                )

        self._active = False

        # Post LOCKDOWN_DISENGAGED
        try:
            self._report_violation(
                "LOCKDOWN_DISENGAGED",
                "info",
                "Lockdown disengaged. All subsystems stopped.",
            )
        except Exception:
            # If reporting fails during shutdown, just log it
            logger.error("Failed to post LOCKDOWN_DISENGAGED incident")

        # Restore original exception handlers
        self._restore_exception_handlers()

        logger.info("LockdownManager stopped.")

    # -- Violation pipeline -------------------------------------------------

    def report(
        self,
        incident_type: str,
        severity: str,
        description: str = "",
        *,
        subsystem_name: str = "",
        **forensics: Any,
    ) -> None:
        """Report a violation from a subsystem.

        Attaches subsystem metadata and forwards to the screen's
        report_violation callable.
        """
        # Attach metadata
        forensics["subsystem"] = subsystem_name
        forensics["occurred_at_local"] = datetime.now(timezone.utc).isoformat()

        try:
            self._report_violation(
                incident_type, severity, description, **forensics
            )
        except Exception as e:
            logger.error(f"Violation report failed: {e}")

    # -- Exception handlers (double-belt approach) --------------------------

    def _install_exception_handlers(self) -> None:
        """Install sys.excepthook and Tk report_callback_exception overrides."""
        # Save originals
        self._orig_excepthook = sys.excepthook
        self._orig_tk_report_callback_exception = getattr(
            self._window, "report_callback_exception", None
        )

        # Install our handlers
        sys.excepthook = self._on_unhandled_exception
        self._window.report_callback_exception = self._on_tk_exception

    def _restore_exception_handlers(self) -> None:
        """Restore original exception handlers."""
        if self._orig_excepthook is not None:
            sys.excepthook = self._orig_excepthook
            self._orig_excepthook = None

        if self._orig_tk_report_callback_exception is not None:
            self._window.report_callback_exception = (
                self._orig_tk_report_callback_exception
            )
            self._orig_tk_report_callback_exception = None

    def _on_unhandled_exception(
        self, exc_type: type, exc_value: BaseException, exc_tb: Any
    ) -> None:
        """sys.excepthook override — ensures lockdown stops on crash."""
        logger.critical(
            f"Unhandled exception caught by LockdownManager: {exc_value}",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        self.stop()

        # Call original handler
        if self._orig_excepthook and self._orig_excepthook is not sys.excepthook:
            self._orig_excepthook(exc_type, exc_value, exc_tb)

    def _on_tk_exception(self, exc_type: type, exc_value: BaseException, exc_tb: Any) -> None:
        """Tk report_callback_exception override — ensures lockdown stops on Tk errors."""
        logger.critical(
            f"Tk exception caught by LockdownManager: {exc_value}",
            exc_info=(exc_type, exc_value, exc_tb),
        )
        self.stop()

        # Call original handler
        if self._orig_tk_report_callback_exception:
            self._orig_tk_report_callback_exception(exc_type, exc_value, exc_tb)


__all__ = ["LockdownManager", "LockdownSubsystem"]
