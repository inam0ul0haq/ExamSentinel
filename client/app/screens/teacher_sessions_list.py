"""
Teacher Sessions List screen.

Fetches GET /teacher/exams/<id>/sessions (paginated) and renders a table
showing student name, roll number, status badge, started/ended timestamps,
score, incident count, and highest severity.  Clicking a row navigates to
the session detail screen.

Includes a "View Analytics" button that opens an analytics drawer with
aggregate stats from GET /teacher/exams/<id>/analytics.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Any, Dict, List, Optional

from client.app.ui import theme


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_STATUS_COLORS: Dict[str, str] = {
    "pre_check": theme.TEXT_SECONDARY,
    "in_progress": theme.ACCENT,
    "submitted": theme.SUCCESS,
    "expired": theme.WARNING,
    "aborted_vm": theme.ERROR,
    "aborted_stealth_vm": theme.ERROR,
}

_SEVERITY_COLORS: Dict[str, str] = {
    "info": theme.TEXT_SECONDARY,
    "warning": theme.WARNING,
    "critical": theme.ERROR,
}


def _fmt_dt(iso: Optional[str]) -> str:
    """Format ISO timestamp to readable short form."""
    if not iso:
        return "\u2014"
    # e.g. "2026-05-18T02:20:13.789980+00:00" → "2026-05-18 02:20"
    try:
        return iso[:16].replace("T", " ")
    except Exception:
        return iso


# ===================================================================
# Main screen
# ===================================================================

class TeacherSessionsListScreen(tk.Frame):
    """Lists all sessions for a given exam."""

    def __init__(self, parent: tk.Widget, router: Any, *,
                 exam_id: Any = None, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api
        self._root: tk.Tk = router.root
        self._exam_id = exam_id
        self._page = 1
        self._page_size = 20
        self._total_pages = 1
        self._analytics_visible = False

        self._build_header()
        self._list_frame = tk.Frame(self, bg=theme.BG_PRIMARY)
        self._list_frame.pack(fill="both", expand=True, padx=24)

        self._analytics_frame: Optional[tk.Frame] = None

        self._show_loading()
        self._fetch()

    # ---- header ----

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=theme.BG_PRIMARY)
        hdr.pack(fill="x", padx=24, pady=(20, 10))

        back = tk.Label(hdr, text="\u2190 Back", font=theme.FONT_BODY,
                        bg=theme.BG_PRIMARY, fg=theme.ACCENT, cursor="hand2")
        back.pack(side="left")
        back.bind("<Button-1>", lambda _e: self._go_back())

        tk.Label(
            hdr,
            text=f"Sessions — Exam #{self._exam_id}",
            font=theme.FONT_HEADING,
            bg=theme.BG_PRIMARY, fg=theme.TEXT_PRIMARY,
        ).pack(side="left", padx=16)

        tk.Button(
            hdr, text="View Analytics", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.ACCENT,
            activebackground=theme.BORDER, activeforeground=theme.ACCENT,
            relief="flat", cursor="hand2", bd=0, padx=12, pady=4,
            command=self._toggle_analytics,
        ).pack(side="right")

        tk.Button(
            hdr, text="\u21bb Refresh", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
            activebackground=theme.BORDER, activeforeground=theme.TEXT_PRIMARY,
            relief="flat", cursor="hand2", bd=0, padx=8, pady=2,
            command=self._refresh,
        ).pack(side="right", padx=(0, 8))

    # ---- data fetch ----

    def _show_loading(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        tk.Label(self._list_frame, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY).pack(pady=40)

    def _fetch(self) -> None:
        eid = self._exam_id
        p = self._page
        ps = self._page_size

        def _work():
            ok, payload, err = self._api.get(
                f"/teacher/exams/{eid}/sessions?page={p}&page_size={ps}")
            if ok:
                self._root.after(0, lambda: self._on_ok(payload))
            else:
                msg = err.message if err else "Failed to load sessions."
                self._root.after(0, lambda: self._on_err(msg))
        threading.Thread(target=_work, daemon=True).start()

    def _on_ok(self, payload: dict) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()

        items = payload.get("items", [])
        pag = payload.get("pagination", {})
        self._total_pages = pag.get("total_pages", 1)
        total = pag.get("total_items", len(items))

        self._render(items, total)

    def _on_err(self, msg: str) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        tk.Label(self._list_frame, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_PRIMARY, fg=theme.ERROR).pack(pady=40)

    def _refresh(self) -> None:
        self._page = 1
        self._show_loading()
        self._fetch()

    # ---- render table ----

    def _render(self, items: List[dict], total: int) -> None:
        if not items:
            tk.Label(self._list_frame, text="No sessions found for this exam.",
                     font=theme.FONT_BODY, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(pady=60)
            return

        # Summary
        tk.Label(self._list_frame,
                 text=f"{total} session(s) total",
                 font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
                 fg=theme.TEXT_SECONDARY).pack(anchor="w", pady=(0, 8))

        # Scrollable area
        canvas = tk.Canvas(self._list_frame, bg=theme.BG_PRIMARY,
                           highlightthickness=0, bd=0)
        vsb = tk.Scrollbar(self._list_frame, orient="vertical",
                           command=canvas.yview)
        inner = tk.Frame(canvas, bg=theme.BG_PRIMARY)
        inner.bind("<Configure>",
                   lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", tags=("inner",))
        canvas.configure(yscrollcommand=vsb.set)

        def _stretch(_e):
            canvas.itemconfigure("inner", width=canvas.winfo_width())
        canvas.bind("<Configure>", _stretch)

        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _wheel(event):
            try:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass
        canvas.bind("<Enter>",
                    lambda _: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>",
                    lambda _: canvas.unbind_all("<MouseWheel>"))

        # Table header
        hdr = tk.Frame(inner, bg=theme.BG_INPUT)
        hdr.pack(fill="x", pady=(0, 2))
        cols = [("Student", 18), ("Roll #", 14), ("Status", 10),
                ("Started", 16), ("Ended", 16), ("Score", 10),
                ("Incidents", 8), ("Severity", 8)]
        for txt, w in cols:
            tk.Label(hdr, text=txt, font=("Segoe UI", 9, "bold"),
                     bg=theme.BG_INPUT, fg=theme.TEXT_SECONDARY,
                     width=w, anchor="w").pack(side="left", padx=2, pady=4)

        # Rows
        for item in items:
            self._row(inner, item)

        # Pagination
        if self._total_pages > 1:
            pf = tk.Frame(inner, bg=theme.BG_PRIMARY)
            pf.pack(fill="x", pady=8)
            if self._page > 1:
                tk.Button(pf, text="\u2190 Prev", font=theme.FONT_SMALL,
                          bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                          relief="flat", cursor="hand2", bd=0, padx=8,
                          command=lambda: self._go_page(-1)).pack(side="left")
            tk.Label(pf, text=f"Page {self._page}/{self._total_pages}",
                     font=theme.FONT_SMALL, bg=theme.BG_PRIMARY,
                     fg=theme.TEXT_SECONDARY).pack(side="left", padx=8)
            if self._page < self._total_pages:
                tk.Button(pf, text="Next \u2192", font=theme.FONT_SMALL,
                          bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                          relief="flat", cursor="hand2", bd=0, padx=8,
                          command=lambda: self._go_page(1)).pack(side="left")

    def _row(self, parent: tk.Widget, item: dict) -> None:
        row = tk.Frame(parent, bg=theme.BG_SECONDARY,
                       highlightbackground=theme.BORDER, highlightthickness=1,
                       cursor="hand2")
        row.pack(fill="x", pady=1)
        inner = tk.Frame(row, bg=theme.BG_SECONDARY)
        inner.pack(fill="x", padx=4, pady=4)

        student = item.get("student") or {}
        name = student.get("name", "\u2014")
        roll = student.get("roll_number", "\u2014")
        status = item.get("status", "unknown")
        started = _fmt_dt(item.get("started_at"))
        ended = _fmt_dt(item.get("ended_at"))
        score = item.get("score")
        total = item.get("total_marks")
        score_txt = f"{score:.1f}/{total}" if score is not None and total else "\u2014"
        inc_count = item.get("incident_count", 0)
        hi_sev = item.get("highest_incident_severity") or "\u2014"

        status_color = _STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
        sev_color = _SEVERITY_COLORS.get(hi_sev, theme.TEXT_SECONDARY)

        widgets = []
        widgets.append(tk.Label(inner, text=name, font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                                width=18, anchor="w"))
        widgets.append(tk.Label(inner, text=roll, font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                                width=14, anchor="w"))
        widgets.append(tk.Label(inner, text=status.replace("_", " ").title(),
                                font=("Segoe UI", 9, "bold"),
                                bg=theme.BG_SECONDARY, fg=status_color,
                                width=10, anchor="w"))
        widgets.append(tk.Label(inner, text=started, font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                                width=16, anchor="w"))
        widgets.append(tk.Label(inner, text=ended, font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                                width=16, anchor="w"))
        widgets.append(tk.Label(inner, text=score_txt, font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                                width=10, anchor="w"))
        widgets.append(tk.Label(inner, text=str(inc_count), font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY,
                                fg=theme.WARNING if inc_count > 0 else theme.TEXT_SECONDARY,
                                width=8, anchor="w"))
        widgets.append(tk.Label(inner, text=hi_sev if hi_sev != "\u2014" else "\u2014",
                                font=theme.FONT_SMALL,
                                bg=theme.BG_SECONDARY, fg=sev_color,
                                width=8, anchor="w"))

        for w in widgets:
            w.pack(side="left", padx=2)

        sid = item.get("id")
        def _click(_e, session_id=sid):
            self._open_detail(session_id)
        for w in (row, inner, *widgets):
            w.bind("<Button-1>", _click)

    def _open_detail(self, session_id: int) -> None:
        self._router.show("teacher_session_detail", session_id=session_id)

    def _go_page(self, delta: int) -> None:
        self._page += delta
        self._show_loading()
        self._fetch()

    def _go_back(self) -> None:
        self._router.show("teacher_dashboard", push=False)

    # ================================================================
    # Analytics drawer
    # ================================================================

    def _toggle_analytics(self) -> None:
        if self._analytics_visible:
            self._close_analytics()
        else:
            self._open_analytics()

    def _close_analytics(self) -> None:
        self._analytics_visible = False
        if self._analytics_frame:
            self._analytics_frame.destroy()
            self._analytics_frame = None

    def _open_analytics(self) -> None:
        self._analytics_visible = True
        self._analytics_frame = af = tk.Frame(
            self, bg=theme.BG_SECONDARY, width=360,
            highlightbackground=theme.BORDER, highlightthickness=1,
        )
        af.place(relx=1.0, rely=0.0, anchor="ne", relheight=1.0, width=360)
        af.pack_propagate(False)

        # Close button
        top = tk.Frame(af, bg=theme.BG_SECONDARY)
        top.pack(fill="x", padx=12, pady=(12, 0))
        tk.Label(top, text="Exam Analytics", font=theme.FONT_SUBHEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(side="left")
        close_btn = tk.Label(top, text="\u2715", font=theme.FONT_BODY,
                             bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                             cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda _: self._close_analytics())

        # Loading
        self._analytics_body = tk.Frame(af, bg=theme.BG_SECONDARY)
        self._analytics_body.pack(fill="both", expand=True, padx=12, pady=8)
        tk.Label(self._analytics_body, text="Loading\u2026", font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(pady=30)

        eid = self._exam_id
        def _work():
            ok, payload, err = self._api.get(
                f"/teacher/exams/{eid}/analytics")
            if ok:
                self._root.after(0, lambda: self._render_analytics(payload))
            else:
                msg = err.message if err else "Failed to load analytics."
                self._root.after(0, lambda: self._analytics_err(msg))
        threading.Thread(target=_work, daemon=True).start()

    def _analytics_err(self, msg: str) -> None:
        if not self._analytics_body:
            return
        for w in self._analytics_body.winfo_children():
            w.destroy()
        tk.Label(self._analytics_body, text=msg, font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.ERROR).pack(pady=20)

    def _render_analytics(self, data: dict) -> None:
        if not self._analytics_body:
            return
        for w in self._analytics_body.winfo_children():
            w.destroy()

        body = self._analytics_body

        # Exam info
        tk.Label(body, text=data.get("title", ""), font=theme.FONT_BODY,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
                 wraplength=320, anchor="w", justify="left").pack(
            anchor="w", pady=(0, 8))

        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", pady=4)

        # Status counts
        tk.Label(body, text="Sessions by Status", font=("Segoe UI", 10, "bold"),
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
            anchor="w", pady=(8, 4))
        status_counts = data.get("sessions_by_status", {})
        for status, cnt in status_counts.items():
            color = _STATUS_COLORS.get(status, theme.TEXT_SECONDARY)
            tk.Label(body,
                     text=f"  {status.replace('_', ' ').title()}: {cnt}",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=color).pack(anchor="w")

        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", pady=4)

        # Score stats
        tk.Label(body, text="Score Statistics", font=("Segoe UI", 10, "bold"),
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
            anchor="w", pady=(8, 4))
        ss = data.get("score_stats", {})
        total_marks = data.get("total_marks", "?")
        for key in ("mean", "median", "min", "max"):
            val = ss.get(key)
            txt = f"{val:.1f}" if val is not None else "\u2014"
            tk.Label(body,
                     text=f"  {key.title()}: {txt} / {total_marks}",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                anchor="w")

        tk.Frame(body, bg=theme.BORDER, height=1).pack(fill="x", pady=4)

        # Incident histogram
        tk.Label(body, text="Incident Types (Top 5)",
                 font=("Segoe UI", 10, "bold"),
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
            anchor="w", pady=(8, 4))
        inc = data.get("incidents", {})
        top_types = inc.get("top_types", [])
        if not top_types:
            tk.Label(body, text="  No incidents", font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY).pack(
                anchor="w")
        else:
            max_count = max(t["count"] for t in top_types) if top_types else 1
            for t in top_types:
                row = tk.Frame(body, bg=theme.BG_SECONDARY)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=f"  {t['type']}", font=theme.FONT_SMALL,
                         bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY,
                         width=22, anchor="w").pack(side="left")
                # Bar
                bar_w = max(int(120 * t["count"] / max_count), 4)
                bar = tk.Frame(row, bg=theme.ACCENT, height=12, width=bar_w)
                bar.pack(side="left", padx=(4, 4))
                bar.pack_propagate(False)
                tk.Label(row, text=str(t["count"]), font=theme.FONT_SMALL,
                         bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY).pack(
                    side="left")

        pct = inc.get("percent_submitted_with_critical", 0)
        if pct > 0:
            tk.Label(body,
                     text=f"  {pct:.1f}% of submitted have critical incidents",
                     font=theme.FONT_SMALL,
                     bg=theme.BG_SECONDARY, fg=theme.ERROR).pack(
                anchor="w", pady=(6, 0))
