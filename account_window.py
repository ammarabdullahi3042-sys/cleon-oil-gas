"""Independent POS, cash and bank account ledgers with per-account reconciliation."""
import sqlite3
from datetime import date, datetime
from tkinter import filedialog, messagebox, ttk
import customtkinter as ctk

from theme import Theme
from account import (
    LEDGER_TYPES, ensure_account_schema, list_accounts, save_account,
    set_account_active, named_account_balances, record_transfer,
    daily_cash_pos_reconciliation, save_standalone_account_expense,
    update_account_transaction, delete_account_transaction,
)
from price_management import PriceManagementWindow
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from app_settings import get_active_database
from short_reconciliation import ensure_reconciliation_schema
from number_entry import FormattedNumberEntry
from supplier_records import ensure_supplier_schema

DATABASE = get_active_database()


class AccountManagerWindow(ctk.CTkToplevel):
    """Create and maintain named POS and bank accounts."""
    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change
        self.selected_id = None
        self.title("Manage POS and Bank Accounts")
        self.geometry("850x560")
        self.transient(master)
        self.build_ui()
        self.refresh()

    def build_ui(self):
        ctk.CTkLabel(self, text="Account Register", font=Theme.TITLE_FONT).pack(pady=(16, 6))
        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=16, pady=8)
        self.name = ctk.CTkEntry(form, placeholder_text="Account name / POS terminal name")
        self.name.grid(row=0, column=0, padx=6, pady=8, sticky="ew")
        self.kind = ctk.CTkOptionMenu(form, values=["BANK", "POS"])
        self.kind.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        self.number = ctk.CTkEntry(form, placeholder_text="Account / terminal number")
        self.number.grid(row=0, column=2, padx=6, pady=8, sticky="ew")
        self.provider = ctk.CTkEntry(form, placeholder_text="Bank / POS provider")
        self.provider.grid(row=0, column=3, padx=6, pady=8, sticky="ew")
        for i in range(4): form.grid_columnconfigure(i, weight=1)
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=16)
        Theme.primary_button(actions, "Add Account", self.add).pack(side="left", padx=4)
        Theme.secondary_button(actions, "Update Selected", self.update).pack(side="left", padx=4)
        Theme.secondary_button(actions, "Activate / Deactivate", self.toggle).pack(side="left", padx=4)
        self.tree = ttk.Treeview(self, columns=("ID", "Name", "Type", "Number", "Provider", "Status"), show="headings")
        for c, w in zip(("ID", "Name", "Type", "Number", "Provider", "Status"), (55, 210, 80, 170, 160, 100)):
            self.tree.heading(c, text=c); self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=16, pady=12)
        self.tree.bind("<<TreeviewSelect>>", self.select)

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in list_accounts(database=DATABASE):
            if row[2] != "CASH":
                self.tree.insert("", "end", iid=str(row[0]), values=(row[0], row[1], row[2], row[3], row[4], "Active" if row[5] else "Inactive"))

    def select(self, _event=None):
        chosen = self.tree.selection()
        if not chosen: return
        row = self.tree.item(chosen[0], "values")
        self.selected_id = int(row[0])
        for entry, value in ((self.name, row[1]), (self.number, row[3]), (self.provider, row[4])):
            entry.delete(0, "end"); entry.insert(0, value)
        self.kind.set(row[2])

    def add(self):
        try:
            save_account(self.name.get(), self.kind.get(), self.number.get(), self.provider.get(), database=DATABASE)
            self.refresh()
            if self.on_change: self.on_change()
            messagebox.showinfo("Account saved", "The new account is ready for transactions.", parent=self)
        except (ValueError, sqlite3.Error) as error: messagebox.showerror("Account", str(error), parent=self)

    def update(self):
        if not self.selected_id:
            messagebox.showwarning("Select account", "Select an account to update.", parent=self); return
        try:
            save_account(self.name.get(), self.kind.get(), self.number.get(), self.provider.get(), self.selected_id, DATABASE)
            self.refresh()
            if self.on_change: self.on_change()
        except (ValueError, sqlite3.Error) as error: messagebox.showerror("Account", str(error), parent=self)

    def toggle(self):
        if not self.selected_id:
            messagebox.showwarning("Select account", "Select an account first.", parent=self); return
        active = self.tree.item(str(self.selected_id), "values")[5] == "Active"
        try:
            set_account_active(self.selected_id, not active, DATABASE)
            self.refresh()
            if self.on_change: self.on_change()
        except (ValueError, sqlite3.Error) as error: messagebox.showerror("Account", str(error), parent=self)


