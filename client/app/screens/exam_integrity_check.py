"""
Exam integrity-check screen.

Displays a placeholder message and Continue / Cancel buttons.
Continue calls PATCH /sessions/<id> with {"status":"in_progress"} to
transition the session from pre_check → in_progress, then navigates to
the exam-taking screen.  Cancel returns to the student dashboard.

Parts 20 and 22 will replace the body with real VM / stealth-VM checks;
the Cancel / Continue contract stays.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any

from client.app.ui import theme


class ExamIntegrityCheckScreen(tk.Frame):
    """Pre-exam integrity gate (placeholder body, real transition)."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 session_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api          # type: ignore[attr-defined]
        self._root: tk.Tk = router.root
        self._session_id = int(session_id) if session_id else None

        # --- heading ---
        tk.Label(
            self,
            text="Exam Integrity Check",
            font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.34, anchor="center")

        # --- placeholder body ---
        tk.Label(
            self,
            text="Integrity checks will run here. Click Continue to proceed.",
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.46, anchor="center")

        # --- status label (hidden until action) ---
        self._status_var = tk.StringVar()
        self._status_label = tk.Label(
            self,
            textvariable=self._status_var,
            font=theme.FONT_SMALL,
            bg=theme.BG_PRIMARY,
            fg=theme.ERROR,
        )

        # --- buttons ---
        btn_frame = tk.Frame(self, bg=theme.BG_PRIMARY)
        btn_frame.place(relx=0.5, rely=0.58, anchor="center")

        self._cancel_btn = tk.Button(
            btn_frame,
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
            btn_frame,
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
            command=self._on_continue,
        )
        self._continue_btn.pack(side="left")

    # -- actions -----------------------------------------------------------

    def _on_cancel(self) -> None:
        self._router.show("student_dashboard", push=False)

    def _on_continue(self) -> None:
        if self._session_id is None:
            self._show_error("No session ID available.")
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
        self._show_error(msg)

    def _show_error(self, msg: str) -> None:
        self._status_var.set(msg)
        self._status_label.place(relx=0.5, rely=0.68, anchor="center")
