"""
Placeholder exam-integrity-check screen (Part 17 stub).

Displays the session id passed through from the student dashboard.
The real implementation will perform environment integrity verification
before allowing the student into the exam.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from client.app.ui import theme


class ExamIntegrityCheckScreen(tk.Frame):
    """Stub screen that shows the session id while Part 17 is pending."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 session_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router

        tk.Label(
            self,
            text="Exam Integrity Check",
            font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.38, anchor="center")

        tk.Label(
            self,
            text=f"Session ID: {session_id}",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.48, anchor="center")

        tk.Label(
            self,
            text="Environment verification will be implemented in Part 17.",
            font=theme.FONT_SMALL,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.56, anchor="center")

        back_btn = tk.Button(
            self,
            text="\u2190 Back to Dashboard",
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
            command=lambda: self._router.show("student_dashboard", push=False),
        )
        back_btn.place(relx=0.5, rely=0.66, anchor="center")