class DailyReconciliationWindow(ctk.CTkToplevel):
    """Compare pump-session cash/POS with entered amounts and bank movements."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Daily Cash & POS Reconciliation")
        self.geometry("1320x680")
        self.transient(master)
        self.build_ui()
        self.refresh()

    def build_ui(self):
        ctk.CTkLabel(
            self, text="Daily Cash & POS Reconciliation",
            font=Theme.TITLE_FONT, text_color=Theme.TEXT,
        ).pack(anchor="w", padx=18, pady=(14, 4))
        ctk.CTkLabel(
            self,
            text=("Expected = pump-session Cash + POS, less Cash Vault expenses. "
                  "Session expenses are already included in pump-session sales and are not "
                  "deducted again. Reconciliation is balanced when either moved-out funds "
                  "or Cash Vault count plus POS receipts equals expected. Actual includes "
                  "funds remaining in receiving bank accounts. Otherwise, "
                  "Short/Over is actual minus expected (short is negative; over is positive). "
                  "Remaining is the outstanding attendant short/over total after reconciliations."),
            font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT,
            wraplength=1260, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 8))

        filters = Theme.card(self)
        filters.pack(fill="x", padx=16, pady=6)
        ctk.CTkLabel(filters, text="From").pack(side="left", padx=(12, 4), pady=10)
        self.from_entry = ctk.CTkEntry(filters, width=135,
                                       placeholder_text="DD-MM-YY")
        self.from_entry.pack(side="left", padx=4, pady=8)
        self.from_entry.insert(0, format_display_date(date.today().replace(day=1).isoformat()))
        attach_date_picker(self.from_entry)
        ctk.CTkLabel(filters, text="To").pack(side="left", padx=(10, 4), pady=10)
        self.to_entry = ctk.CTkEntry(filters, width=135,
                                     placeholder_text="DD-MM-YY")
        self.to_entry.pack(side="left", padx=4, pady=8)
        self.to_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.to_entry)
        Theme.primary_button(filters, "Refresh", self.refresh, width=105).pack(
            side="left", padx=10, pady=7)
        Theme.secondary_button(
            filters, "Export Excel", self.export_excel, width=125
        ).pack(side="left", padx=4, pady=7)

        self.summary = ctk.CTkLabel(
            self, text="", font=Theme.BODY_BOLD_FONT, text_color=Theme.TEXT
        )
        self.summary.pack(anchor="w", padx=20, pady=(5, 7))

        table_frame = ctk.CTkFrame(self, fg_color=Theme.SURFACE,
                                   corner_radius=Theme.CARD_RADIUS)
        table_frame.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        columns = (
            "Date", "Expected Cash + POS", "Cash Expenses",
            "Expected After Expenses", "Cash Vault Count", "POS Received",
            "Actual Cash + POS + Bank", "Short / Over", "Moved Out", "Remaining",
            "Status",
        )
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        widths = (110, 150, 125, 160, 145, 135, 150, 135, 135, 135, 120)
        for column, width in zip(columns, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=100, anchor="center")
        self.tree.tag_configure("SHORT", foreground=Theme.DANGER)
        self.tree.tag_configure("OVER", foreground=Theme.SUCCESS)
        self.tree.tag_configure("PENDING", foreground=Theme.WARNING)
        self.tree.tag_configure("COUNT REQUIRED", foreground=Theme.WARNING)
        self.tree.tag_configure("BALANCED", foreground=Theme.SUCCESS)
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(7, 0), pady=(7, 0))
        ybar.grid(row=0, column=1, sticky="ns", padx=(0, 7), pady=(7, 0))
        xbar.grid(row=1, column=0, sticky="ew", padx=(7, 0), pady=(0, 7))
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)

    def refresh(self):
        try:
            start = parse_flexible_date(self.from_entry.get()).isoformat()
            end = parse_flexible_date(self.to_entry.get()).isoformat()
            if start > end:
                raise ValueError("From date cannot be later than To date.")
            rows = daily_cash_pos_reconciliation(start, end, DATABASE)
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                (day, expected_total, cash_expenses, expected_after_expenses,
                 cash_count, pos_received, actual_total, short_over,
                 moved_out, remaining, status) = row
                self.tree.insert("", "end", values=(
                    format_display_date(day),
                    f"₦{expected_total:,.2f}",
                    f"₦{cash_expenses:,.2f}",
                    f"₦{expected_after_expenses:,.2f}",
                    "" if cash_count is None else f"₦{cash_count:,.2f}",
                    f"₦{pos_received:,.2f}",
                    "" if actual_total is None else f"₦{actual_total:,.2f}",
                    "" if short_over is None else f"₦{short_over:+,.2f}",
                    f"₦{moved_out:,.2f}", f"₦{remaining:,.2f}", status,
                ), tags=(status,))
            expected_sum = sum(row[3] for row in rows)
            checked_rows = [row for row in rows if row[6] is not None]
            actual_sum = sum(row[6] for row in checked_rows)
            variance_sum = sum(row[7] for row in checked_rows)
            moved_sum = sum(row[8] for row in rows)
            remaining_sum = sum(row[9] for row in rows)
            self.summary.configure(
                text=(f"Expected: ₦{expected_sum:,.2f}     "
                      f"Actual Funds: ₦{actual_sum:,.2f}     "
                      f"Short / Over: ₦{variance_sum:+,.2f}     "
                      f"Moved out: ₦{moved_sum:,.2f}     "
                      f"Remaining: ₦{remaining_sum:,.2f}")
            )
            return True
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Reconciliation Error", str(error), parent=self)
            return False

    def export_excel(self):
        try:
            if not self.refresh():
                return
            start = parse_flexible_date(self.from_entry.get()).isoformat()
            end = parse_flexible_date(self.to_entry.get()).isoformat()
            if start > end:
                raise ValueError("From date cannot be later than To date.")

            path = filedialog.asksaveasfilename(
                parent=self,
                title="Export daily reconciliation as Excel",
                defaultextension=".xlsx",
                initialfile=f"daily_reconciliation_{start}_to_{end}.xlsx",
                filetypes=[("Excel workbooks", "*.xlsx")],
            )
            if not path:
                return

            from export_utils import export_excel as write_cleon_excel

            write_cleon_excel(
                path,
                "Daily Cash & POS Reconciliation",
                self.tree["columns"],
                [
                    self.tree.item(item, "values")
                    for item in self.tree.get_children()
                ],
                (start, end),
            )
            messagebox.showinfo(
                "Export Complete",
                "CLEON formatted daily reconciliation workbook saved.",
                parent=self,
            )
        except (ValueError, sqlite3.Error, OSError, ImportError) as error:
            messagebox.showerror("Export Error", str(error), parent=self)


class SupplierManagerWindow(ctk.CTkToplevel):
    """Maintain supplier contacts and bank details for fuel payments."""

    def __init__(self, master, on_change=None):
        super().__init__(master)
        self.on_change = on_change
        self.selected_id = None
        self.title("Supplier Register")
        self.geometry("1050x620")
        self.transient(master.winfo_toplevel())
        self.build_ui()
        self.refresh()

    def build_ui(self):
        ctk.CTkLabel(
            self, text="Supplier Register", font=Theme.TITLE_FONT,
            text_color=Theme.TEXT,
        ).pack(anchor="w", padx=18, pady=(16, 5))
        ctk.CTkLabel(
            self,
            text="Supplier bank details appear when recording a product payment.",
            font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT,
        ).pack(anchor="w", padx=20, pady=(0, 8))

        form = Theme.card(self)
        form.pack(fill="x", padx=16, pady=6)
        fields = (
            ("name_entry", "Supplier name"),
            ("phone_entry", "Contact phone"),
            ("bank_entry", "Bank name"),
            ("account_name_entry", "Bank account name"),
            ("account_number_entry", "Bank account number"),
        )
        for index, (attribute, placeholder) in enumerate(fields):
            entry = ctk.CTkEntry(form, placeholder_text=placeholder)
            setattr(self, attribute, entry)
            entry.grid(
                row=index // 3, column=index % 3,
                padx=7, pady=7, sticky="ew",
            )
        for column in range(3):
            form.grid_columnconfigure(column, weight=1)
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=2, column=0, columnspan=3, pady=(2, 8))
        Theme.primary_button(actions, "Add Supplier", self.save_supplier).pack(
            side="left", padx=4
        )
        Theme.secondary_button(
            actions, "Update Selected", self.update_supplier
        ).pack(
            side="left", padx=4
        )
        Theme.secondary_button(actions, "Clear", self.clear_form).pack(
            side="left", padx=4
        )

        columns = (
            "Supplier", "Contact Phone", "Bank", "Account Name",
            "Account Number",
        )
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for column, width in zip(columns, (220, 160, 160, 230, 190)):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=16, pady=(5, 16))
        self.tree.bind("<<TreeviewSelect>>", self.select_supplier)

    def refresh(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_supplier_schema(conn)
                rows = conn.execute("""
                    SELECT id,name,contact_phone,bank_name,
                           bank_account_name,bank_account_number
                    FROM suppliers ORDER BY name COLLATE NOCASE
                """).fetchall()
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                self.tree.insert("", "end", iid=str(row[0]), values=row[1:])
        except sqlite3.Error as error:
            messagebox.showerror("Supplier Register", str(error), parent=self)

    def select_supplier(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        self.selected_id = int(selected[0])
        row = self.tree.item(selected[0], "values")
        for entry, value in zip(
            (
                self.name_entry, self.phone_entry, self.bank_entry,
                self.account_name_entry, self.account_number_entry,
            ),
            row,
        ):
            entry.delete(0, "end")
            entry.insert(0, value)

    def clear_form(self):
        self.selected_id = None
        self.tree.selection_remove(self.tree.selection())
        for entry in (
            self.name_entry, self.phone_entry, self.bank_entry,
            self.account_name_entry, self.account_number_entry,
        ):
            entry.delete(0, "end")

    def _supplier_values(self):
        name = self.name_entry.get().strip()
        if not name:
            raise ValueError("Enter the supplier name.")
        return (
            name,
            self.phone_entry.get().strip(),
            self.bank_entry.get().strip(),
            self.account_name_entry.get().strip(),
            self.account_number_entry.get().strip(),
        )

    def save_supplier(self):
        try:
            values = self._supplier_values()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_supplier_schema(conn)
                conn.execute("""
                    INSERT INTO suppliers(
                        name,contact_phone,bank_name,bank_account_name,
                        bank_account_number
                    ) VALUES(?,?,?,?,?)
                """, values)
            self.refresh()
            self.clear_form()
            if self.on_change:
                self.on_change()
        except ValueError as error:
            messagebox.showwarning("Supplier Register", str(error), parent=self)
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Supplier Register",
                "A supplier with that name already exists.",
                parent=self,
            )
        except sqlite3.Error as error:
            messagebox.showerror("Supplier Register", str(error), parent=self)

    def update_supplier(self):
        if self.selected_id is None:
            messagebox.showwarning(
                "Supplier Register",
                "Select a supplier to update.",
                parent=self,
            )
            return
        try:
            values = self._supplier_values()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_supplier_schema(conn)
                cursor = conn.execute("""
                    UPDATE suppliers SET name=?,contact_phone=?,bank_name=?,
                        bank_account_name=?,bank_account_number=?
                    WHERE id=?
                """, (*values, self.selected_id))
                if cursor.rowcount != 1:
                    raise ValueError(
                        "The selected supplier no longer exists."
                    )
            self.refresh()
            self.clear_form()
            if self.on_change:
                self.on_change()
        except ValueError as error:
            messagebox.showwarning("Supplier Register", str(error), parent=self)
        except sqlite3.IntegrityError:
            messagebox.showwarning(
                "Supplier Register",
                "A supplier with that name already exists.",
                parent=self,
            )
        except sqlite3.Error as error:
            messagebox.showerror("Supplier Register", str(error), parent=self)


class AccountWindow(ctk.CTkFrame):
    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)
        Theme.setup()
        self.account_choices = {}
        self.target_choices = {}
        self.receipt_choices = {}
        self.receipt_payees = {}
        self._account_rows = []
        self.build_ui()
        self.refresh()

    def build_ui(self):
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.pack(fill="x", padx=18, pady=(12, 2))
        ctk.CTkLabel(heading, text="Accounts & Reconciliation", font=Theme.TITLE_FONT, text_color=Theme.TEXT).pack(side="left")
        Theme.secondary_button(heading, "Daily Reconciliation", self.open_daily_reconciliation, width=185).pack(side="right", padx=5)
        Theme.secondary_button(heading, "Suppliers", self.open_supplier_manager, width=110).pack(side="right", padx=5)
        Theme.primary_button(heading, "Manage POS / Bank Accounts", self.open_account_manager, width=220).pack(side="right", padx=5)
        Theme.secondary_button(heading, "Selling Prices", self.open_price_management, width=130).pack(side="right", padx=5)
        ctk.CTkLabel(self, text="Each POS terminal and company bank account is reconciled separately. Account balances come only from transactions posted to that account.", font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT, wraplength=1250).pack(anchor="w", padx=22, pady=(0, 8))

        filters = Theme.card(self); filters.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(filters, text="From").pack(side="left", padx=(10, 3), pady=8)
        self.from_entry = ctk.CTkEntry(filters, width=125, placeholder_text="DD/MM/YY"); self.from_entry.pack(side="left", padx=4); self.from_entry.insert(0, format_display_date(date.today().replace(day=1).isoformat()))
        attach_date_picker(self.from_entry)
        ctk.CTkLabel(filters, text="To").pack(side="left", padx=(8, 3))
        self.to_entry = ctk.CTkEntry(filters, width=125, placeholder_text="DD/MM/YY"); self.to_entry.pack(side="left", padx=4); self.to_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.to_entry)
        Theme.primary_button(filters, "Refresh", self.refresh, width=100).pack(side="left", padx=8, pady=6)

        self.balance_frame = Theme.card(self); self.balance_frame.pack(fill="x", padx=18, pady=5)
        self.balance_tree = ttk.Treeview(self.balance_frame, columns=("Account", "Type", "Number", "Provider", "Book Balance", "Status"), show="headings", height=4)
        for c, w in zip(("Account", "Type", "Number", "Provider", "Book Balance", "Status"), (250, 90, 190, 170, 170, 90)):
            self.balance_tree.heading(c, text=c); self.balance_tree.column(c, width=w, anchor="center")
        self.balance_tree.pack(fill="x", padx=7, pady=7)
        self.balance_summary_label = ctk.CTkLabel(
            self.balance_frame,
            text=("Cash Vault: ₦0.00     POS Accounts: ₦0.00     "
                  "POS Expected from Pump Sessions: ₦0.00     Bank Balance: ₦0.00"),
            font=Theme.SUBHEADING_FONT,
            text_color=Theme.TEXT,
        )
        self.balance_summary_label.pack(anchor="w", padx=12, pady=(0, 4))
        self.total_sales_label = ctk.CTkLabel(
            self.balance_frame,
            text="Total Sales (all days): ₦0.00",
            font=Theme.SUBHEADING_FONT,
            text_color=Theme.SUCCESS,
        )
        self.total_sales_label.pack(anchor="w", padx=12, pady=(0, 8))

        form = Theme.card(self); form.pack(fill="x", padx=18, pady=6)
        ctk.CTkLabel(form, text="Record account activity", font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT).grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(8, 2))
        self.type_menu = ctk.CTkOptionMenu(form, values=list(LEDGER_TYPES), command=self.on_type_change, width=210)
        self.type_menu.grid(row=1, column=0, padx=6, pady=7, sticky="ew")
        self.date_input = ctk.CTkEntry(form, placeholder_text="Date DD-MM-YY", width=135); self.date_input.grid(row=1, column=1, padx=6, pady=7, sticky="ew"); self.date_input.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.date_input)
        self.amount_input = FormattedNumberEntry(form, placeholder_text="Amount (NGN)", width=145); self.amount_input.grid(row=1, column=2, padx=6, pady=7, sticky="ew")
        self.account_menu = ctk.CTkOptionMenu(form, values=["Select account"], width=190); self.account_menu.grid(row=1, column=3, padx=6, pady=7, sticky="ew")
        self.target_menu = ctk.CTkOptionMenu(form, values=["Select destination"], width=190); self.target_menu.grid(row=1, column=4, padx=6, pady=7, sticky="ew")
        self.reference_input = ctk.CTkEntry(form, placeholder_text="Beneficiary / narration", width=210); self.reference_input.grid(row=1, column=5, padx=6, pady=7, sticky="ew")
        # A destination account is only needed for transfers. Hide the second
        # account selector for other transaction types to avoid duplicate choices.
        self.target_menu.grid_remove()
        self.reference_input.grid_configure(column=4)
        self.product_receipt_menu = ctk.CTkOptionMenu(
            form, values=["Select fuel receipt"], width=470,
            command=self.on_product_receipt_selected,
        )
        self.product_receipt_menu.grid(
            row=3, column=1, columnspan=4, padx=6, pady=5, sticky="ew"
        )
        self.product_receipt_menu.grid_remove()
        self.transaction_hint = ctk.CTkLabel(
            form, text="", font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT,
            anchor="w", wraplength=1150,
        )
        self.transaction_hint.grid(
            row=2, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 3)
        )
        Theme.primary_button(form, "Save Transaction", self.save_transaction, width=150).grid(row=4, column=0, columnspan=6, pady=(0, 8))
        for i in range(6): form.grid_columnconfigure(i, weight=1)
        self.on_type_change(self.type_menu.get())

        table_frame = ctk.CTkFrame(self, fg_color=Theme.SURFACE, corner_radius=Theme.CARD_RADIUS)
        table_frame.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        transaction_actions = ctk.CTkFrame(table_frame, fg_color="transparent")
        transaction_actions.grid(row=0, column=0, columnspan=2, sticky="ew",
                                 padx=7, pady=(7, 0))
        Theme.secondary_button(
            transaction_actions, "Edit Selected", self.edit_selected_transaction,
            width=140,
        ).pack(side="left", padx=(0, 6))
        Theme.secondary_button(
            transaction_actions, "Delete Selected", self.delete_selected_transaction,
            width=140,
        ).pack(side="left")
        columns = ("Date", "Type", "Account / Route", "Amount", "Reference")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings")
        for col, width in zip(columns, (120, 200, 300, 150, 280)):
            self.tree.heading(col, text=col); self.tree.column(col, width=width, minwidth=90, anchor="center")
        self.tree.tag_configure("inflow", foreground=Theme.SUCCESS); self.tree.tag_configure("outflow", foreground=Theme.DANGER); self.tree.tag_configure("transfer", foreground=Theme.TEXT_LIGHT)
        ybar = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview); xbar = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(7, 0), pady=(7, 0)); ybar.grid(row=1, column=1, sticky="ns", padx=(0, 7), pady=(7, 0)); xbar.grid(row=2, column=0, sticky="ew", padx=(7, 0), pady=(0, 7))
        table_frame.grid_rowconfigure(1, weight=1); table_frame.grid_columnconfigure(0, weight=1)

    def _range(self):
        try:
            start = parse_flexible_date(self.from_entry.get())
            end = parse_flexible_date(self.to_entry.get())
        except ValueError as error: raise ValueError(str(error))
        if start > end: raise ValueError("From date cannot be later than To date.")
        return start.isoformat(), end.isoformat()

    def on_type_change(self, selected):
        needs_target = selected in ("Account Transfer", "Bank Deposit")
        if selected == "Bank Deposit":
            self.transaction_hint.configure(
                text=("Bank Deposit moves funds from the Cash Vault to a bank account. "
                      "To move POS funds, choose Account Transfer and select the POS "
                      "account as the source and a bank account as the destination.")
            )
        elif selected == "Account Transfer":
            self.transaction_hint.configure(
                text=("Account Transfer moves funds internally between accounts, "
                      "including POS to bank.")
            )
        else:
            self.transaction_hint.configure(text="")
        if needs_target:
            self.target_menu.grid()
            self.reference_input.grid_configure(column=5)
        else:
            self.target_menu.grid_remove()
            self.reference_input.grid_configure(column=4)
        self.target_menu.configure(state="normal")
        if selected == "Product Payment":
            self.product_receipt_menu.grid()
            self.on_product_receipt_selected(self.product_receipt_menu.get())
        else:
            self.product_receipt_menu.grid_remove()
        allowed_type = None
        if selected in ("Account Receipt", "Cash Count", "Cash Expense", "Bank Deposit"):
            allowed_type = "CASH"
        elif selected == "POS Transaction":
            allowed_type = "POS"
        if selected == "Account Expense":
            rows = [row for row in self._account_rows
                    if row[2] in ("POS", "BANK")]
        else:
            rows = [row for row in self._account_rows
                    if not allowed_type or row[2] == allowed_type]
        self.account_choices = {f"{row[0]} | {row[1]} ({row[2]})": row[0] for row in rows}
        account_values = list(self.account_choices) or ["No matching account"]
        self.account_menu.configure(values=account_values)
        self.account_menu.set(account_values[0])

        target_rows = [r for r in self._account_rows
                       if selected != "Bank Deposit" or r[2] == "BANK"]
        self.target_choices = {f"{r[0]} | {r[1]} ({r[2]})": r[0]
                               for r in target_rows}
        target_values = list(self.target_choices) or ["No destination account"]
        self.target_menu.configure(values=target_values)
        self.target_menu.set(target_values[0])

    def refresh_account_menus(self):
        self._account_rows = [r for r in list_accounts(active_only=True, database=DATABASE)]
        self.target_choices = {f"{r[0]} | {r[1]} ({r[2]})": r[0] for r in self._account_rows}
        target_values = list(self.target_choices) or ["No accounts — create one"]
        self.target_menu.configure(values=target_values); self.target_menu.set(target_values[0])
        self.on_type_change(self.type_menu.get())
        self.refresh_product_receipts()

    def refresh_product_receipts(self):
        self.receipt_choices = {}
        self.receipt_payees = {}
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            ensure_account_schema(conn)
            ensure_reconciliation_schema(conn)
            ensure_supplier_schema(conn)
            rows = conn.execute("""
                SELECT fr.id,COALESCE(fr.product,'Fuel'),
                       COALESCE(s.name,fr.supplier_name,''),
                       COALESCE(fr.total_cost,0),
                       COALESCE((SELECT SUM(rs.station_borne_cost)
                                 FROM receipt_short_reconciliations rs
                                 WHERE rs.receipt_id=fr.id),0),
                       COALESCE(SUM(at.amount),0),
                       COALESCE(s.contact_phone,''),COALESCE(s.bank_name,''),
                       COALESCE(s.bank_account_name,''),
                       COALESCE(s.bank_account_number,'')
                FROM fuel_receipts fr
                LEFT JOIN suppliers s ON s.id=fr.supplier_id
                LEFT JOIN account_transactions at
                  ON at.receipt_id=fr.id
                 AND at.transaction_type='Product Payment'
                GROUP BY fr.id
                ORDER BY date(fr.receipt_date),fr.id
            """).fetchall()
        for (
            receipt_id, product, supplier, cost, station_cost, paid,
            contact_phone, bank_name, account_name, account_number,
        ) in rows:
            due = max(
                float(cost or 0) + float(station_cost or 0)
                - float(paid or 0), 0
            )
            self.receipt_payees[receipt_id] = (
                supplier, contact_phone, bank_name, account_name,
                account_number,
            )
            if due > 0.005:
                self.receipt_choices[
                    f"#{receipt_id} {product} — {supplier} — "
                    f"Bank: {bank_name or 'Not set'} | "
                    f"Account name: {account_name or 'Not set'} | "
                    f"Account no.: {account_number or 'Not set'} | "
                    f"Due ₦{due:,.2f}"
                ] = receipt_id
        values = list(self.receipt_choices) or ["No unpaid fuel receipts"]
        self.product_receipt_menu.configure(values=values)
        self.product_receipt_menu.set(values[0])
        if self.type_menu.get() == "Product Payment":
            self.on_product_receipt_selected(values[0])

    def on_product_receipt_selected(self, selection):
        receipt_id = self.receipt_choices.get(selection)
        if receipt_id is None:
            self.transaction_hint.configure(
                text="Select an unpaid fuel receipt to see its supplier payment details."
            )
            return
        supplier, contact_phone, bank_name, account_name, account_number = (
            self.receipt_payees.get(receipt_id, ("", "", "", "", ""))
        )
        supplier_details = [
            f"Supplier: {supplier or 'Not set'}",
            f"Receipt: #{receipt_id}",
            f"Contact: {contact_phone or 'Not set'}",
            f"Bank: {bank_name or 'Not set'}",
            f"Account name: {account_name or 'Not set'}",
            f"Account number: {account_number or 'Not set'}",
        ]
        self.transaction_hint.configure(
            text="Product payment will be linked to this receipt and supplier:\n"
            + " | ".join(supplier_details)
        )

    def refresh(self):
        try:
            start, end = self._range()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_account_schema(conn)
                ensure_supplier_schema(conn)
                rows = conn.execute("""SELECT at.transaction_date,
                    at.transaction_type,COALESCE(at.bank_name,''),at.amount,
                    COALESCE(at.reference,''),
                    at.receipt_id,COALESCE(s.name,fr.supplier_name,''),at.id
                    FROM account_transactions at
                    LEFT JOIN fuel_receipts fr ON fr.id=at.receipt_id
                    LEFT JOIN suppliers s ON s.id=fr.supplier_id
                    WHERE date(at.transaction_date) BETWEEN date(?) AND date(?)
                    ORDER BY date(at.transaction_date),at.id""", (start, end)).fetchall()
            self.refresh_account_menus()
            self.balance_tree.delete(*self.balance_tree.get_children())
            totals = {"CASH": 0.0, "POS": 0.0, "BANK": 0.0}
            for row in named_account_balances(end, DATABASE):
                if not row[6]: continue
                totals[row[2]] = totals.get(row[2], 0.0) + row[5]
                account_name = "Cash Vault" if row[2] == "CASH" else row[1]
                self.balance_tree.insert("", "end", values=(account_name, row[2], row[3], row[4], f"₦{row[5]:,.2f}", "Active"))
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                total_sales, pos_expected = conn.execute("""
                    SELECT
                        (SELECT COALESCE(SUM(sale_amount),0)
                         FROM pump_sessions),
                        MAX(
                            COALESCE((
                                SELECT SUM(pos_amount)
                                FROM pump_sessions
                                WHERE date(session_date)<=date(?)
                            ),0)
                            - COALESCE((
                                SELECT SUM(at.amount)
                                FROM account_transactions at
                                JOIN accounts source ON source.id=at.account_id
                                WHERE source.account_type='POS'
                                  AND at.transaction_type IN (
                                      'POS Settlement','Account Transfer',
                                      'Account Payment / Amount Sent',
                                      'Account Expense','Product Payment'
                                  )
                                  AND date(at.transaction_date)<=date(?)
                            ),0),
                            0
                        )
                """, (end, end)).fetchone()
            self.balance_summary_label.configure(
                text=(f"Cash Vault: ₦{totals['CASH']:,.2f}     "
                      f"POS Accounts: ₦{totals['POS']:,.2f}     "
                      f"POS Expected from Pump Sessions: "
                      f"₦{float(pos_expected or 0):,.2f}     "
                      f"Bank Balance: ₦{totals['BANK']:,.2f}")
            )
            self.total_sales_label.configure(
                text=f"Total Sales (all days): ₦{float(total_sales or 0):,.2f}"
            )
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                typ = row[1]
                tag = "outflow" if typ in (
                    "Account Payment / Amount Sent", "Cash Expense",
                    "Account Expense", "Product Payment",
                ) else ("transfer" if typ in ("Account Transfer", "Bank Deposit")
                       else "inflow")
                reference = row[4]
                if typ == "Product Payment" and row[5] is not None:
                    reference = (
                        f"Receipt #{row[5]} — {row[6]} — {reference}"
                    )
                self.tree.insert("", "end", iid=str(row[7]), values=(
                    format_display_date(row[0]), typ, row[2], f"₦{float(row[3] or 0):,.2f}",
                    reference
                ), tags=(tag,))
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Accounts Error", str(error), parent=self)

    def save_transaction(self):
        try:
            transaction_date = parse_flexible_date(self.date_input.get()).isoformat()
            amount = float(self.amount_input.get().replace(",", "").strip())
            account_id = self.account_choices.get(self.account_menu.get())
            target_id = self.target_choices.get(self.target_menu.get()) if self.type_menu.get() in ("Account Transfer", "Bank Deposit") else None
            if not account_id: raise ValueError("Create and select an account first.")
            receipt_id = (
                self.receipt_choices.get(self.product_receipt_menu.get())
                if self.type_menu.get() == "Product Payment" else None
            )
            if self.type_menu.get() == "Product Payment" and not receipt_id:
                raise ValueError("Select an unpaid fuel receipt for the product payment.")
            record_transfer(self.type_menu.get(), amount, transaction_date, reference=self.reference_input.get().strip(), database=DATABASE, account_id=account_id, target_account_id=target_id, receipt_id=receipt_id)
            self.amount_input.delete(0, "end"); self.reference_input.delete(0, "end")
            self.refresh_product_receipts()
            self.refresh(); messagebox.showinfo("Saved", "Transaction posted to the selected account ledger.", parent=self)
        except (ValueError, sqlite3.Error) as error: messagebox.showerror("Check Entry", str(error), parent=self)

    def edit_selected_transaction(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Select transaction", "Select an account transaction to edit.",
                parent=self,
            )
            return
        transaction_id = int(selected[0])
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT transaction_date,transaction_type,amount,
                           COALESCE(bank_name,''),COALESCE(reference,'')
                    FROM account_transactions WHERE id=?
                """, (transaction_id,)).fetchone()
            if not row:
                raise ValueError("The selected transaction no longer exists.")
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Transaction Error", str(error), parent=self)
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Edit Account Transaction")
        dialog.geometry("440x340")
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()
        ctk.CTkLabel(
            dialog, text=f"{row[1]} — {row[3]}",
            font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT,
        ).pack(anchor="w", padx=20, pady=(18, 8))

        ctk.CTkLabel(dialog, text="Date").pack(anchor="w", padx=20)
        date_entry = ctk.CTkEntry(dialog, placeholder_text="DD-MM-YY")
        date_entry.pack(fill="x", padx=20, pady=(3, 10))
        date_entry.insert(0, format_display_date(row[0]))
        attach_date_picker(date_entry)

        ctk.CTkLabel(dialog, text="Amount (NGN)").pack(anchor="w", padx=20)
        amount_entry = FormattedNumberEntry(dialog)
        amount_entry.pack(fill="x", padx=20, pady=(3, 10))
        amount_entry.insert(0, str(float(row[2] or 0)))

        ctk.CTkLabel(dialog, text="Reference").pack(anchor="w", padx=20)
        reference_entry = ctk.CTkEntry(dialog)
        reference_entry.pack(fill="x", padx=20, pady=(3, 14))
        reference_entry.insert(0, row[4])

        def save_changes():
            try:
                transaction_date = parse_flexible_date(
                    date_entry.get()
                ).isoformat()
                amount = float(amount_entry.get().replace(",", "").strip())
                update_account_transaction(
                    transaction_id, transaction_date, amount,
                    reference_entry.get(), DATABASE,
                )
                dialog.destroy()
                self.refresh()
                messagebox.showinfo(
                    "Updated", "The account transaction was updated.", parent=self,
                )
            except (ValueError, sqlite3.Error) as error:
                messagebox.showerror("Transaction Error", str(error), parent=dialog)

        actions = ctk.CTkFrame(dialog, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 16))
        Theme.primary_button(
            actions, "Update Transaction", save_changes, width=180,
        ).pack(side="left", padx=(0, 8))
        Theme.secondary_button(
            actions, "Cancel", dialog.destroy, width=100,
        ).pack(side="left")

    def delete_selected_transaction(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning(
                "Select transaction", "Select an account transaction to delete.",
                parent=self,
            )
            return
        transaction_id = int(selected[0])
        if not messagebox.askyesno(
            "Delete Transaction",
            "Delete the selected posted transaction? This may change account balances and reconciliation results.",
            parent=self,
        ):
            return
        try:
            delete_account_transaction(transaction_id, DATABASE)
            self.refresh_product_receipts()
            self.refresh()
            messagebox.showinfo(
                "Deleted", "The account transaction was deleted.", parent=self,
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Transaction Error", str(error), parent=self)

    def open_account_manager(self):
        AccountManagerWindow(self.winfo_toplevel(), self.refresh)

    def open_supplier_manager(self):
        SupplierManagerWindow(self.winfo_toplevel(), self.refresh_product_receipts)

    def open_daily_reconciliation(self):
        DailyReconciliationWindow(self.winfo_toplevel())

    def open_price_management(self):
        PriceManagementWindow(self.winfo_toplevel())
