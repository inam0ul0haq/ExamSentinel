"""
Screen router / navigator for the ExamSentinel client.

Owns the root Tk window's content frame and swaps screens in and out by
name.  Supports a simple back-stack for screens that need it.
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Dict, List, Optional, Type

from client.app.ui import theme


class Router:
    """Manages screen navigation inside the root window."""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._registry: Dict[str, Type] = {}
        self._content_frame = tk.Frame(root, bg=theme.BG_PRIMARY)
        self._content_frame.pack(fill="both", expand=True)
        self._current_screen: Optional[tk.Frame] = None
        self._current_name: Optional[str] = None
        self._back_stack: List[Dict[str, Any]] = []

    # -- registration -------------------------------------------------------

    def register(self, name: str, screen_cls: Type) -> None:
        """Map a screen name to a class.  The class must accept
        ``(parent, router, **kwargs)`` in its constructor."""
        self._registry[name] = screen_cls

    # -- navigation ---------------------------------------------------------

    def show(self, screen_name: str, *, push: bool = True, **kwargs: Any) -> None:
        """Destroy the current screen and mount *screen_name*.

        Parameters
        ----------
        push : bool
            If ``True`` (default), the current screen is pushed onto the
            back-stack before navigating away.
        **kwargs
            Forwarded to the screen class constructor.
        """
        if screen_name not in self._registry:
            raise KeyError(f"Screen '{screen_name}' is not registered.")

        # Push current onto back-stack (if requested and there is one).
        if push and self._current_name is not None:
            self._back_stack.append({"name": self._current_name})

        self._destroy_current()

        cls = self._registry[screen_name]
        self._current_screen = cls(self._content_frame, self, **kwargs)
        self._current_screen.pack(fill="both", expand=True)
        self._current_name = screen_name

    def back(self) -> None:
        """Navigate to the previous screen on the back-stack."""
        if not self._back_stack:
            return
        entry = self._back_stack.pop()
        self.show(entry["name"], push=False)

    @property
    def can_go_back(self) -> bool:
        return len(self._back_stack) > 0

    # -- helpers ------------------------------------------------------------

    def _destroy_current(self) -> None:
        if self._current_screen is not None:
            try:
                self._current_screen.destroy()
            except tk.TclError:
                pass
            self._current_screen = None

    @property
    def root(self) -> tk.Tk:
        return self._root
