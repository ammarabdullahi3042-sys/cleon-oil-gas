import sqlite3
from datetime import date, datetime
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk
from account import (
    ensure_account_schema, list_accounts, save_standalone_account_expense,
    delete_standalone_account_expense,
)
from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from number_entry import FormattedNumberEntry


from app_settings import get_active_database

DATABASE = get_active_database()


class ExpenseWindow(ctk.CTkFrame):

    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)

        self.expense_id = None
        self.expense_source = None

        self.prepare_database()
        self.build_ui()
        self.refresh_source_accounts()
        self.load_expenses()

    def prepare_database(self):
        """Create the standalone expenses table if it does not exist."""
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_account_schema(conn)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS expenses (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        description TEXT NOT NULL,
                        amount REAL NOT NULL,
                        expense_date TEXT NOT NULL
                    )
                """)
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(expenses)")
                }
                if "source_account_id" not in columns:
                    conn.execute(
                        "ALTER TABLE expenses ADD COLUMN source_account_id INTEGER"
                    )
                if "account_transaction_id" not in columns:
                    conn.execute(
                        "ALTER TABLE expenses ADD COLUMN account_transaction_id INTEGER"
                    )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not prepare the database:\n{error}",
                parent=self
            )

    def build_ui(self):
        ctk.CTkLabel(
            self,
            text="Expense Management",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=12)

        self.description_entry = ctk.CTkEntry(
            self,
            placeholder_text="Standalone Expense Description"
        )
        self.description_entry.pack(
            fill="x",
            padx=20,
            pady=5
        )

        self.amount_entry = FormattedNumberEntry(
            self,
            placeholder_text="Amount (₦)"
        )
        self.amount_entry.pack(
            fill="x",
            padx=20,
            pady=5
        )

        self.date_entry = ctk.CTkEntry(
            self,
            placeholder_text="Expense Date (DD-MM-YY)"
        )
        self.date_entry.pack(
            fill="x",
            padx=20,
            pady=5
        )
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.date_entry)

        ctk.CTkLabel(
            self, text="Pay from account", font=Theme.BODY_FONT,
            text_color=Theme.TEXT_LIGHT
        ).pack(anchor="w", padx=20, pady=(5, 0))
        self.source_account = ctk.CTkOptionMenu(self, values=["Cash Vault"])
        self.source_account.pack(fill="x", padx=20, pady=5)
        self.source_account_choices = {}

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=8)

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Save Expense",
            command=self.save_expense
        )
        self.save_button.pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Update Selected",
            command=self.update_expense
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Delete Selected",
            fg_color="#b3261e",
            hover_color="#8c1d18",
            command=self.delete_expense
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Clear",
            command=self.clear_form
        ).pack(side="left", padx=5, pady=6)

        self.total_label = ctk.CTkLabel(
            self,
            text="Standalone: ₦0.00  |  Session: ₦0.00  |  Total: ₦0.00",
            font=("Segoe UI", 15, "bold")
        )
        self.total_label.pack(pady=8)

        columns = ("Record", "Date", "Description", "Amount", "Source")

        self.tree = ttk.Treeview(
            self,
            columns=columns,
            show="headings"
        )

        headings = {
            "Record": "Record",
            "Date": "Date",
            "Description": "Description",
            "Amount": "Amount (₦)",
            "Source": "Source"
        }

        widths = {
            "Record": 90,
            "Date": 150,
            "Description": 350,
            "Amount": 150,
            "Source": 150
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                anchor="center"
            )

        self.tree.tag_configure(
            "Standalone",
            background="#E8F5E9",
            foreground="#17202C",
        )
        self.tree.tag_configure(
            "Session",
            background="#E2E8F0",
            foreground="#17202C",
        )

        self.tree.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=10
        )
        self.tree.bind("<<TreeviewSelect>>", self.select_record)

        ctk.CTkLabel(
            self,
            text="Green rows are standalone expenses. Grey rows are pump-session expenses.",
            font=("Segoe UI", 11)
        ).pack(pady=(0, 10))

    def get_form_values(self):
        description = self.description_entry.get().strip()
        amount_text = self.amount_entry.get().strip()
        expense_date = self.date_entry.get().strip()

        if not description:
            raise ValueError("Enter an expense description.")

        try:
            amount = float(amount_text)
        except ValueError:
            raise ValueError("Enter a valid amount.")

        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        parsed_date = parse_flexible_date(expense_date)
        account_id = self.source_account_choices.get(self.source_account.get())
        if account_id is None:
            raise ValueError("Select the Cash Vault, POS, or bank account to pay from.")
        return description, amount, parsed_date.isoformat(), account_id

    def refresh_source_accounts(self):
        rows = sorted(
            list_accounts(active_only=True, database=DATABASE),
            key=lambda row: (
                row[2] != "CASH", row[1].casefold()
            )
        )
        self.source_account_choices = {}
        for account_id, name, account_type, *_rest in rows:
            label = (
                "Cash Vault" if account_type == "CASH"
                else f"{name} ({account_type})"
            )
            self.source_account_choices[label] = account_id
        values = list(self.source_account_choices) or ["No active accounts"]
        self.source_account.configure(values=values)
        current = self.source_account.get()
        self.source_account.set(
            current if current in self.source_account_choices
            else next(iter(self.source_account_choices), values[0])
        )

    def save_expense(self):
        if self.expense_id is not None and self.expense_source == "Standalone":
            self.update_expense()
            return
        try:
            description, amount, expense_date, account_id = self.get_form_values()
            save_standalone_account_expense(
                description, amount, expense_date, account_id, DATABASE
            )

            self.load_expenses()
            self.clear_form()

            messagebox.showinfo(
                "Saved",
                "Standalone expense saved successfully.",
                parent=self
            )

        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not save expense:\n{error}",
                parent=self
            )

    def update_expense(self):
        if self.expense_id is None or self.expense_source != "Standalone":
            messagebox.showwarning(
                "Select Standalone Expense",
                "Select a standalone expense row to update. "
                "Session expenses are changed in the Pump Session window.",
                parent=self
            )
            return

        if not self.authorize_change("update this expense"):
            return

        try:
            description, amount, expense_date, account_id = self.get_form_values()
            save_standalone_account_expense(
                description, amount, expense_date, account_id, DATABASE,
                expense_id=self.expense_id
            )

            self.load_expenses()
            self.clear_form()

            messagebox.showinfo(
                "Updated",
                "Standalone expense updated successfully.",
                parent=self
            )

        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not update expense:\n{error}",
                parent=self
            )

    def delete_expense(self):
        if self.expense_id is None or self.expense_source != "Standalone":
            messagebox.showwarning(
                "Select Standalone Expense",
                "Select a standalone expense row to delete. "
                "Session expenses are managed in the Pump Session window.",
                parent=self
            )
            return

        if not self.authorize_change("delete this expense"):
            return

        if not messagebox.askyesno(
            "Delete Expense",
            "Delete the selected standalone expense?",
            parent=self
        ):
            return

        try:
            delete_standalone_account_expense(self.expense_id, DATABASE)

            self.load_expenses()
            self.clear_form()

            messagebox.showinfo(
                "Deleted",
                "Standalone expense deleted.",
                parent=self
            )

        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror(
                "Database Error",
                f"Could not delete expense:\n{error}",
                parent=self
            )

    def load_expenses(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        standalone_total = 0.0
        session_total = 0.0

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT e.id,e.expense_date,e.description,e.amount,
                           e.source_account_id,a.account_name,a.account_type
                    FROM expenses e
                    LEFT JOIN accounts a ON a.id=e.source_account_id
                    ORDER BY e.expense_date, e.id
                """)
                standalone_rows = cursor.fetchall()

                for (record_id, expense_date, description, amount,
                     _source_id, account_name, account_type) in standalone_rows:
                    amount = float(amount or 0)
                    standalone_total += amount

                    self.tree.insert(
                        "",
                        "end",
                        iid=f"MANUAL-{record_id}",
                        values=(
                            f"M-{record_id}",
                            format_display_date(expense_date),
                            description,
                            f"₦{amount:,.2f}",
                            ("Cash Vault" if account_type == "CASH" else
                             f"{account_name} ({account_type})"
                             if account_name else "Legacy / unassigned")
                        ),
                        tags=("Standalone",)
                    )

                # Pump-session expenses are listed for reference.
                cursor.execute("""
                    SELECT
                        ps.id,
                        ps.session_date,
                        a.name,
                        ps.expenses
                    FROM pump_sessions AS ps
                    LEFT JOIN attendants AS a
                        ON ps.attendant_id = a.id
                    WHERE COALESCE(ps.expenses, 0) > 0
                    ORDER BY ps.session_date, ps.id
                """)
                session_rows = cursor.fetchall()

                for record_id, session_date, attendant_name, amount in session_rows:
                    amount = float(amount or 0)
                    session_total += amount

                    description = (
                        f"Pump session expense — {attendant_name or 'Attendant'}"
                    )

                    self.tree.insert(
                        "",
                        "end",
                        iid=f"SESSION-{record_id}",
                        values=(
                            f"S-{record_id}",
                            format_display_date(session_date),
                            description,
                            f"₦{amount:,.2f}",
                            "Session"
                        ),
                        tags=("Session",)
                    )

            grand_total = standalone_total + session_total

            self.total_label.configure(
                text=(
                    f"Standalone: ₦{standalone_total:,.2f}  |  "
                    f"Session: ₦{session_total:,.2f}  |  "
                    f"Total: ₦{grand_total:,.2f}"
                )
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load expense records:\n{error}",
                parent=self
            )

    def authorize_change(self, action):
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

    def select_record(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        item_id = selected[0]
        values = self.tree.item(item_id, "values")

        if item_id.startswith("SESSION-"):
            self.expense_id = None
            self.expense_source = "Session"
            self.save_button.configure(text="Save Expense")
            self.clear_entry_fields(keep_date=True)

            messagebox.showinfo(
                "Session Expense",
                "This expense belongs to a pump session. "
                "Edit it from the Pump Session window.",
                parent=self
            )
            return

        self.expense_source = "Standalone"
        self.expense_id = int(item_id.split("-", 1)[1])
        self.save_button.configure(text="Save Changes to Selected Expense")

        self.description_entry.delete(0, "end")
        self.description_entry.insert(0, values[2])

        self.amount_entry.delete(0, "end")
        amount_text = values[3].replace("₦", "").replace(",", "")
        self.amount_entry.insert(0, amount_text)

        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, format_display_date(values[1]))
        if values[4] in self.source_account_choices:
            self.source_account.set(values[4])

    def clear_entry_fields(self, keep_date=False):
        self.description_entry.delete(0, "end")
        self.amount_entry.delete(0, "end")

        if not keep_date:
            self.date_entry.delete(0, "end")
            self.date_entry.insert(0, format_display_date(date.today().isoformat()))

    def clear_form(self):
        self.expense_id = None
        self.expense_source = None
        self.save_button.configure(text="Save Expense")
        self.clear_entry_fields()
        self.refresh_source_accounts()

        for item in self.tree.selection():
            self.tree.selection_remove(item)
