"""
Placeholder teacher-review screen (Part 18 stub).

Shows the exam_id passed from the teacher dashboard's "Review Sessions" action.
The real implementation will list student sessions for the exam.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from client.app.ui import theme


class TeacherReviewScreen(tk.Frame):
    """Stub screen for reviewing exam sessions."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 exam_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router

        tk.Label(
            self, text="Review Sessions", font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.38, anchor="center")

        tk.Label(
            self, text=f"Exam ID: {exam_id}", font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.48, anchor="center")

        tk.Label(
            self, text="Session review will be implemented in Part 18.",
            font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.56, anchor="center")

        tk.Button(
            self, text="\u2190 Back to Dashboard", font=theme.FONT_BUTTON,
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=theme.PAD_MEDIUM, pady=theme.PAD_SMALL,
            command=lambda: self._router.show("teacher_dashboard", push=False),
        ).place(relx=0.5, rely=0.66, anchor="center")
