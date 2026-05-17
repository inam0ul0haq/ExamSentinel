"""
Register screen — account creation with role-specific fields.

Card layout with common fields at top, a role selector (Student / Teacher),
and a dynamic section that swaps fields based on the selected role.
Departments are loaded from GET /departments on mount.
"""

from __future__ import annotations

import re
import threading
import tkinter as tk
from typing import Any, Dict, List, Optional

from client.app.ui import theme
from client.app.ui.widgets import (
    get_entry_value,
    primary_button,
    themed_combobox,
    themed_entry,
    themed_label,
)


_CARD_WIDTH = 500
_CARD_PAD_X = 36
_CARD_PAD_Y = 24
_FIELD_PAD_Y = 4
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class RegisterScreen(tk.Frame):
    """Registration card with dynamic role-specific sections."""

    def __init__(self, parent: tk.Widget, router: Any, **kwargs: Any) -> None:
        super().__init__(parent, bg=theme.BG_PRIMARY)
        self._router = router
        self._api = router.api          # type: ignore[attr-defined]
        self._session = router.session  # type: ignore[attr-defined]
        self._root: tk.Tk = router.root

        self._departments: List[Dict[str, Any]] = []
        self._field_error_labels: Dict[str, tk.Label] = {}

        # --- scrollable area via canvas (card can be tall) ---
        card = tk.Frame(self, bg=theme.BG_SECONDARY, highlightbackground=theme.BORDER,
                        highlightthickness=1)
        card.place(relx=0.5, rely=0.47, anchor="center", width=_CARD_WIDTH)

        inner = tk.Frame(card, bg=theme.BG_SECONDARY)
        inner.pack(padx=_CARD_PAD_X, pady=_CARD_PAD_Y, fill="x")

        # --- heading ---
        tk.Label(inner, text="Create Account", font=theme.FONT_HEADING,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY
                 ).pack(pady=(0, 12))

        # --- full name ---
        self._name_entry = self._add_field(inner, "Full Name", "full_name", placeholder="Ahmed Khan")

        # --- email ---
        self._email_entry = self._add_field(inner, "Email", "email", placeholder="you@pucit.edu.pk")

        # --- password ---
        self._password_entry = self._add_field(inner, "Password", "password", placeholder="Min 8 characters", show="•")

        # --- confirm password ---
        self._confirm_entry = self._add_field(inner, "Confirm Password", "confirm_password", placeholder="Re-enter password", show="•")

        # --- role selector ---
        role_frame = tk.Frame(inner, bg=theme.BG_SECONDARY)
        role_frame.pack(fill="x", pady=(10, 2))
        tk.Label(role_frame, text="Role", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, anchor="w"
                 ).pack(side="left")

        self._role_var = tk.StringVar(value="student")
        seg_frame = tk.Frame(role_frame, bg=theme.BG_SECONDARY)
        seg_frame.pack(side="right")
        self._student_rb = tk.Radiobutton(
            seg_frame, text="Student", variable=self._role_var, value="student",
            font=theme.FONT_SMALL, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            selectcolor=theme.BG_INPUT, activebackground=theme.BG_SECONDARY,
            activeforeground=theme.ACCENT, indicatoron=1,
            command=self._on_role_change,
        )
        self._student_rb.pack(side="left", padx=(0, 10))
        self._teacher_rb = tk.Radiobutton(
            seg_frame, text="Teacher", variable=self._role_var, value="teacher",
            font=theme.FONT_SMALL, bg=theme.BG_SECONDARY, fg=theme.TEXT_PRIMARY,
            selectcolor=theme.BG_INPUT, activebackground=theme.BG_SECONDARY,
            activeforeground=theme.ACCENT, indicatoron=1,
            command=self._on_role_change,
        )
        self._teacher_rb.pack(side="left")
        self._add_field_error(inner, "role")

        # --- dynamic role section container ---
        self._role_section = tk.Frame(inner, bg=theme.BG_SECONDARY)
        self._role_section.pack(fill="x")

        # Student fields (created once, shown/hidden)
        self._student_frame = tk.Frame(self._role_section, bg=theme.BG_SECONDARY)
        self._roll_entry = self._add_field(self._student_frame, "Roll Number", "roll_number", placeholder="BSIT-F22-001")
        dept_lbl_frame = tk.Frame(self._student_frame, bg=theme.BG_SECONDARY)
        dept_lbl_frame.pack(fill="x", pady=(_FIELD_PAD_Y, 2))
        tk.Label(dept_lbl_frame, text="Department", font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, anchor="w"
                 ).pack(fill="x")
        self._dept_combo = themed_combobox(self._student_frame, values=(), width=36)
        self._dept_combo.pack(fill="x", ipady=2)
        self._add_field_error(self._student_frame, "department_id")
        self._semester_entry = self._add_field(self._student_frame, "Semester", "semester", placeholder="e.g. 5")

        # Teacher fields
        self._teacher_frame = tk.Frame(self._role_section, bg=theme.BG_SECONDARY)
        self._empcode_entry = self._add_field(self._teacher_frame, "Employee Code", "employee_code", placeholder="PUCIT-T-001")
        self._designation_entry = self._add_field(self._teacher_frame, "Designation", "designation", placeholder="Assistant Professor")

        # Show student fields by default
        self._current_role_frame: Optional[tk.Frame] = None
        self._on_role_change()

        # --- submit button ---
        self._submit_btn = primary_button(inner, text="Create Account", command=self._on_submit)
        self._submit_btn.pack(fill="x", pady=(14, 0), ipady=4)

        # --- login link ---
        login_label = tk.Label(
            inner, text="Already have an account? Sign in", font=theme.FONT_SMALL,
            bg=theme.BG_SECONDARY, fg=theme.ACCENT, cursor="hand2",
        )
        login_label.pack(pady=(10, 0))
        login_label.bind("<Button-1>", lambda _: self._router.show("login"))
        login_label.bind("<Enter>", lambda _: login_label.configure(fg=theme.ACCENT_HOVER))
        login_label.bind("<Leave>", lambda _: login_label.configure(fg=theme.ACCENT))

        # --- footer ---
        tk.Label(self, text="PUCIT FYP 2026", font=theme.FONT_SMALL,
                 bg=theme.BG_PRIMARY, fg=theme.TEXT_SECONDARY
                 ).place(relx=0.5, rely=0.96, anchor="center")

        # --- load departments in background ---
        threading.Thread(target=self._load_departments, daemon=True).start()

    # -- field helpers -------------------------------------------------------

    def _add_field(self, parent: tk.Frame, label: str, key: str,
                   placeholder: str = "", show: str = "") -> tk.Entry:
        tk.Label(parent, text=label, font=theme.FONT_SMALL,
                 bg=theme.BG_SECONDARY, fg=theme.TEXT_SECONDARY, anchor="w"
                 ).pack(fill="x", pady=(_FIELD_PAD_Y, 2))
        entry = themed_entry(parent, placeholder=placeholder, show=show)
        entry.pack(fill="x", ipady=3)
        self._add_field_error(parent, key)
        return entry

    def _add_field_error(self, parent: tk.Frame, key: str) -> None:
        lbl = tk.Label(parent, text="", font=("Segoe UI", 9),
                       bg=theme.BG_SECONDARY, fg=theme.ERROR, anchor="w",
                       wraplength=_CARD_WIDTH - 2 * _CARD_PAD_X, justify="left")
        lbl.pack(fill="x")
        lbl.pack_forget()
        self._field_error_labels[key] = lbl

    def _show_field_error(self, key: str, msg: str) -> None:
        lbl = self._field_error_labels.get(key)
        if lbl:
            lbl.configure(text=msg)
            lbl.pack(fill="x")

    def _clear_all_errors(self) -> None:
        for lbl in self._field_error_labels.values():
            lbl.configure(text="")
            lbl.pack_forget()

    # -- role toggle ---------------------------------------------------------

    def _on_role_change(self) -> None:
        if self._current_role_frame:
            self._current_role_frame.pack_forget()
        if self._role_var.get() == "student":
            self._student_frame.pack(in_=self._role_section, fill="x")
            self._current_role_frame = self._student_frame
        else:
            self._teacher_frame.pack(in_=self._role_section, fill="x")
            self._current_role_frame = self._teacher_frame

    # -- departments ---------------------------------------------------------

    def _load_departments(self) -> None:
        ok, payload, _err = self._api.get("/departments?page_size=100")
        if ok and payload:
            items = payload.get("items", [])
            self._departments = items
            names = tuple(d.get("name", "") for d in items)
            self._root.after(0, lambda: self._dept_combo.configure(values=names))

    # -- validation & submit -------------------------------------------------

    def _on_submit(self) -> None:
        self._clear_all_errors()
        errors: Dict[str, str] = {}

        name = get_entry_value(self._name_entry).strip()
        email = get_entry_value(self._email_entry).strip()
        password = get_entry_value(self._password_entry)
        confirm = get_entry_value(self._confirm_entry)
        role = self._role_var.get()

        if not name:
            errors["full_name"] = "Full name is required."
        if not email:
            errors["email"] = "Email is required."
        elif not _EMAIL_RE.match(email):
            errors["email"] = "Enter a valid email address."
        if not password:
            errors["password"] = "Password is required."
        elif len(password) < 8:
            errors["password"] = "Password must be at least 8 characters."
        if password and confirm != password:
            errors["confirm_password"] = "Passwords do not match."

        body: Dict[str, Any] = {
            "full_name": name,
            "email": email,
            "password": password,
            "role": role,
        }

        if role == "student":
            roll = get_entry_value(self._roll_entry).strip()
            semester_str = get_entry_value(self._semester_entry).strip()
            dept_name = self._dept_combo.get()

            if not roll:
                errors["roll_number"] = "Roll number is required."
            if not dept_name:
                errors["department_id"] = "Department is required."
            if not semester_str:
                errors["semester"] = "Semester is required."
            elif not semester_str.isdigit() or int(semester_str) <= 0:
                errors["semester"] = "Semester must be a positive number."

            # Resolve department id
            dept_id = None
            for d in self._departments:
                if d.get("name") == dept_name:
                    dept_id = d.get("id")
                    break
            body["roll_number"] = roll
            body["department_id"] = dept_id
            body["semester"] = int(semester_str) if semester_str.isdigit() else None
        else:
            emp = get_entry_value(self._empcode_entry).strip()
            desig = get_entry_value(self._designation_entry).strip()
            if not emp:
                errors["employee_code"] = "Employee code is required."
            if not desig:
                errors["designation"] = "Designation is required."
            body["employee_code"] = emp
            body["designation"] = desig

        if errors:
            for key, msg in errors.items():
                self._show_field_error(key, msg)
            return

        self._submit_btn.configure(text="Creating account…", state="disabled")
        threading.Thread(target=self._do_register, args=(body,), daemon=True).start()

    def _do_register(self, body: Dict[str, Any]) -> None:
        ok, payload, err = self._api.post("/auth/register", body=body)
        if ok:
            self._root.after(0, lambda: self._on_register_success(payload))
        else:
            self._root.after(0, lambda: self._on_register_failure(err))

    def _on_register_success(self, payload: dict) -> None:
        token = payload.get("access_token", "")
        user = payload.get("user", {})
        self._api.set_token(token)
        self._session.login(token, user)

        role = user.get("role", "student")
        if role == "teacher":
            self._router.show("teacher_dashboard", push=False)
        else:
            self._router.show("student_dashboard", push=False)

    def _on_register_failure(self, err: Any) -> None:
        self._submit_btn.configure(text="Create Account", state="normal")
        if err and err.field_errors:
            for field, messages in err.field_errors.items():
                msg = messages[0] if isinstance(messages, list) and messages else str(messages)
                self._show_field_error(field, msg)
        elif err:
            # Show general error on the first available field
            self._show_field_error("full_name", err.message)
        else:
            self._show_field_error("full_name", "Registration failed.")
