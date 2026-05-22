"""Controlled vocabulary for ``IncidentLog.incident_type``.

The desktop client and the server both validate against this single
vocabulary. Adding a new incident kind means appending here, never
inventing strings ad-hoc at the call site.

The ``IncidentSeverity`` constants are mirrored on the model layer as a
SQLAlchemy enum (see ``app.models.enums``); this module only owns the
free-form ``incident_type`` string vocabulary.
"""

from __future__ import annotations

from typing import Final, FrozenSet, Tuple


# --- Lockdown / focus violations ----------------------------------------
FOCUS_LOST: Final[str] = "FOCUS_LOST"
BLACKLISTED_PROCESS_KILLED: Final[str] = "BLACKLISTED_PROCESS_KILLED"
CLIPBOARD_SCRUB: Final[str] = "CLIPBOARD_SCRUB"
KEYBOARD_BLOCKED: Final[str] = "KEYBOARD_BLOCKED"
MULTI_MONITOR_DETECTED: Final[str] = "MULTI_MONITOR_DETECTED"
FULLSCREEN_BREACH: Final[str] = "FULLSCREEN_BREACH"
MOUSE_ESCAPE: Final[str] = "MOUSE_ESCAPE"
LOCKDOWN_VIOLATION: Final[str] = "LOCKDOWN_VIOLATION"

# --- VM / virtualisation evidence ---------------------------------------
VM_DETECTED: Final[str] = "VM_DETECTED"
STEALTH_VM_DETECTED: Final[str] = "STEALTH_VM_DETECTED"
TIMING_ANOMALY: Final[str] = "TIMING_ANOMALY"
THERMAL_ANOMALY: Final[str] = "THERMAL_ANOMALY"

# --- Lockdown lifecycle events ------------------------------------------
LOCKDOWN_ENGAGED: Final[str] = "LOCKDOWN_ENGAGED"
LOCKDOWN_DISENGAGED: Final[str] = "LOCKDOWN_DISENGAGED"
STARTUP_PARTIAL_FAILURE: Final[str] = "STARTUP_PARTIAL_FAILURE"
KEYBOARD_HOOK_UNAVAILABLE: Final[str] = "KEYBOARD_HOOK_UNAVAILABLE"
RIGHT_CLICK_BLOCKED: Final[str] = "RIGHT_CLICK_BLOCKED"

# --- Submission / lifecycle ---------------------------------------------
LATE_SUBMIT: Final[str] = "LATE_SUBMIT"
NETWORK_DROP: Final[str] = "NETWORK_DROP"


# Canonical, ordered list. Iteration order is stable so callers can use it
# to drive UI menus / OpenAPI enum descriptions without sorting drift.
ALL_INCIDENT_TYPES: Final[Tuple[str, ...]] = (
    FOCUS_LOST,
    BLACKLISTED_PROCESS_KILLED,
    CLIPBOARD_SCRUB,
    KEYBOARD_BLOCKED,
    MULTI_MONITOR_DETECTED,
    FULLSCREEN_BREACH,
    MOUSE_ESCAPE,
    LOCKDOWN_VIOLATION,
    LOCKDOWN_ENGAGED,
    LOCKDOWN_DISENGAGED,
    STARTUP_PARTIAL_FAILURE,
    KEYBOARD_HOOK_UNAVAILABLE,
    RIGHT_CLICK_BLOCKED,
    VM_DETECTED,
    STEALTH_VM_DETECTED,
    TIMING_ANOMALY,
    THERMAL_ANOMALY,
    LATE_SUBMIT,
    NETWORK_DROP,
)

# Set form for O(1) membership checks in validators.
INCIDENT_TYPE_SET: Final[FrozenSet[str]] = frozenset(ALL_INCIDENT_TYPES)


def is_valid_incident_type(value: str) -> bool:
    """Return True if ``value`` is a recognised incident type string."""
    return value in INCIDENT_TYPE_SET


__all__ = [
    "FOCUS_LOST",
    "BLACKLISTED_PROCESS_KILLED",
    "CLIPBOARD_SCRUB",
    "KEYBOARD_BLOCKED",
    "MULTI_MONITOR_DETECTED",
    "FULLSCREEN_BREACH",
    "MOUSE_ESCAPE",
    "LOCKDOWN_VIOLATION",
    "LOCKDOWN_ENGAGED",
    "LOCKDOWN_DISENGAGED",
    "STARTUP_PARTIAL_FAILURE",
    "KEYBOARD_HOOK_UNAVAILABLE",
    "RIGHT_CLICK_BLOCKED",
    "VM_DETECTED",
    "STEALTH_VM_DETECTED",
    "TIMING_ANOMALY",
    "THERMAL_ANOMALY",
    "LATE_SUBMIT",
    "NETWORK_DROP",
    "ALL_INCIDENT_TYPES",
    "INCIDENT_TYPE_SET",
    "is_valid_incident_type",
]
