"""
Reusable themed Tkinter widget factories.

Every function returns a standard Tkinter widget styled with the ExamSentinel
dark theme — no third-party GUI libraries.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Optional, Tuple

from client.app.ui import theme


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

def primary_button(
    parent: tk.Widget,
    text: str,
    command: Any = None,
    width: int = 18,
    **kwargs: Any,
) -> tk.Button:
    """Vivid-accent action button."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        font=theme.FONT_BUTTON,
        bg=theme.ACCENT,
        fg="#FFFFFF",
        activebackground=theme.ACCENT_HOVER,
        activeforeground="#FFFFFF",
        relief="flat",
        cursor="hand2",
        width=width,
        bd=0,
        padx=theme.PAD_MEDIUM,
        pady=theme.PAD_SMALL,
        **kwargs,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=theme.ACCENT_HOVER))
    btn.bind("<Leave>", lambda e: btn.configure(bg=theme.ACCENT))
    return btn


def secondary_button(
    parent: tk.Widget,
    text: str,
    command: Any = None,
    width: int = 18,
    **kwargs: Any,
) -> tk.Button:
    """Outlined / subdued button for secondary actions."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        font=theme.FONT_BUTTON,
        bg=theme.BG_SECONDARY,
        fg=theme.TEXT_PRIMARY,
        activebackground=theme.BORDER,
        activeforeground=theme.TEXT_PRIMARY,
        relief="flat",
        cursor="hand2",
        width=width,
        bd=0,
        highlightbackground=theme.BORDER,
        highlightthickness=1,
        padx=theme.PAD_MEDIUM,
        pady=theme.PAD_SMALL,
        **kwargs,
    )
    btn.bind("<Enter>", lambda e: btn.configure(bg=theme.BORDER))
    btn.bind("<Leave>", lambda e: btn.configure(bg=theme.BG_SECONDARY))
    return btn


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------

def themed_label(
    parent: tk.Widget,
    text: str = "",
    font: Optional[Tuple] = None,
    fg: Optional[str] = None,
    **kwargs: Any,
) -> tk.Label:
    return tk.Label(
        parent,
        text=text,
        font=font or theme.FONT_BODY,
        bg=kwargs.pop("bg", theme.BG_PRIMARY),
        fg=fg or theme.TEXT_PRIMARY,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Entry with placeholder
# ---------------------------------------------------------------------------

def themed_entry(
    parent: tk.Widget,
    placeholder: str = "",
    show: str = "",
    width: int = 30,
    **kwargs: Any,
) -> tk.Entry:
    """Entry field with focus-in / focus-out placeholder emulation."""
    entry = tk.Entry(
        parent,
        font=theme.FONT_BODY,
        bg=theme.BG_INPUT,
        fg=theme.TEXT_PRIMARY,
        insertbackground=theme.TEXT_PRIMARY,
        relief="flat",
        width=width,
        highlightbackground=theme.BORDER,
        highlightcolor=theme.ACCENT,
        highlightthickness=1,
        bd=4,
        **kwargs,
    )

    # Store metadata on the widget itself
    entry._placeholder = placeholder  # type: ignore[attr-defined]
    entry._show_char = show           # type: ignore[attr-defined]
    entry._has_placeholder = False     # type: ignore[attr-defined]

    def _set_placeholder() -> None:
        entry.delete(0, tk.END)
        entry.insert(0, placeholder)
        entry.configure(fg=theme.TEXT_PLACEHOLDER, show="")
        entry._has_placeholder = True  # type: ignore[attr-defined]

    def _clear_placeholder() -> None:
        entry.delete(0, tk.END)
        entry.configure(fg=theme.TEXT_PRIMARY, show=show)
        entry._has_placeholder = False  # type: ignore[attr-defined]

    def _on_focus_in(_event: tk.Event) -> None:
        if entry._has_placeholder:  # type: ignore[attr-defined]
            _clear_placeholder()

    def _on_focus_out(_event: tk.Event) -> None:
        if not entry.get():
            _set_placeholder()

    if placeholder:
        _set_placeholder()
        entry.bind("<FocusIn>", _on_focus_in)
        entry.bind("<FocusOut>", _on_focus_out)

    return entry


def get_entry_value(entry: tk.Entry) -> str:
    """Return the entry's text, treating placeholder state as empty."""
    if getattr(entry, "_has_placeholder", False):
        return ""
    return entry.get()


# ---------------------------------------------------------------------------
# Combobox (ttk — styled as close to the theme as possible)
# ---------------------------------------------------------------------------

def themed_combobox(
    parent: tk.Widget,
    values: tuple = (),
    width: int = 28,
    **kwargs: Any,
) -> ttk.Combobox:
    style = ttk.Style(parent)
    style.theme_use("clam")
    style.configure(
        "ES.TCombobox",
        fieldbackground=theme.BG_INPUT,
        background=theme.BG_SECONDARY,
        foreground=theme.TEXT_PRIMARY,
        arrowcolor=theme.TEXT_SECONDARY,
        bordercolor=theme.BORDER,
        selectbackground=theme.ACCENT,
        selectforeground="#FFFFFF",
    )
    combo = ttk.Combobox(
        parent,
        values=values,
        width=width,
        style="ES.TCombobox",
        state="readonly",
        font=theme.FONT_BODY,
        **kwargs,
    )
    return combo


# ---------------------------------------------------------------------------
# Text area
# ---------------------------------------------------------------------------

def themed_text(
    parent: tk.Widget,
    width: int = 60,
    height: int = 8,
    **kwargs: Any,
) -> tk.Text:
    return tk.Text(
        parent,
        font=theme.FONT_BODY,
        bg=theme.BG_INPUT,
        fg=theme.TEXT_PRIMARY,
        insertbackground=theme.TEXT_PRIMARY,
        relief="flat",
        width=width,
        height=height,
        highlightbackground=theme.BORDER,
        highlightcolor=theme.ACCENT,
        highlightthickness=1,
        bd=4,
        wrap="word",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Toast notification
# ---------------------------------------------------------------------------

class Toast:
    """Briefly shows a coloured message at the bottom of a window."""

    _LEVEL_COLOURS = {
        "success": theme.SUCCESS,
        "error": theme.ERROR,
        "warning": theme.WARNING,
        "info": theme.ACCENT,
    }

    def __init__(self, parent: tk.Widget) -> None:
        self._parent = parent
        self._label: Optional[tk.Label] = None

    def show(
        self,
        message: str,
        level: str = "info",
        duration_ms: int = theme.TOAST_DURATION_MS,
    ) -> None:
        """Display *message* for *duration_ms* milliseconds."""
        self.dismiss()
        fg = self._LEVEL_COLOURS.get(level, theme.ACCENT)
        self._label = tk.Label(
            self._parent,
            text=message,
            font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY,
            fg=fg,
            padx=theme.PAD_MEDIUM,
            pady=theme.PAD_SMALL,
            anchor="center",
        )
        self._label.pack(side="bottom", fill="x", pady=(0, theme.PAD_SMALL))
        self._label.after(duration_ms, self.dismiss)

    def dismiss(self) -> None:
        if self._label is not None:
            try:
                self._label.destroy()
            except tk.TclError:
                pass
            self._label = None
