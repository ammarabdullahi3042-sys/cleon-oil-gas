"""Attendant management page hosted inside the main dashboard."""

import sqlite3
from datetime import date, datetime
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk

from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from short_reconciliation import (
    ensure_reconciliation_schema, attendant_short_balances,
    attendant_short_outstanding, reconcile_attendant_short,
)
from attendant_payroll import (
    ensure_payroll_schema, process_salary_payment, salary_preview,
)
from number_entry import FormattedNumberEntry


from app_settings import get_active_database

DATABASE = get_active_database()


class AttendantWindow(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, fg_color=Theme.BG)
        self.attendant_id = None
        self.build_ui()
        self.load_attendants()

    def build_ui(self):
        ctk.CTkLabel(self, text="Attendant Management", font=Theme.TITLE_FONT,
                     text_color=Theme.TEXT).pack(anchor="w", padx=20, pady=(18, 12))
        form = Theme.card(self)
        form.pack(fill="x", padx=20, pady=8)
        self.name_entry = ctk.CTkEntry(form, placeholder_text="Attendant name", height=40)
        self.name_entry.pack(fill="x", padx=14, pady=(14, 7))
        self.phone_entry = ctk.CTkEntry(form, placeholder_text="Phone number", height=40)
        self.phone_entry.pack(fill="x", padx=14, pady=7)
        self.joined_entry = ctk.CTkEntry(
            form, placeholder_text="Date joined (DD-MM-YY)", height=40
        )
        self.joined_entry.pack(fill="x", padx=14, pady=7)
        self.joined_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.joined_entry)
        self.salary_entry = FormattedNumberEntry(
            form, placeholder_text="Monthly base salary (NGN)", height=40
        )
        self.salary_entry.pack(fill="x", padx=14, pady=7)
        self.payday_entry = FormattedNumberEntry(
            form, placeholder_text="Monthly payday (day 1-31)", height=40
        )
        self.payday_entry.pack(fill="x", padx=14, pady=7)
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.pack(pady=(5, 12))
        self.save_button = Theme.primary_button(actions, "Save New Attendant", self.save_attendant)
        self.save_button.pack(side="left", padx=5)
        Theme.secondary_button(actions, "Update", self.update_attendant).pack(side="left", padx=5)
        Theme.danger_button(actions, "Delete", self.delete_attendant).pack(side="left", padx=5)
        Theme.secondary_button(actions, "Clear", self.clear_form).pack(side="left", padx=5)
        Theme.primary_button(
            actions, "Update Short", self.reconcile_shorts
        ).pack(side="left", padx=5)
        Theme.secondary_button(
            actions, "Short History", self.open_short_history
        ).pack(side="left", padx=5)
        Theme.primary_button(
            actions, "Process Salary", self.process_salary
        ).pack(side="left", padx=5)
        Theme.secondary_button(
            actions, "Salary History", self.open_salary_history
        ).pack(side="left", padx=5)

        table_frame = ctk.CTkFrame(self, fg_color=Theme.SURFACE,
                                   corner_radius=Theme.CARD_RADIUS)
        table_frame.pack(fill="both", expand=True, padx=20, pady=(8, 18))
        columns = (
            "Name", "Phone", "Date Joined", "Monthly Salary NGN",
            "Payday", "Outstanding Shorts NGN",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        for column, width in zip(columns, (210, 150, 125, 155, 75, 180)):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, anchor="center")
        bar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=bar.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        bar.pack(side="right", fill="y", padx=(0, 8), pady=8)
        self.tree.bind("<<TreeviewSelect>>", self.select_attendant)

    def load_attendants(self):
        self.tree.delete(*self.tree.get_children())
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_reconciliation_schema(conn)
                ensure_payroll_schema(conn)
                rows = conn.execute("""
                    SELECT id,name,COALESCE(phone,''),COALESCE(date_joined,''),
                           COALESCE(monthly_salary,0),salary_payday_day
                    FROM attendants ORDER BY name COLLATE NOCASE
                """).fetchall()
                balances = {
                    row[0]: attendant_short_outstanding(conn, row[0])
                    for row in rows
                }
            for attendant_id, name, phone, joined, salary, payday in rows:
                self.tree.insert("", "end", iid=str(attendant_id),
                                 values=(name, phone, joined,
                                         f"₦{salary:,.2f}",
                                         "" if payday is None else str(payday),
                                         f"₦{balances[attendant_id]:,.2f}"))
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not load attendants:\n{error}", parent=self)

    def select_attendant(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        self.attendant_id = int(selected[0])
        self.save_button.configure(text="Save Changes to Selected Attendant")
        name, phone, joined, salary, payday, _outstanding = self.tree.item(
            selected[0], "values"
        )
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, name)
        self.phone_entry.delete(0, "end")
        self.phone_entry.insert(0, phone)
        self.joined_entry.delete(0, "end")
        self.joined_entry.insert(0, joined or "")
        self.salary_entry.delete(0, "end")
        self.salary_entry.insert(0, str(salary).replace("₦", "").replace(",", ""))
        self.payday_entry.delete(0, "end")
        self.payday_entry.insert(0, payday or "")

    def _values(self):
        name = self.name_entry.get().strip()
        phone = self.phone_entry.get().strip()
        joined = self.joined_entry.get().strip()
        if not name:
            raise ValueError("Attendant name is required.")
        try:
            joined = parse_flexible_date(joined).isoformat()
        except ValueError as error:
            raise ValueError(str(error)) from error
        try:
            salary = float(self.salary_entry.get().replace(",", "").strip() or 0)
            payday_text = self.payday_entry.get().strip()
            payday = int(payday_text) if payday_text else None
        except ValueError as error:
            raise ValueError("Enter a valid monthly salary and payday day.") from error
        if salary < 0:
            raise ValueError("Monthly salary cannot be negative.")
        if payday is not None and not 1 <= payday <= 31:
            raise ValueError("Monthly payday must be between day 1 and 31.")
        if salary > 0 and payday is None:
            raise ValueError("Enter the monthly payday for this salary.")
        return name, phone, joined, salary, payday

    def _authorize(self, action):
        password = simpledialog.askstring(
            "Password Required", f"Enter an authorized password to {action}:",
            parent=self, show="*"
        )
        if password is None:
            return False
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                found = conn.execute("SELECT 1 FROM users WHERE password=? LIMIT 1",
                                     (password,)).fetchone()
        except sqlite3.Error as error:
            messagebox.showerror("Authorization Error", str(error), parent=self)
            return False
        if found:
            return True
        messagebox.showerror("Access Denied", "The password is incorrect.", parent=self)
        return False

    def save_attendant(self):
        if self.attendant_id is not None:
            self.update_attendant()
            return
        try:
            name, phone, joined, salary, payday = self._values()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_payroll_schema(conn)
                conn.execute(
                    """INSERT INTO attendants
                       (name,phone,date_joined,monthly_salary,salary_payday_day)
                       VALUES (?,?,?,?,?)""",
                    (name, phone, joined, salary, payday)
                )
            self.load_attendants()
            self.clear_form()
            messagebox.showinfo("Saved", "Attendant saved successfully.", parent=self)
        except ValueError as error:
            messagebox.showwarning("Check Entry", str(error), parent=self)
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not save attendant:\n{error}", parent=self)

    def update_attendant(self):
        if self.attendant_id is None:
            messagebox.showwarning("Select Attendant", "Select an attendant to update.", parent=self)
            return
        if not self._authorize("update this attendant"):
            return
        try:
            name, phone, joined, salary, payday = self._values()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_payroll_schema(conn)
                cursor = conn.execute(
                    """UPDATE attendants
                       SET name=?,phone=?,date_joined=?,monthly_salary=?,
                           salary_payday_day=?
                       WHERE id=?""",
                    (name, phone, joined, salary, payday, self.attendant_id)
                )
                if cursor.rowcount != 1:
                    raise ValueError("The selected attendant no longer exists; no new attendant was created.")
            self.load_attendants()
            messagebox.showinfo("Updated", "Attendant details updated.", parent=self)
        except ValueError as error:
            messagebox.showwarning("Check Entry", str(error), parent=self)
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not update attendant:\n{error}", parent=self)

    def delete_attendant(self):
        if self.attendant_id is None:
            messagebox.showwarning("Select Attendant", "Select an attendant to delete.", parent=self)
            return
        if not self._authorize("delete this attendant"):
            return
        if not messagebox.askyesno("Delete Attendant", "Delete the selected attendant?", parent=self):
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                count = conn.execute("SELECT COUNT(*) FROM pump_sessions WHERE attendant_id=?",
                                     (self.attendant_id,)).fetchone()[0]
                if count:
                    raise ValueError("This attendant has session history. Keep the record for reporting; mark it inactive in the attendant setup instead.")
                conn.execute("DELETE FROM attendants WHERE id=?", (self.attendant_id,))
            self.load_attendants()
            self.clear_form()
        except ValueError as error:
            messagebox.showwarning("Cannot Delete", str(error), parent=self)
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not delete attendant:\n{error}", parent=self)

    def clear_form(self):
        self.attendant_id = None
        self.save_button.configure(text="Save New Attendant")
        self.name_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
        self.joined_entry.delete(0, "end")
        self.joined_entry.insert(0, format_display_date(date.today().isoformat()))
        self.salary_entry.delete(0, "end")
        self.payday_entry.delete(0, "end")

    def reconcile_shorts(self):
        if self.attendant_id is None:
            messagebox.showwarning(
                "Select Attendant", "Select an attendant first.", parent=self
            )
            return
        attendant_id = self.attendant_id
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            outstanding = attendant_short_outstanding(conn, attendant_id)
            name = conn.execute(
                "SELECT name FROM attendants WHERE id=?", (attendant_id,)
            ).fetchone()
        if not name:
            messagebox.showerror("Attendant", "The selected attendant no longer exists.", parent=self)
            return
        if outstanding <= 0:
            messagebox.showinfo(
                "No Outstanding Short",
                f"{name[0]} has no recorded short balance outstanding.",
                parent=self
            )
            return

        window = ctk.CTkToplevel(self)
        window.title(f"Reconcile Shorts — {name[0]}")
        window.geometry("520x480")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window,
            text=f"Outstanding recorded short: ₦{outstanding:,.2f}",
            font=Theme.SUBHEADING_FONT,
        ).pack(anchor="w", padx=16, pady=(16, 10))
        reduced = FormattedNumberEntry(
            window, placeholder_text="Amount to deduct from total shorts (NGN)"
        )
        reduced.pack(fill="x", padx=16, pady=6)
        recovered = FormattedNumberEntry(
            window, placeholder_text="Amount actually recovered as sales money (NGN)"
        )
        recovered.pack(fill="x", padx=16, pady=6)
        recovery_date = ctk.CTkEntry(window, placeholder_text="Recovery date")
        recovery_date.pack(fill="x", padx=16, pady=6)
        recovery_date.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(recovery_date)
        notes = ctk.CTkTextbox(window, height=150)
        notes.pack(fill="both", expand=True, padx=16, pady=6)

        ctk.CTkLabel(
            window,
            text=("The amount entered is deducted from this attendant's outstanding "
                  "short and reflected in reports. Any actual cash recovery is "
                  "entered separately and posted once to Station Cash. Original "
                  "session readings remain unchanged for audit."),
            wraplength=480, justify="left", text_color=Theme.TEXT_LIGHT
        ).pack(anchor="w", padx=16, pady=6)

        def save():
            try:
                amount = float(reduced.get().replace(",", "").strip())
                recovered_amount = float(recovered.get().replace(",", "").strip() or 0)
                if not messagebox.askyesno(
                    "Confirm Short Update",
                    f"Deduct ₦{amount:,.2f} from {name[0]}'s outstanding shorts "
                    f"and record ₦{recovered_amount:,.2f} actually received?",
                    parent=window
                ):
                    return
                reconcile_attendant_short(
                    DATABASE, attendant_id, amount, recovered_amount,
                    recovery_date.get(), notes.get("1.0", "end").strip()
                )
                self.load_attendants()
                window.destroy()
                messagebox.showinfo(
                    "Short Updated", "The amount was deducted from outstanding shorts.",
                    parent=self
                )
            except (ValueError, sqlite3.Error) as error:
                messagebox.showerror("Short Reconciliation", str(error), parent=window)

        Theme.primary_button(window, "Save Reconciliation", save).pack(pady=12)

    def process_salary(self):
        if self.attendant_id is None:
            messagebox.showwarning(
                "Select Attendant", "Select an attendant first.", parent=self
            )
            return
        attendant_id = self.attendant_id
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                preview = salary_preview(conn, attendant_id)
            if not preview["is_due"]:
                messagebox.showinfo(
                    "Salary Not Due",
                    f"{preview['name']}'s next salary date is "
                    f"{preview['payday'].strftime('%d-%m-%Y')}.",
                    parent=self,
                )
                return

            message = (
                f"Monthly base salary: ₦{preview['base_salary']:,.2f}\n"
                f"Outstanding shorts: ₦{preview['outstanding_short']:,.2f}\n"
                f"Session overages: ₦{preview['overage_total']:,.2f}\n"
                f"Overage offset against shorts: "
                f"₦{preview['overage_offset']:,.2f}\n"
                f"Short deducted from salary: "
                f"₦{preview['short_deduction']:,.2f}\n"
                f"Overage added to salary: "
                f"₦{preview['overage_credit']:,.2f}\n\n"
                f"Net salary to pay: ₦{preview['net_salary']:,.2f}"
            )
            if not self._authorize("confirm this salary payout"):
                return
            if not messagebox.askyesno(
                "Confirm Salary Payout", message, parent=self
            ):
                return
            process_salary_payment(DATABASE, attendant_id)
            self.load_attendants()
            messagebox.showinfo(
                "Salary Recorded",
                f"Salary payout of ₦{preview['net_salary']:,.2f} recorded. "
                "Short deductions and overage allocations are retained in "
                "the attendant's history.",
                parent=self,
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Salary Payout", str(error), parent=self)

    def open_salary_history(self):
        if self.attendant_id is None:
            messagebox.showwarning(
                "Select Attendant", "Select an attendant first.", parent=self
            )
            return
        attendant_id = self.attendant_id
        window = ctk.CTkToplevel(self)
        window.title("Attendant Salary History")
        window.geometry("980x520")
        window.transient(self.winfo_toplevel())
        columns = (
            "Payday", "Paid Date", "Base Salary", "Short Deduction",
            "Overage Offset", "Overage Added", "Net Salary", "Notes",
        )
        tree = ttk.Treeview(window, columns=columns, show="headings")
        for column, width in zip(
            columns, (100, 100, 125, 130, 125, 125, 125, 200)
        ):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_payroll_schema(conn)
                rows = conn.execute("""
                    SELECT payday,paid_date,base_salary,short_deduction,
                           overage_offset,overage_credit,net_salary,
                           COALESCE(notes,'')
                    FROM attendant_salary_payments
                    WHERE attendant_id=?
                    ORDER BY date(payday) DESC,id DESC
                """, (attendant_id,)).fetchall()
            for row in rows:
                tree.insert("", "end", values=(
                    format_display_date(row[0]),
                    format_display_date(row[1]),
                    *(f"₦{float(value or 0):,.2f}" for value in row[2:7]),
                    row[7],
                ))
        except sqlite3.Error as error:
            messagebox.showerror(
                "Salary History", str(error), parent=window
            )

    def open_short_history(self):
        if self.attendant_id is None:
            messagebox.showwarning(
                "Select Attendant", "Select an attendant first.", parent=self
            )
            return
        attendant_id = self.attendant_id
        window = ctk.CTkToplevel(self)
        window.title("Attendant Short History")
        window.geometry("900x580")
        window.transient(self.winfo_toplevel())
        tree = ttk.Treeview(
            window,
            columns=("Date", "Type", "Recorded NGN", "Reduced NGN",
                     "Recovered NGN", "Outstanding NGN", "Notes"),
            show="headings"
        )
        for column, width in zip(
            ("Date", "Type", "Recorded NGN", "Reduced NGN",
             "Recovered NGN", "Outstanding NGN", "Notes"),
            (110, 180, 130, 130, 130, 140, 260)
        ):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_reconciliation_schema(conn)
                balances = attendant_short_balances(conn, attendant_id)
                reconciliation_rows = conn.execute("""
                    SELECT id,recovery_date,reduced_amount,recovered_amount,
                           COALESCE(notes,'')
                    FROM attendant_short_reconciliations
                    WHERE attendant_id=? ORDER BY date(recovery_date),id
                """, (attendant_id,)).fetchall()
                sessions = {
                    row[0]: (row[1], row[2], max(row[2] - row[3], 0), row[3])
                    for row in balances
                }
                session_rows = conn.execute("""
                    SELECT id,session_date,COALESCE(short_over,0)
                    FROM pump_sessions
                    WHERE attendant_id=?
                    ORDER BY date(session_date),id
                """, (attendant_id,)).fetchall()
                for reconciliation_id, day, reduced_amount, recovered_amount, notes_text in reconciliation_rows:
                    tree.insert("", "end", values=(
                        format_display_date(day), "Short reconciliation", "",
                        f"₦{float(reduced_amount):,.2f}",
                        f"₦{float(recovered_amount):,.2f}", "",
                        notes_text
                    ))
                for session_id, day, short_over in session_rows:
                    recorded = float(short_over or 0)
                    _, _, allocated, outstanding = sessions.get(
                        session_id, (day, 0, 0, 0)
                    )
                    if recorded > 0:
                        recorded_display = f"+₦{recorded:,.2f}"
                        session_type = f"Pump session #{session_id} (overage)"
                        reduced_display = recovered_display = outstanding_display = ""
                    elif recorded < 0:
                        recorded_display = f"-₦{abs(recorded):,.2f}"
                        session_type = f"Pump session #{session_id} (short)"
                        reduced_display = f"₦{allocated:,.2f}"
                        recovered_display = ""
                        outstanding_display = f"₦{outstanding:,.2f}"
                    else:
                        recorded_display = "₦0.00"
                        session_type = f"Pump session #{session_id}"
                        reduced_display = recovered_display = outstanding_display = ""
                    tree.insert("", "end", values=(
                        format_display_date(day), session_type,
                        recorded_display, reduced_display, recovered_display,
                        outstanding_display,
                        "Original session balance retained for audit"
                    ))
        except sqlite3.Error as error:
            messagebox.showerror("Short History", str(error), parent=window)
        for item in self.tree.selection():
            self.tree.selection_remove(item)
