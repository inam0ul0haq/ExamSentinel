"""
Splash screen — first thing the user sees.

Displays the ExamSentinel wordmark, a "Locked Exam Environment" subtitle,
a status line, and a small spinner.  On mount a background thread pings
``/health``.  On success the router navigates to the login screen; on
failure a red error and a Retry button appear.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any

from client.app.ui import theme


_SPINNER_GLYPHS = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_SPINNER_INTERVAL_MS = 100


class SplashScreen(tk.Frame):
    """Splash screen with animated health-check indicator."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api  # type: ignore[attr-defined]
        self._root: tk.Tk = router.root  # type: ignore[attr-defined]
        self._spinner_idx = 0
        self._spinning = False

        # --- wordmark ---
        tk.Label(
            self,
            text="ExamSentinel",
            font=("Segoe UI", 36, "bold"),
            bg=theme.BG_PRIMARY,
            fg=theme.ACCENT,
        ).place(relx=0.5, rely=0.38, anchor="center")

        # --- subtitle ---
        tk.Label(
            self,
            text="Locked Exam Environment",
            font=theme.FONT_SUBHEADING,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        ).place(relx=0.5, rely=0.47, anchor="center")

        # --- status line ---
        self._status_var = tk.StringVar(value="Connecting to server…")
        self._status_label = tk.Label(
            self,
            textvariable=self._status_var,
            font=theme.FONT_BODY,
            bg=theme.BG_PRIMARY,
            fg=theme.TEXT_SECONDARY,
        )
        self._status_label.place(relx=0.5, rely=0.55, anchor="center")

        # --- spinner ---
        self._spinner_label = tk.Label(
            self,
            text=_SPINNER_GLYPHS[0],
            font=("Segoe UI", 18),
            bg=theme.BG_PRIMARY,
            fg=theme.ACCENT,
        )
        self._spinner_label.place(relx=0.5, rely=0.62, anchor="center")

        # --- retry button (hidden by default) ---
        self._retry_btn = tk.Button(
            self,
            text="Retry",
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
            command=self._start_health_check,
        )
        # Not placed yet — shown only on failure.

        # --- kick off health check ---
        self._start_health_check()

    # -- spinner animation --------------------------------------------------

    def _start_spinner(self) -> None:
        self._spinning = True
        self._tick_spinner()

    def _stop_spinner(self) -> None:
        self._spinning = False

    def _tick_spinner(self) -> None:
        if not self._spinning:
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(_SPINNER_GLYPHS)
        try:
            self._spinner_label.configure(text=_SPINNER_GLYPHS[self._spinner_idx])
        except tk.TclError:
            return  # widget destroyed
        self._spinner_label.after(_SPINNER_INTERVAL_MS, self._tick_spinner)

    # -- health check -------------------------------------------------------

    def _start_health_check(self) -> None:
        self._retry_btn.place_forget()
        self._status_var.set("Connecting to server…")
        self._status_label.configure(fg=theme.TEXT_SECONDARY)
        self._spinner_label.configure(fg=theme.ACCENT)
        self._start_spinner()
        threading.Thread(target=self._check_health, daemon=True).start()

    def _check_health(self) -> None:
        ok, _payload, err = self._api.get("/health")
        if ok:
            self._root.after(0, self._on_health_ok)
        else:
            msg = err.message if err else "Unknown error."
            self._root.after(0, lambda: self._on_health_fail(msg))

    def _on_health_ok(self) -> None:
        self._stop_spinner()
        self._status_var.set("Server reachable")
        self._status_label.configure(fg=theme.SUCCESS)
        self._spinner_label.configure(text="✓", fg=theme.SUCCESS)
        # Brief pause so the user sees the success state, then navigate.
        self.after(800, self._go_to_login)

    def _on_health_fail(self, message: str) -> None:
        self._stop_spinner()
        self._status_var.set(message)
        self._status_label.configure(fg=theme.ERROR)
        self._spinner_label.configure(text="✗", fg=theme.ERROR)
        self._retry_btn.place(relx=0.5, rely=0.70, anchor="center")

    def _go_to_login(self) -> None:
        try:
            self._router.show("login", push=False)
        except tk.TclError:
            pass
