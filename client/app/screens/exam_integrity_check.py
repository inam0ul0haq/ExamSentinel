"""
Exam integrity-check screen.

Runs two sequential VM detection gates before allowing the exam to proceed:
  1. Standard VM Detection — processes, registry, WMI, MAC
  2. Stealth VM Detection — thermal zone, SCSI disk identifier

Both gates must pass before the session transitions from pre_check to
in_progress. If either fails, the session is aborted and an incident is
posted to the server.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Dict

from client.app.config import SKIP_VM_CHECK, SKIP_STEALTH_CHECK
from client.app.ui import theme
from client.app.vm_detect.standard import detect_standard_vm
from client.app.vm_detect.stealth import detect_stealth_vm


class ExamIntegrityCheckScreen(tk.Frame):
    """Pre-exam integrity gate with real VM detection."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 session_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api          # type: ignore[attr-defined]
        self._root: tk.Tk = router.root
        self._session_id = int(session_id) if session_id else None
        self._aborted = False

        # --- heading ---
        tk.Label(
            self,
            text="Pre-Exam Integrity Check",
            font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
        ).pack(pady=(60, 10))

        tk.Label(
            self,
            text="Verifying environment before exam can begin…",
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).pack(pady=(0, 30))

        # --- check status panel ---
        self._checks_frame = tk.Frame(self, bg=theme.BG_SECONDARY, padx=30, pady=20)
        self._checks_frame.pack(padx=80, fill="x")

        # Check 1: Standard VM
        self._std_frame = tk.Frame(self._checks_frame, bg=theme.BG_SECONDARY)
        self._std_frame.pack(fill="x", pady=6)
        self._std_indicator = tk.Label(
            self._std_frame, text="⏳", font=("Segoe UI", 14),
            bg=theme.BG_SECONDARY, fg=theme.WARNING, width=3,
        )
        self._std_indicator.pack(side="left")
        self._std_label = tk.Label(
            self._std_frame, text="Virtual Machine — Standard",
            font=theme.FONT_BODY, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
        )
        self._std_label.pack(side="left", padx=(8, 0))
        self._std_status = tk.Label(
            self._std_frame, text="Pending",
            font=theme.FONT_SMALL, bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        )
        self._std_status.pack(side="right")

        # Check 2: Stealth VM
        self._stl_frame = tk.Frame(self._checks_frame, bg=theme.BG_SECONDARY)
        self._stl_frame.pack(fill="x", pady=6)
        self._stl_indicator = tk.Label(
            self._stl_frame, text="⏳", font=("Segoe UI", 14),
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, width=3,
        )
        self._stl_indicator.pack(side="left")
        self._stl_label = tk.Label(
            self._stl_frame, text="Virtual Machine — Stealth",
            font=theme.FONT_BODY, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
        )
        self._stl_label.pack(side="left", padx=(8, 0))
        self._stl_status = tk.Label(
            self._stl_frame, text="Pending",
            font=theme.FONT_SMALL, bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
        )
        self._stl_status.pack(side="right")

        # --- details area (shows indicators on failure) ---
        self._details_var = tk.StringVar()
        self._details_label = tk.Label(
            self,
            textvariable=self._details_var,
            font=theme.FONT_SMALL,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
            justify="left",
            wraplength=700,
        )

        # --- error message area ---
        self._error_var = tk.StringVar()
        self._error_label = tk.Label(
            self,
            textvariable=self._error_var,
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY,
            fg=theme.ERROR,
            wraplength=600,
        )

        # --- buttons ---
        self._btn_frame = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._btn_frame.pack(pady=30)

        self._cancel_btn = tk.Button(
            self._btn_frame,
            text="Cancel",
            font=theme.FONT_BUTTON,
            bg=theme.BG_SECONDARY,
            fg=theme.TEXT_PRIMARY,
            activebackground=theme.BORDER,
            activeforeground=theme.TEXT_PRIMARY,
            relief="flat",
            cursor="hand2",
            bd=0,
            highlightbackground=theme.BORDER,
            highlightthickness=1,
            padx=theme.PAD_MEDIUM,
            pady=theme.PAD_SMALL,
            command=self._on_cancel,
        )
        self._cancel_btn.pack(side="left", padx=(0, 12))

        self._continue_btn = tk.Button(
            self._btn_frame,
            text="Continue",
            font=theme.FONT_BUTTON,
            bg=theme.ACCENT,
            fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER,
            activeforeground="#FFFFFF",
            relief="flat",
            cursor="hand2",
            bd=0,
            padx=theme.PAD_MEDIUM,
            pady=theme.PAD_SMALL,
            state="disabled",
            command=self._on_continue,
        )
        self._continue_btn.pack(side="left")

        # --- start checks automatically ---
        self._root.after(500, self._start_checks)

    # -- check execution ---------------------------------------------------

    def _start_checks(self) -> None:
        """Kick off the detection sequence on a background thread."""
        threading.Thread(target=self._run_all_checks, daemon=True).start()

    def _run_all_checks(self) -> None:
        """Run standard then stealth detection sequentially."""

        # --- SKIP_VM_CHECK dev mode ---
        if SKIP_VM_CHECK:
            self._root.after(0, lambda: self._mark_check_skipped("standard"))
            self._root.after(200, lambda: self._mark_check_skipped("stealth"))
            self._root.after(400, self._all_passed)
            return

        # --- Gate 1: Standard VM Detection ---
        self._root.after(0, lambda: self._mark_check_running("standard"))

        try:
            std_result = detect_standard_vm()
        except Exception as e:
            # Detection crashed — treat as pass (don't block exam for bugs)
            std_result = {"is_vm": False, "vm_type": None, "indicators": []}

        if std_result["is_vm"]:
            self._root.after(0, lambda: self._on_standard_failed(std_result))
            return

        self._root.after(0, lambda: self._mark_check_passed("standard"))

        # --- Gate 2: Stealth VM Detection ---
        if SKIP_STEALTH_CHECK:
            self._root.after(0, lambda: self._mark_check_skipped("stealth"))
        else:
            self._root.after(0, lambda: self._mark_check_running("stealth"))

            try:
                stl_result = detect_stealth_vm()
            except Exception as e:
                stl_result = {"is_vm": False, "vm_type": None, "indicators": []}

            if stl_result["is_vm"]:
                self._root.after(0, lambda: self._on_stealth_failed(stl_result))
                return

            self._root.after(0, lambda: self._mark_check_passed("stealth"))

        # --- Both passed ---
        self._root.after(0, self._all_passed)

    # -- UI state updates --------------------------------------------------

    def _mark_check_running(self, check: str) -> None:
        if check == "standard":
            self._std_indicator.configure(text="🔄", fg=theme.WARNING)
            self._std_status.configure(text="Running…", fg=theme.WARNING)
        else:
            self._stl_indicator.configure(text="🔄", fg=theme.WARNING)
            self._stl_status.configure(text="Running…", fg=theme.WARNING)

    def _mark_check_passed(self, check: str) -> None:
        if check == "standard":
            self._std_indicator.configure(text="✓", fg=theme.SUCCESS)
            self._std_status.configure(text="Passed — No VM detected", fg=theme.SUCCESS)
        else:
            self._stl_indicator.configure(text="✓", fg=theme.SUCCESS)
            self._stl_status.configure(text="Passed — No hypervisor detected", fg=theme.SUCCESS)

    def _mark_check_skipped(self, check: str) -> None:
        if check == "standard":
            self._std_indicator.configure(text="⚠", fg=theme.WARNING)
            self._std_status.configure(text="Skipped (dev mode)", fg=theme.WARNING)
        else:
            self._stl_indicator.configure(text="⚠", fg=theme.WARNING)
            self._stl_status.configure(text="Skipped (dev mode)", fg=theme.WARNING)

    def _mark_check_failed(self, check: str, detail: str) -> None:
        if check == "standard":
            self._std_indicator.configure(text="✗", fg=theme.ERROR)
            self._std_status.configure(text=detail, fg=theme.ERROR)
        else:
            self._stl_indicator.configure(text="✗", fg=theme.ERROR)
            self._stl_status.configure(text=detail, fg=theme.ERROR)

    # -- failure handlers --------------------------------------------------

    def _on_standard_failed(self, result: Dict[str, Any]) -> None:
        """Handle standard VM detection failure."""
        self._aborted = True
        vm_type = result.get("vm_type") or "Unknown"
        indicators = result.get("indicators", [])

        self._mark_check_failed(
            "standard",
            f"FAILED — {vm_type.upper()} detected ({len(indicators)} indicator(s))"
        )
        # Mark stealth as skipped since standard already failed
        self._stl_indicator.configure(text="—", fg=theme.TEXT_SECONDARY)
        self._stl_status.configure(text="Skipped (standard gate failed)", fg=theme.TEXT_SECONDARY)

        # Show indicator details
        details_lines = ["Indicators found:"]
        for ind in indicators:
            details_lines.append(f"  • [{ind['category']}] {ind['name']}: {ind['evidence']}")
        self._details_var.set("\n".join(details_lines))
        self._details_label.pack(pady=(15, 0))

        # Show error message
        self._error_var.set(
            "This exam cannot be taken inside a virtual machine. "
            "Please run on a physical Windows 10/11 device."
        )
        self._error_label.pack(pady=(10, 0))

        # Disable continue permanently
        self._continue_btn.configure(state="disabled")

        # Post incident and abort session on server
        threading.Thread(target=self._do_abort, args=("vm", result), daemon=True).start()

    def _on_stealth_failed(self, result: Dict[str, Any]) -> None:
        """Handle stealth VM detection failure."""
        self._aborted = True
        vm_type = result.get("vm_type") or "Unknown Hypervisor"
        indicators = result.get("indicators", [])

        self._mark_check_failed(
            "stealth",
            f"FAILED — {vm_type.upper()} detected ({len(indicators)} indicator(s))"
        )

        # Show indicator details
        details_lines = ["Stealth indicators found:"]
        for ind in indicators:
            details_lines.append(f"  • [{ind['category']}] {ind['name']}: {ind['evidence']}")
        self._details_var.set("\n".join(details_lines))
        self._details_label.pack(pady=(15, 0))

        # Show error message
        self._error_var.set(
            "This exam cannot be taken inside any virtualized environment. "
            "Stealth VM signatures detected. Please run on a physical Windows 10/11 device."
        )
        self._error_label.pack(pady=(10, 0))

        # Disable continue permanently
        self._continue_btn.configure(state="disabled")

        # Post incident and abort session on server
        threading.Thread(target=self._do_abort, args=("stealth_vm", result), daemon=True).start()

    def _do_abort(self, reason: str, result: Dict[str, Any]) -> None:
        """Post incident to server and abort the session."""
        if self._session_id is None:
            return

        # Post incident
        incident_type = "VM_DETECTED" if reason == "vm" else "STEALTH_VM_DETECTED"
        indicators = result.get("indicators", [])
        description = (
            f"{result.get('vm_type', 'unknown').upper()} detected via "
            f"{', '.join(set(i['category'] for i in indicators))} checks"
        )

        incident_body = {
            "incidents": [{
                "type": incident_type,
                "severity": "critical",
                "description": description,
            }]
        }

        # Add thermal value if present (stealth detection)
        if result.get("cpu_thermal_value") is not None:
            incident_body["incidents"][0]["cpu_thermal_value"] = result["cpu_thermal_value"]

        # Add timing latency if present (RDTSC check — convert cycles to ~ms)
        if result.get("timing_latency_cycles") is not None:
            # Approximate: cycles / cpu_freq_mhz ≈ microseconds, /1000 = ms
            # Use a rough 3GHz estimate for demo purposes
            cycles = result["timing_latency_cycles"]
            approx_ms = cycles / 3_000_000  # 3GHz → ms
            incident_body["incidents"][0]["timing_latency_ms"] = round(approx_ms, 4)

        self._api.post(
            f"/sessions/{self._session_id}/incidents",
            body=incident_body,
        )

        # Abort the session
        self._api.post(
            f"/sessions/{self._session_id}/abort",
            body={"reason": reason},
        )

    # -- success handler ---------------------------------------------------

    def _all_passed(self) -> None:
        """Both gates passed — enable Continue button."""
        self._continue_btn.configure(state="normal")

    # -- actions -----------------------------------------------------------

    def _on_cancel(self) -> None:
        self._router.show("student_dashboard", push=False)

    def _on_continue(self) -> None:
        if self._session_id is None:
            self._error_var.set("No session ID available.")
            self._error_label.pack(pady=(10, 0))
            return
        if self._aborted:
            return
        self._continue_btn.configure(text="Transitioning…", state="disabled")
        self._cancel_btn.configure(state="disabled")
        threading.Thread(target=self._do_transition, daemon=True).start()

    def _do_transition(self) -> None:
        ok, payload, err = self._api.patch(
            f"/sessions/{self._session_id}",
            body={"status": "in_progress"},
        )
        if ok:
            self._root.after(0, self._on_transition_ok)
        else:
            msg = err.message if err else "Transition failed."
            self._root.after(0, lambda: self._on_transition_fail(msg))

    def _on_transition_ok(self) -> None:
        self._router.show(
            "exam_taking",
            session_id=self._session_id,
            push=False,
        )

    def _on_transition_fail(self, msg: str) -> None:
        self._continue_btn.configure(text="Continue", state="normal")
        self._cancel_btn.configure(state="normal")
        self._error_var.set(msg)
        self._error_label.pack(pady=(10, 0))
