"""Right-Click Suppress subsystem — blocks right-click context menus.

On start(), walks the entire Tkinter widget tree and binds <Button-3> and
<Control-Button-1> to a do-nothing handler that returns "break". On stop(),
unbinds all. Exposes bind_for_widget() for dynamic widgets created mid-exam.

Posts RIGHT_CLICK_BLOCKED incident on each blocked attempt, throttled to
one per 5 seconds.

Cross-version: Tkinter binding is OS-agnostic.
"""

from __future__ import annotations

import logging
import time
import tkinter as tk
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


class RightClickSuppressSubsystem:
    """Suppresses right-click on all Tkinter widgets in the exam window."""

    def __init__(self, manager: Any, window: tk.Tk) -> None:
        self._manager = manager
        self._window = window
        self._started = False
        # Track bound widgets for cleanup
        self._bound_widgets: List[tk.Widget] = []
        # Throttle: one incident per 5 seconds
        self._last_incident_time: float = 0.0
        self._throttle_seconds = 5.0

    @property
    def name(self) -> str:
        return "right_click_suppress"

    @property
    def is_started(self) -> bool:
        return self._started

    def start(self) -> None:
        self._started = True
        self._walk_and_bind(self._window)
        logger.info(
            f"Right-click suppression active on {len(self._bound_widgets)} widget(s)"
        )

    def stop(self) -> None:
        self._started = False
        for widget in self._bound_widgets:
            try:
                widget.unbind("<Button-3>")
                widget.unbind("<Control-Button-1>")
            except Exception:
                pass
        self._bound_widgets.clear()
        logger.info("Right-click suppression removed.")

    # -- Public helper for dynamic widgets ----------------------------------

    def bind_for_widget(self, widget: tk.Widget) -> None:
        """Bind right-click suppression to a dynamically created widget.

        Call this from the exam screen when creating new widgets mid-exam
        (e.g., the submit confirmation dialog).
        """
        if not self._started:
            return
        self._bind_widget(widget)
        # Also bind all children
        for child in widget.winfo_children():
            self.bind_for_widget(child)

    # -- Internal -----------------------------------------------------------

    def _walk_and_bind(self, widget: tk.Widget) -> None:
        """Recursively walk the widget tree and bind suppression."""
        self._bind_widget(widget)
        for child in widget.winfo_children():
            self._walk_and_bind(child)

    def _bind_widget(self, widget: tk.Widget) -> None:
        """Bind right-click and Ctrl+click handlers to a single widget."""
        try:
            widget.bind("<Button-3>", self._on_right_click, add="+")
            widget.bind("<Control-Button-1>", self._on_right_click, add="+")
            self._bound_widgets.append(widget)
        except Exception as e:
            logger.debug(f"Failed to bind right-click suppression: {e}")

    def _on_right_click(self, event: Any = None) -> str:
        """Handler that blocks right-click and posts a throttled incident."""
        now = time.time()
        if now - self._last_incident_time >= self._throttle_seconds:
            self._last_incident_time = now
            self._manager.report(
                "RIGHT_CLICK_BLOCKED",
                "warning",
                "Right-click blocked in exam window",
                subsystem_name=self.name,
            )
        return "break"


__all__ = ["RightClickSuppressSubsystem"]
