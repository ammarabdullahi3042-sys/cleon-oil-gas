import math
import sqlite3
from datetime import date, datetime
from tkinter import messagebox, simpledialog

import customtkinter as ctk

from fifo_inventory import (
    ensure_fifo_schema,
    product_for_pump,
    rebuild_fifo_product,
)
from session_history_window import SessionHistoryWindow
from price_management import current_price
from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from fifo_inventory import latest_product_for_session
from app_settings import verify_access
from pump_runs import (
    ensure_pump_run_schema, run_choices, opening_meter_for_run,
    record_run_session,
)
from number_entry import FormattedNumberEntry


from app_settings import get_active_database

DATABASE = get_active_database()


class SessionWindow(ctk.CTkFrame):

    def __init__(self, master=None):
        super().__init__(master, fg_color="transparent")

        self.session_id = None
        self.session_run_id = None
        self.auto_price = None
        self.run_options = {}

        self.build_ui()
        self.load_pumps()
        self.load_attendants()

    def build_ui(self):
        action_bar = ctk.CTkFrame(self, fg_color=Theme.SURFACE)
        action_bar.pack(side="top", fill="x", padx=6, pady=(4, 6))
        self.save_button = Theme.primary_button(
            action_bar, "SAVE SESSION", self.save_session,
            width=125, height=36
        )
        self.save_button.pack(side="left", padx=4, pady=4)
        Theme.secondary_button(
            action_bar, "Update Session", self.update_session,
            width=135, height=36
        ).pack(side="left", padx=4)
        Theme.danger_button(
            action_bar, "Delete Session", self.delete_session,
            width=115, height=36
        ).pack(side="left", padx=4)
        Theme.secondary_button(
            action_bar, "Clear Session", self.clear_form,
            width=115, height=36
        ).pack(side="left", padx=4)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        form_panel = ctk.CTkScrollableFrame(
            content, width=390, fg_color="transparent"
        )
        form_panel.pack(side="left", fill="y", padx=(0, 8))
        history_panel = ctk.CTkFrame(content, fg_color="transparent")
        history_panel.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            form_panel,
            text="Pump Session Entry",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=(6, 10))

        self.pump_menu = ctk.CTkOptionMenu(
            form_panel,
            values=["Loading pumps..."],
            command=self.on_pump_selected
        )
        self.pump_menu.pack(padx=8, pady=4, fill="x")

        self.run_menu = ctk.CTkOptionMenu(
            form_panel, values=["No Open Product Runs"],
            command=self.on_run_selected
        )
        self.run_menu.pack(padx=8, pady=4, fill="x")

        self.attendant_menu = ctk.CTkOptionMenu(
            form_panel,
            values=["Loading attendants..."]
        )
        self.attendant_menu.pack(padx=8, pady=4, fill="x")

        self.opening_meter = FormattedNumberEntry(
            form_panel, placeholder_text="Opening meter (carried forward automatically)"
        )
        self.opening_meter.pack(padx=8, pady=4, fill="x")
        self.opening_meter.configure(state="disabled")

        self.closing_meter = FormattedNumberEntry(
            form_panel,
            placeholder_text="Closing Meter"
        )
        self.closing_meter.pack(padx=8, pady=4, fill="x")

        self.price_entry = FormattedNumberEntry(
            form_panel,
            placeholder_text="Automatic selling price (set in Accounts)",
            text_color=Theme.TEXT
        )
        self.price_entry.pack(padx=8, pady=4, fill="x")
        self.price_entry.configure(state="disabled")
        price_status_frame = ctk.CTkFrame(form_panel, fg_color="transparent")
        price_status_frame.pack(fill="x", padx=8, pady=(0, 4))
        self.price_status_label = ctk.CTkLabel(
            price_status_frame,
            text="Select a pump to load its product selling price.",
            font=Theme.SMALL_FONT,
            text_color=Theme.TEXT_LIGHT,
            anchor="w",
        )
        self.price_status_label.pack(side="left", fill="x", expand=True)
        Theme.secondary_button(
            price_status_frame, "Refresh Price", self.load_current_price,
            width=110, height=28
        ).pack(side="right", padx=(6, 0))

        self.cash_entry = FormattedNumberEntry(
            form_panel,
            placeholder_text="Cash Collected (₦)"
        )
        self.cash_entry.pack(padx=8, pady=4, fill="x")

        self.pos_entry = FormattedNumberEntry(
            form_panel,
            placeholder_text="POS Amount (₦)"
        )
        self.pos_entry.pack(padx=8, pady=4, fill="x")

        self.expense_entry = FormattedNumberEntry(
            form_panel,
            placeholder_text="Session Expenses (₦)"
        )
        self.expense_entry.pack(padx=8, pady=4, fill="x")

        self.rtt_entry = FormattedNumberEntry(
            form_panel,
            placeholder_text="RTT Returned to Tank (Litres)"
        )
        self.rtt_entry.pack(padx=8, pady=4, fill="x")

        self.date_entry = ctk.CTkEntry(
            form_panel,
            placeholder_text="Session Date (DD-MM-YY)"
        )
        self.date_entry.pack(padx=8, pady=4, fill="x")
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.date_entry)
        self.date_entry.bind("<FocusOut>", self.on_date_changed)
        self.date_entry.bind("<Return>", self.on_date_changed)

        self.result_label = ctk.CTkLabel(
            form_panel,
            text="Litres Sold: 0.00"
        )
        self.result_label.pack(pady=2)

        self.sales_label = ctk.CTkLabel(
            form_panel,
            text="Sales (price × litres sold): ₦0.00",
            wraplength=360
        )
        self.sales_label.pack(pady=2)

        self.net_sales_label = ctk.CTkLabel(
            form_panel,
            text="Net Sales Amount (net litres × price − session expense): ₦0.00",
            wraplength=360
        )
        self.net_sales_label.pack(pady=2)

        self.short_label = ctk.CTkLabel(
            form_panel,
            text="Cash Short / Over: ₦0.00",
            font=Theme.BODY_BOLD_FONT,
            text_color=Theme.TEXT,
            wraplength=360,
        )
        self.short_label.pack(pady=2)

        self.profit_label = ctk.CTkLabel(
            form_panel,
            text="Fuel cost / gross profit: calculated when saved",
            wraplength=360
        )
        self.profit_label.pack(pady=2)
        for entry in (
            self.opening_meter, self.closing_meter, self.cash_entry,
            self.pos_entry, self.expense_entry, self.rtt_entry,
        ):
            entry.bind("<KeyRelease>", self.update_sales_preview, add="+")
        self.history_view = SessionHistoryWindow(
            history_panel, session_window=self
        )
        self.history_view.pack(fill="both", expand=True)

    def load_pumps(self, preserve_selection=False):
        previous_selection = self.pump_menu.get() if preserve_selection else None
        try:
            with sqlite3.connect(DATABASE) as conn:
                rows = conn.execute("""
                    SELECT pump_number
                    FROM pumps
                    ORDER BY pump_number
                """).fetchall()

            values = [str(row[0]) for row in rows] or ["No Pumps"]
            selected = (previous_selection if previous_selection in values
                        else values[0])
            self.pump_menu.configure(values=values)
            self.pump_menu.set(selected)
            self.load_product_runs()
            # Avoid resetting a user's in-progress session when the cached page
            # is reopened and its existing pump is still available.
            if selected != previous_selection and selected != "No Pumps":
                self.load_product_runs()
                self.load_previous_closing()
                self.load_current_price()

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load pumps:\n{error}",
                parent=self
            )

    def load_attendants(self, preserve_selection=False):
        previous_selection = self.attendant_menu.get() if preserve_selection else None
        try:
            with sqlite3.connect(DATABASE) as conn:
                rows = conn.execute("""
                    SELECT name
                    FROM attendants
                    ORDER BY name
                """).fetchall()

            values = [str(row[0]) for row in rows] or ["No Attendants"]
            selected = (previous_selection if previous_selection in values
                        else values[0])
            self.attendant_menu.configure(values=values)
            self.attendant_menu.set(selected)

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load attendants:\n{error}",
                parent=self
            )

    def refresh_page(self):
        """Refresh lists when the dashboard raises this cached page again."""
        self.load_pumps(preserve_selection=True)
        self.load_attendants(preserve_selection=True)
        self.load_current_price()

    def on_pump_selected(self, selected_pump):
        if selected_pump != "No Pumps":
            self.load_product_runs()
            self.load_previous_closing()
            self.load_current_price()

    def load_product_runs(self):
        pump_number = self.pump_menu.get()
        self.run_options.clear()
        if not pump_number or pump_number == "No Pumps":
            labels = ["No Open Product Runs"]
        else:
            try:
                with sqlite3.connect(DATABASE, timeout=10) as conn:
                    ensure_pump_run_schema(conn)
                    pump = conn.execute(
                        "SELECT id FROM pumps WHERE pump_number=?",
                        (pump_number,)
                    ).fetchone()
                    if not pump:
                        labels = ["No Open Product Runs"]
                    else:
                        self.run_options = run_choices(conn, pump[0])
                        labels = list(self.run_options) or ["No Open Product Runs"]
            except sqlite3.Error as error:
                messagebox.showerror(
                    "Product Run Error", str(error), parent=self
                )
                labels = ["No Open Product Runs"]
        current = self.run_menu.get()
        self.run_menu.configure(values=labels)
        selected = current if current in labels else labels[0]
        self.run_menu.set(selected)
        if selected in self.run_options:
            self.load_run_opening()

    def on_run_selected(self, _selected=None):
        self.load_run_opening()

    def selected_run_id(self):
        return self.run_options.get(self.run_menu.get())

    def load_run_opening(self):
        run_id = (self.session_run_id if self.session_id is not None
                  else self.selected_run_id())
        if run_id is None:
            self._set_opening_meter("")
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                pump = conn.execute(
                    "SELECT id FROM pumps WHERE pump_number=?",
                    (self.pump_menu.get(),)
                ).fetchone()
                reading = opening_meter_for_run(
                    conn, pump[0], run_id, self.session_id
                ) if pump else None
            self._set_opening_meter(
                "" if reading is None else f"{reading:.2f}",
                editable=self.session_id is not None
            )
        except sqlite3.Error as error:
            messagebox.showerror("Meter Reading Error", str(error), parent=self)

    def _set_opening_meter(self, value, editable=False):
        self.opening_meter.configure(state="normal")
        self.opening_meter.delete(0, "end")
        if value != "":
            self.opening_meter.insert(0, str(value))
        self.opening_meter.configure(state="normal" if editable else "disabled")
        self.update_sales_preview()

    def on_date_changed(self, event=None):
        self.load_previous_closing()
        self.load_current_price()

    def set_session_price(self, value):
        self.price_entry.configure(state="normal")
        self.price_entry.delete(0, "end")
        if value is not None:
            self.price_entry.insert(0, f"{float(value):.2f}")
            self.price_status_label.configure(
                text=f"Automatic selling price applied: NGN {float(value):,.2f} per litre.",
                text_color=Theme.SUCCESS
            )
        else:
            self.price_status_label.configure(
                text="No effective price found. Add this product's price in Accounts > Selling Prices.",
                text_color=Theme.WARNING
            )
        self.price_entry.configure(state="disabled")
        self.update_sales_preview()

    def load_current_price(self):
        """Fill the locked session price using product and session date."""
        pump_number = self.pump_menu.get()
        if not pump_number or pump_number == "No Pumps":
            self.set_session_price(None)
            self.price_status_label.configure(
                text="Add and assign a pump to a fuel tank to load a selling price.",
                text_color=Theme.TEXT_LIGHT
            )
            return
        try:
            session_date = self.get_session_date()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                pump = conn.execute(
                    "SELECT id FROM pumps WHERE pump_number=?", (pump_number,)
                ).fetchone()
                product = product_for_pump(conn.cursor(), pump[0]) if pump else None
            price = current_price(product, session_date, DATABASE)
            self.set_session_price(price)
            if price is None and product:
                with sqlite3.connect(DATABASE, timeout=10) as conn:
                    upcoming = conn.execute("""
                        SELECT MIN(date(effective_date))
                        FROM product_prices
                        WHERE UPPER(TRIM(product))=UPPER(TRIM(?))
                          AND date(effective_date)>date(?)
                    """, (product, session_date)).fetchone()[0]
                if upcoming:
                    self.price_status_label.configure(
                        text=(f"{product} has a saved price, but its effective "
                              f"date is {upcoming}, after this session date "
                              f"({session_date})."),
                        text_color=Theme.WARNING
                    )
                else:
                    self.price_status_label.configure(
                        text=(f"No selling price for {product} is effective on "
                              f"{session_date}. Check Accounts > Selling Prices."),
                        text_color=Theme.WARNING
                    )
        except ValueError as error:
            self.set_session_price(None)
            self.price_status_label.configure(
                text=str(error), text_color=Theme.WARNING
            )
        except sqlite3.Error as error:
            self.set_session_price(None)
            self.price_status_label.configure(
                text="Could not load selling price; see the database error.",
                text_color=Theme.WARNING
            )
            messagebox.showerror(
                "Selling Price", f"Could not load the saved price:\n{error}",
                parent=self,
            )

    def load_previous_closing(self):
        """Carry forward only the selected pump/product run's previous meter."""
        self.load_run_opening()

    def get_session_date(self):
        try:
            return parse_flexible_date(self.date_entry.get()).isoformat()
        except ValueError:
            raise ValueError("Enter a valid date such as 30/09/2026 or 2026-09-30.")

    def get_form_data(self):
        session_date = self.get_session_date()
        pump_number = self.pump_menu.get()
        attendant_name = self.attendant_menu.get()

        if pump_number == "No Pumps":
            raise ValueError("Add a pump before recording a session.")
        if attendant_name == "No Attendants":
            raise ValueError("Add an attendant before recording a session.")
        run_id = self.selected_run_id()
        if run_id is None and not (
            self.session_id is not None and self.session_run_id is None
        ):
            raise ValueError(
                "Select an open product run linked to a stock receipt before recording sales."
            )

        try:
            opening = float(self.opening_meter.get())
            closing = float(self.closing_meter.get())
            price_text = self.price_entry.get().strip()
            if not price_text:
                raise ValueError("Set a selling price for this product and date in Accounts first.")
            price = float(price_text)
            cash = float(self.cash_entry.get() or 0)
            pos = float(self.pos_entry.get() or 0)
            expenses = float(self.expense_entry.get() or 0)
            rtt_litres = float(self.rtt_entry.get() or 0)
        except ValueError:
            raise ValueError("Enter valid numbers in the session fields.")

        values = (opening, closing, price, cash, pos, expenses, rtt_litres)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Session values must be finite numbers.")
        if min(values) < 0:
            raise ValueError("Session values cannot be negative.")
        if closing < opening:
            raise ValueError(
                "Closing meter cannot be less than opening meter."
            )

        gross_dispensed = closing - opening
        if rtt_litres > gross_dispensed:
            raise ValueError("RTT litres cannot exceed the pump meter movement.")
        litres = gross_dispensed - rtt_litres
        sale_amount = litres * price
        net_sales = sale_amount - expenses
        short_over = cash + pos - net_sales

        return {
            "date": session_date,
            "pump_number": pump_number,
            "attendant_name": attendant_name,
            "run_id": run_id,
            "opening": opening,
            "closing": closing,
            "litres": litres,
            "price": price,
            "sale_amount": sale_amount,
            "net_sales": net_sales,
            "cash": cash,
            "pos": pos,
            "expenses": expenses,
            "rtt_litres": rtt_litres,
            "short_over": short_over,
        }

    def get_ids_and_product(self, cursor, pump_number, attendant_name, run_id,
                            allow_closed=False):
        cursor.execute(
            "SELECT id FROM pumps WHERE pump_number=?",
            (pump_number,)
        )
        pump = cursor.fetchone()
        if not pump:
            raise ValueError("The selected pump could not be found.")

        pump_id = pump[0]
        product = product_for_pump(cursor, pump_id)
        if run_id is not None:
            run = cursor.execute("""
                SELECT product,tank_id,status FROM pump_product_runs
                WHERE id=? AND pump_id=?
            """, (run_id, pump_id)).fetchone()
            if not run or (run[2] != "OPEN" and not allow_closed):
                raise ValueError("The selected pump has no matching open product run.")
            if run[0].casefold() != product.casefold():
                raise ValueError(
                    "The selected stock run product does not match this pump's assigned tank."
                )

        cursor.execute(
            "SELECT id FROM attendants WHERE name=?",
            (attendant_name,)
        )
        attendant = cursor.fetchone()
        if not attendant:
            raise ValueError("The selected attendant could not be found.")

        return pump_id, attendant[0], product, run_id

    def calculate_sales(self):
        try:
            data = self.get_form_data()
            self._display_sales(data)
        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )

    def update_sales_preview(self, _event=None):
        try:
            self._display_sales(self.get_form_data())
        except ValueError:
            self.result_label.configure(text="Litres Sold: —")
            self.sales_label.configure(
                text="Sales (price × litres sold): —"
            )
            self.net_sales_label.configure(
                text="Net Sales Amount (net litres × price − session expense): —"
            )
            self.short_label.configure(text="Cash Short / Over: —")

    def _display_sales(self, data):
        self.result_label.configure(
            text=f"Litres Sold: {data['litres']:,.2f}"
        )
        self.sales_label.configure(
            text=f"Sales (price × litres sold): ₦{data['sale_amount']:,.2f}"
        )
        self.net_sales_label.configure(
            text=f"Net Sales Amount (net litres × price − session expense): "
                 f"₦{data['net_sales']:,.2f}"
        )
        self.short_label.configure(
            text=f"Cash Short / Over: ₦{data['short_over']:+,.2f}",
            text_color=(
                Theme.DANGER if data["short_over"] < 0 else
                Theme.SUCCESS if data["short_over"] > 0 else Theme.TEXT
            )
        )

    def save_session(self):
        if self.session_id is not None:
            messagebox.showwarning(
                "Session Loaded",
                "This session is loaded for editing. Use Update Session to save your changes.",
                parent=self
            )
            return
        try:
            data = self.get_form_data()
            self._display_sales(data)

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_fifo_schema(conn)
                cursor = conn.cursor()
                pump_id, attendant_id, product, run_id = self.get_ids_and_product(
                    cursor,
                    data["pump_number"],
                    data["attendant_name"],
                    data["run_id"],
                )

                cursor.execute("""
                    INSERT INTO pump_sessions (
                        pump_id, attendant_id, opening_meter, closing_meter,
                        litres_sold, price_per_litre, sale_amount,
                        cash_collected, pos_amount, expenses, rtt,
                        short_over, session_date, product,
                        cost_of_goods_sold, gross_profit,
                        average_cost_per_litre, rtt_litres, run_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                """, (
                    pump_id, attendant_id, data["opening"], data["closing"],
                    data["litres"], data["price"], data["sale_amount"],
                    data["cash"], data["pos"], data["expenses"], data["rtt_litres"],
                    data["short_over"], data["date"], product, data["rtt_litres"],
                    run_id
                ))

                session_id = cursor.lastrowid
                record_run_session(
                    cursor, pump_id, run_id, session_id,
                    data["opening"], data["closing"]
                )
                rebuild_fifo_product(cursor, product)

                cursor.execute("""
                    SELECT cost_of_goods_sold, gross_profit
                    FROM pump_sessions
                    WHERE id=?
                """, (session_id,))
                cogs, gross_profit = cursor.fetchone()

            self.profit_label.configure(
                text=(
                    f"Fuel Cost: ₦{cogs:,.2f}  |  "
                    f"Gross Profit: ₦{gross_profit:,.2f}"
                )
            )
            messagebox.showinfo(
                "Saved",
                f"Session saved.\n"
                f"Fuel cost: ₦{cogs:,.2f}\n"
                f"Gross profit: ₦{gross_profit:,.2f}",
                parent=self
            )
            self.refresh_history()
            self.clear_form()

        except ValueError as error:
            messagebox.showerror(
                "Check Entry / Stock",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not save session:\n{error}",
                parent=self
            )

    def update_session(self):
        if self.session_id is None:
            messagebox.showwarning(
                "Select Session",
                "Load a session from history before updating.",
                parent=self
            )
            return

        password = simpledialog.askstring(
            "Accounts Authorization",
            "Enter the Accounts access password to update this pump session:",
            parent=self, show="*"
        )
        if password is None:
            return
        try:
            if not verify_access("accounts", password, DATABASE):
                messagebox.showerror(
                    "Access Denied", "The Accounts password is incorrect.",
                    parent=self
                )
                return
        except sqlite3.Error as error:
            messagebox.showerror(
                "Authorization Error", str(error), parent=self
            )
            return

        try:
            data = self.get_form_data()
            self._display_sales(data)
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_fifo_schema(conn)
                cursor = conn.cursor()

                old_product = latest_product_for_session(
                    cursor, self.session_id
                )
                if old_product is None:
                    raise ValueError("The selected session was not found.")

                pump_id, attendant_id, new_product, run_id = self.get_ids_and_product(
                    cursor,
                    data["pump_number"],
                    data["attendant_name"],
                    data["run_id"],
                    allow_closed=True,
                )
                current_run = cursor.execute(
                    "SELECT run_id FROM pump_sessions WHERE id=?",
                    (self.session_id,)
                ).fetchone()
                if not current_run:
                    raise ValueError("The selected session was not found.")
                old_readings = cursor.execute("""
                    SELECT opening_meter,closing_meter FROM pump_sessions
                    WHERE id=?
                """, (self.session_id,)).fetchone()
                correction_reason = ""
                if (
                    abs(float(old_readings[0]) - data["opening"]) > 0.005
                    or abs(float(old_readings[1]) - data["closing"]) > 0.005
                ):
                    correction_reason = simpledialog.askstring(
                        "Meter Correction Audit",
                        "Explain why the saved pump meter readings are being corrected:",
                        parent=self
                    )
                    if correction_reason is None:
                        return
                    if not correction_reason.strip():
                        raise ValueError(
                            "Enter a reason for changing saved meter readings."
                        )
                if current_run[0] != run_id:
                    raise ValueError(
                        "A saved session cannot be moved to a different stock run."
                    )
                allocated = cursor.execute("""
                    SELECT 1 FROM attendant_short_allocations
                    WHERE session_id=? LIMIT 1
                """, (self.session_id,)).fetchone()
                if allocated:
                    raise ValueError(
                        "This session has an audited short reconciliation and cannot be edited."
                    )

                cursor.execute("""
                    UPDATE pump_sessions
                    SET pump_id=?, attendant_id=?, opening_meter=?,
                        closing_meter=?, litres_sold=?, price_per_litre=?,
                        sale_amount=?, cash_collected=?, pos_amount=?,
                        expenses=?, rtt=?, short_over=?, session_date=?,
                        product=?, rtt_litres=?
                    WHERE id=?
                """, (
                    pump_id, attendant_id, data["opening"], data["closing"],
                    data["litres"], data["price"], data["sale_amount"],
                    data["cash"], data["pos"], data["expenses"], data["rtt_litres"],
                    data["short_over"], data["date"], new_product,
                    data["rtt_litres"],
                    self.session_id
                ))
                if cursor.rowcount != 1:
                    raise ValueError("The selected history session was not found; no new session was created.")
                if correction_reason:
                    cursor.execute("""
                        INSERT INTO pump_session_audit(
                            session_id,changed_by,reason,old_opening_meter,
                            new_opening_meter,old_closing_meter,new_closing_meter
                        ) VALUES (?,?,?,?,?,?,?)
                    """, (
                        self.session_id,
                        getattr(self.winfo_toplevel(), "login_username", ""),
                        correction_reason.strip(), old_readings[0], data["opening"],
                        old_readings[1], data["closing"]
                    ))
                if run_id is not None:
                    record_run_session(
                        cursor, pump_id, run_id, self.session_id,
                        data["opening"], data["closing"], allow_closed=True,
                        allow_opening_correction=True
                    )
                cursor.execute("""
                    UPDATE pump_product_runs SET
                        opening_meter=(SELECT opening_meter FROM pump_sessions
                                       WHERE run_id=? ORDER BY date(session_date),id LIMIT 1),
                        closing_meter=(SELECT closing_meter FROM pump_sessions
                                       WHERE run_id=? ORDER BY date(session_date) DESC,id DESC LIMIT 1)
                    WHERE id=?
                """, (run_id, run_id, run_id))

                for product in {old_product, new_product}:
                    rebuild_fifo_product(cursor, product)

                cursor.execute("""
                    SELECT cost_of_goods_sold, gross_profit
                    FROM pump_sessions
                    WHERE id=?
                """, (self.session_id,))
                cogs, gross_profit = cursor.fetchone()

            self.profit_label.configure(
                text=(
                    f"Fuel Cost: ₦{cogs:,.2f}  |  "
                    f"Gross Profit: ₦{gross_profit:,.2f}"
                )
            )
            messagebox.showinfo(
                "Updated",
                "Session updated and product costs recalculated.",
                parent=self
            )
            self.refresh_history()

        except ValueError as error:
            messagebox.showerror(
                "Check Entry / Stock",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not update session:\n{error}",
                parent=self
            )

    def delete_session(self):
        if self.session_id is None:
            messagebox.showwarning(
                "Select Session",
                "Load a session from history before deleting.",
                parent=self
            )
            return

        if not messagebox.askyesno(
            "Delete Session",
            "Delete the selected session and recalculate product costs?",
            parent=self
        ):
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_fifo_schema(conn)
                cursor = conn.cursor()
                product = latest_product_for_session(cursor, self.session_id)
                if product is None:
                    raise ValueError("The selected session was not found.")
                run_id = cursor.execute(
                    "SELECT run_id FROM pump_sessions WHERE id=?",
                    (self.session_id,)
                ).fetchone()[0]
                if run_id is not None:
                    run_status = cursor.execute(
                        "SELECT status FROM pump_product_runs WHERE id=?",
                        (run_id,)
                    ).fetchone()
                    if run_status and run_status[0] == "CLOSED":
                        raise ValueError(
                            "Sessions in a finished product run are retained for audit."
                        )
                    later = cursor.execute("""
                        SELECT 1 FROM pump_sessions current
                        JOIN pump_sessions later ON later.run_id=current.run_id
                        WHERE current.id=? AND
                          (date(later.session_date)>date(current.session_date) OR
                           (date(later.session_date)=date(current.session_date)
                            AND later.id>current.id))
                        LIMIT 1
                    """, (self.session_id,)).fetchone()
                    if later:
                        raise ValueError(
                            "Delete the latest session in a product run first so "
                            "meter continuity remains auditable."
                        )

                cursor.execute(
                    "SELECT 1 FROM attendant_short_allocations WHERE session_id=? LIMIT 1",
                    (self.session_id,)
                )
                if cursor.fetchone():
                    raise ValueError(
                        "This session has an audited short reconciliation and cannot be deleted."
                    )
                cursor.execute(
                    "DELETE FROM fifo_session_allocations WHERE session_id=?",
                    (self.session_id,)
                )
                cursor.execute(
                    "DELETE FROM pump_sessions WHERE id=?",
                    (self.session_id,)
                )
                if run_id is not None:
                    cursor.execute("""
                        UPDATE pump_product_runs SET
                            opening_meter=(SELECT opening_meter FROM pump_sessions
                                WHERE run_id=? ORDER BY date(session_date),id LIMIT 1),
                            closing_meter=(SELECT closing_meter FROM pump_sessions
                                WHERE run_id=? ORDER BY date(session_date) DESC,id DESC LIMIT 1)
                        WHERE id=?
                    """, (run_id, run_id, run_id))
                rebuild_fifo_product(cursor, product)

            messagebox.showinfo(
                "Deleted",
                "Session deleted and product costs recalculated.",
                parent=self
            )
            self.refresh_history()
            self.clear_form()

        except ValueError as error:
            messagebox.showerror(
                "Session Error",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not delete session:\n{error}",
                parent=self
            )

    def clear_form(self):
        self.session_id = None
        self.session_run_id = None
        self.save_button.configure(text="SAVE SESSION")

        for entry in (
            self.closing_meter,
            self.cash_entry,
            self.pos_entry,
            self.expense_entry,
            self.rtt_entry,
        ):
            entry.delete(0, "end")

        self._set_opening_meter("")

        self.set_session_price(None)

        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))

        self.result_label.configure(text="Litres Sold: 0.00")
        self.sales_label.configure(
            text="Sales (price × litres sold): ₦0.00"
        )
        self.net_sales_label.configure(
            text="Net Sales Amount (net litres × price − session expense): ₦0.00"
        )
        self.short_label.configure(text="Cash Short / Over: ₦0.00")
        self.profit_label.configure(
            text="Fuel cost / gross profit: calculated when saved"
        )

        pump_values = self.pump_menu.cget("values")
        if pump_values:
            self.pump_menu.set(pump_values[0])
            self.load_product_runs()
            self.load_previous_closing()
            self.load_current_price()

        attendant_values = self.attendant_menu.cget("values")
        if attendant_values:
            self.attendant_menu.set(attendant_values[0])

    def refresh_history(self):
        if hasattr(self, "history_view"):
            self.history_view.load_sessions()

    def load_session_record(self, session_id):
        """Load a saved session into this page from session history."""
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT ps.opening_meter, ps.closing_meter,
                           ps.price_per_litre, ps.cash_collected,
                           ps.pos_amount, ps.expenses,
                           COALESCE(ps.rtt_litres,0), ps.session_date,
                           p.pump_number, a.name, ps.run_id
                    FROM pump_sessions ps
                    LEFT JOIN pumps p ON p.id=ps.pump_id
                    LEFT JOIN attendants a ON a.id=ps.attendant_id
                    WHERE ps.id=?
                """, (session_id,)).fetchone()
            if not row:
                raise ValueError("That session record could not be found.")
            self.clear_form()
            self.session_id = int(session_id)
            self.session_run_id = row[10]
            fields = (self.closing_meter, self.cash_entry, self.pos_entry,
                      self.expense_entry, self.rtt_entry)
            for entry, value in zip(fields, (row[1], *row[3:7])):
                entry.insert(0, str(value or 0))
            self.set_session_price(row[2])
            self.date_entry.delete(0, "end")
            self.date_entry.insert(
                0, format_display_date(str(row[7] or date.today().isoformat())[:10])
            )
            if row[8] and row[8] in self.pump_menu.cget("values"):
                self.pump_menu.set(row[8])
            self.load_product_runs()
            for label, run_id in self.run_options.items():
                if run_id == row[10]:
                    self.run_menu.set(label)
                    break
            self._set_opening_meter(str(row[0] or 0), editable=True)
            if row[9] and row[9] in self.attendant_menu.cget("values"):
                self.attendant_menu.set(row[9])
            self.calculate_sales()
        except (sqlite3.Error, ValueError) as error:
            messagebox.showerror("Load Session", str(error), parent=self)
