"""
Login screen — email / password authentication.

Centred 480 px card on the dark background.  On successful login the token
and user profile are stashed in the API client and session state, and the
router navigates to the role-appropriate dashboard.  On failure the
server's human message is shown inline.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any

from client.app.ui import theme
from client.app.ui.widgets import (
    get_entry_value,
    primary_button,
    themed_entry,
    themed_label,
)


_CARD_WIDTH = 480
_CARD_PAD_X = 40
_CARD_PAD_Y = 32
_FIELD_PAD_Y = 6


class LoginScreen(tk.Frame):
    """Login card with email, password, show/hide toggle, and error label."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api          # type: ignore[attr-defined]
        self._session = router.session  # type: ignore[attr-defined]
        self._root: tk.Tk = router.root

        # --- centred card frame ---
        card = tk.Frame(self, bg=theme.BG_SECONDARY, highlightbackground=theme.BORDER,
                        highlightthickness=1)
        card.place(relx=0.5, rely=0.45, anchor="center", width=_CARD_WIDTH)

        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(padx=_CARD_PAD_X, pady=_CARD_PAD_Y, fill="x")

        # --- heading ---
        tk.Label(inner, text="Sign In", font=theme.FONT_HEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY
                 ).pack(pady=(0, 20))

        # --- email ---
        tk.Label(inner, text="Email", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, anchor="w"
                 ).pack(fill="x", pady=(_FIELD_PAD_Y, 2))
        self._email_entry = themed_entry(inner, placeholder="you@example.com")
        self._email_entry.pack(fill="x", ipady=4)

        # --- password row ---
        tk.Label(inner, text="Password", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, anchor="w"
                 ).pack(fill="x", pady=(_FIELD_PAD_Y + 4, 2))

        pw_frame = tk.Frame(inner, bg=theme.BG_SECONDARY)
        pw_frame.pack(fill="x")
        self._password_entry = themed_entry(pw_frame, placeholder="••••••••", show="•")
        self._password_entry.pack(side="left", fill="x", expand=True, ipady=4)

        self._show_pw = False
        self._toggle_btn = tk.Button(
            pw_frame, text="Show", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
            activebackground=theme.BG_SECONDARY, activeforeground=theme.ACCENT,
            relief="flat", bd=0, cursor="hand2",
            command=self._toggle_password,
        )
        self._toggle_btn.pack(side="right", padx=(4, 0))

        # --- error label (hidden by default) ---
        self._error_var = tk.StringVar()
        self._error_label = tk.Label(
            inner, textvariable=self._error_var, font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.ERROR, wraplength=_CARD_WIDTH - 2 * _CARD_PAD_X,
            justify="left",
        )
        # Packed but invisible when empty.
        self._error_label.pack(fill="x", pady=(8, 0))
        self._error_label.pack_forget()

        # --- login button ---
        self._login_btn = primary_button(inner, text="Login", command=self._on_login)
        self._login_btn.pack(fill="x", pady=(16, 0), ipady=4)

        # --- register link ---
        reg_label = tk.Label(
            inner, text="New here? Create an account", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.ACCENT, cursor="hand2",
        )
        reg_label.pack(pady=(14, 0))
        reg_label.bind("<Button-1>", lambda _: self._router.show("register"))
        reg_label.bind("<Enter>", lambda _: reg_label.configure(fg=theme.ACCENT_HOVER))
        reg_label.bind("<Leave>", lambda _: reg_label.configure(fg=theme.ACCENT))

        # --- footer ---
        tk.Label(self, text="PUCIT FYP 2026", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY
                 ).place(relx=0.5, rely=0.96, anchor="center")

        # --- keyboard bindings ---
        self._password_entry.bind("<Return>", lambda _: self._on_login())
        # Focus email after the widget is mapped.
        self.after(50, self._focus_email)

    # -- helpers ------------------------------------------------------------

    def _focus_email(self) -> None:
        self._email_entry.focus_set()
        # If placeholder is showing, clear it on focus
        if getattr(self._email_entry, "_has_placeholder", False):
            self._email_entry.event_generate("<FocusIn>")

    def _toggle_password(self) -> None:
        self._show_pw = not self._show_pw
        # Only change show char if the entry doesn't have placeholder
        if not getattr(self._password_entry, "_has_placeholder", False):
            self._password_entry.configure(show="" if self._show_pw else "•")
        self._password_entry._show_char = "" if self._show_pw else "•"  # type: ignore[attr-defined]
        self._toggle_btn.configure(text="Hide" if self._show_pw else "Show")

    def _show_error(self, msg: str) -> None:
        self._error_var.set(msg)
        self._error_label.pack(fill="x", pady=(8, 0))

    def _hide_error(self) -> None:
        self._error_var.set("")
        self._error_label.pack_forget()

    # -- login flow ---------------------------------------------------------

    def _on_login(self) -> None:
        self._hide_error()
        email = get_entry_value(self._email_entry).strip()
        password = get_entry_value(self._password_entry)

        if not email or not password:
            self._show_error("Please enter both email and password.")
            return

        # Disable button
        self._login_btn.configure(text="Signing in…", state="disabled")

        threading.Thread(target=self._do_login, args=(email, password), daemon=True).start()

    def _do_login(self, email: str, password: str) -> None:
        ok, payload, err = self._api.post("/auth/login", body={"email": email, "password": password})
        if ok:
            self._root.after(0, lambda: self._on_login_success(payload))
        else:
            msg = err.message if err else "Login failed."
            self._root.after(0, lambda: self._on_login_failure(msg))

    def _on_login_success(self, payload: dict) -> None:
        token = payload.get("access_token", "")
        user = payload.get("user", {})
        self._api.set_token(token)
        self._session.login(token, user)

        role = user.get("role", "student")
        if role == "teacher":
            self._router.show("teacher_dashboard", push=False)
        else:
            self._router.show("student_dashboard", push=False)

    def _on_login_failure(self, message: str) -> None:
        self._login_btn.configure(text="Login", state="normal")
        self._show_error(message)
