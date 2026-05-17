"""
Placeholder student dashboard — shows logged-in user name.

Will be replaced with the full dashboard in a later part.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from client.app.ui import theme


class StudentDashboardScreen(tk.Frame):
    """Minimal placeholder that confirms a successful student login."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._session = router.session  # type: ignore[attr-defined]

        user = self._session.user or {}
        name = user.get("full_name", "Student")

        tk.Label(
            self,
            text=f"Logged in as {name}",
            font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_PRIMARY,
        ).place(relx=0.5, rely=0.45, anchor="center")

        tk.Label(
            self,
            text="Student Dashboard (placeholder)",
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.55, anchor="center")
