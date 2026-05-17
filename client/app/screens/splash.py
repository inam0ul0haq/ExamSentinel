"""
Placeholder splash screen.

Shows a centred "ExamSentinel" label until the real splash screen is
implemented in Part 13.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from client.app.ui import theme


class SplashScreen(tk.Frame):
    """Minimal placeholder — just the app name centred on a dark background."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router

        label = tk.Label(
            self,
            text="ExamSentinel",
            font=("Segoe UI", 32, "bold"),
            bg=theme.BG_PRIMARY,
            fg=theme.ACCENT,
        )
        label.place(relx=0.5, rely=0.45, anchor="center")

        subtitle = tk.Label(
            self,
            text="Secure Examination Platform",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        )
        subtitle.place(relx=0.5, rely=0.54, anchor="center")
