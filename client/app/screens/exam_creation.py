"""
Placeholder exam-creation screen (Part 16 stub).

Displays the course_id and optional exam_id for create/edit mode.
The real implementation will provide a full form for exam + questions.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from client.app.ui import theme


class ExamCreationScreen(tk.Frame):
    """Stub screen for exam creation / editing."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 course_id: Any = None, exam_id: Any = None,
                 **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router

        mode = "Edit Exam" if exam_id else "Create Exam"

        tk.Label(
            self, text=mode, font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.34, anchor="center")

        tk.Label(
            self, text=f"Course ID: {course_id}", font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.44, anchor="center")

        if exam_id:
            tk.Label(
                self, text=f"Exam ID: {exam_id}", font=theme.FONT_SUBHEADING,
                bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY,
            ).place(relx=0.5, rely=0.50, anchor="center")

        tk.Label(
            self, text="Full exam form will be implemented in Part 16.",
            font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.58, anchor="center")

        tk.Button(
            self, text="\u2190 Back to Dashboard", font=theme.FONT_BUTTON,
            bg=theme.ACCENT, fg="#FFFFFF",
            activebackground=theme.ACCENT_HOVER, activeforeground="#FFFFFF",
            relief="flat", cursor="hand2", bd=0,
            padx=theme.PAD_MEDIUM, pady=theme.PAD_SMALL,
            command=lambda: self._router.show("teacher_dashboard", push=False),
        ).place(relx=0.5, rely=0.68, anchor="center")
