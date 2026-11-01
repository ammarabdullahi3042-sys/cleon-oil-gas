import sqlite3
import math
from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from fifo_inventory import ensure_fifo_schema, rebuild_fifo_product
from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from pump_runs import link_receipt_to_product_runs
from pump_runs import ensure_pump_run_schema, opening_meter_for_new_run
from short_reconciliation import (
    ensure_reconciliation_schema, receipt_short_amounts,
    reconcile_receipt_short, update_receipt_effective_cost,
)
from number_entry import FormattedNumberEntry
from suggestion_entry import SuggestionEntry
from supplier_records import (
    ensure_supplier_schema, get_or_create_supplier_id, supplier_names,
)


from app_settings import get_active_database

DATABASE = get_active_database()


class FuelReceiptWindow(ctk.CTkFrame):

    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)

        self.tank_options = {}
        self.selected_receipt_id = None
        self.editing_receipt_id = None
        self.pump_meter_entries = {}
        self.supplier_options = []
        self.driver_options = []
        self.driver_phones = {}
        self.last_suggested_driver_phone = ""
        self.vehicle_options = []

        self.prepare_database()
        self.load_suggestions()
        self.build_ui()
        self.load_tanks()
        self.load_receipts()

    def prepare_database(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_fifo_schema(conn)
                ensure_supplier_schema(conn)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not prepare receipt/FIFO tables:\n{error}",
                parent=self
            )

    def build_ui(self):
        ctk.CTkLabel(
            self,
            text="Fuel Receipt Entry",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=(12, 5))

        ctk.CTkLabel(
            self,
            text="Enter invoice quantity and physically measured quantity separately.",
            font=("Segoe UI", 12)
        ).pack(pady=(0, 8))

        form = ctk.CTkFrame(self)
        form.pack(fill="x", padx=14, pady=6)
        form.grid_columnconfigure(0, weight=1)
        form.grid_columnconfigure(1, weight=1)

        self.tank_menu = ctk.CTkOptionMenu(
            form,
            values=["Loading tanks..."],
            command=self.on_tank_selected
        )
        self.tank_menu.grid(
            row=1, column=0, columnspan=2,
            padx=8, pady=7, sticky="ew"
        )

        ctk.CTkLabel(form, text="Receipt Type").grid(
            row=0, column=0, padx=8, pady=(8, 0), sticky="w"
        )
        self.receipt_type_menu = ctk.CTkOptionMenu(
            form,
            values=["Delivery", "Opening Balance"]
        )
        self.receipt_type_menu.grid(
            row=0, column=1, padx=8, pady=7, sticky="ew"
        )

        self.supplier_entry = self.make_suggestion_entry(
            form, "Supplier Name", 2, 0, lambda: self.supplier_options
        )
        self.supplier_entry.bind(
            "<FocusIn>", self.refresh_supplier_suggestions, add="+"
        )
        self.invoice_entry = self.make_entry(
            form, "Invoice Number", 2, 1
        )
        self.delivery_entry = self.make_entry(
            form, "Delivery Note Number", 3, 0
        )
        self.date_entry = self.make_entry(
            form, "Receipt Date (DD-MM-YY)", 3, 1
        )
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.date_entry)

        self.invoice_quantity_entry = self.make_entry(
            form, "Invoice / Expected Quantity (L)", 4, 0, numeric=True
        )
        self.actual_quantity_entry = self.make_entry(
            form, "Actual Quantity Received (L)", 4, 1, numeric=True
        )
        self.cost_entry = self.make_entry(
            form, "Cost Price per Litre (NGN)", 5, 0, numeric=True
        )
        self.vehicle_entry = self.make_suggestion_entry(
            form, "Delivery Vehicle Number", 5, 1,
            lambda: self.vehicle_options,
        )
        self.driver_entry = self.make_suggestion_entry(
            form, "Driver Name", 6, 0, lambda: self.driver_options,
            command=self.on_driver_selected,
        )
        self.driver_phone_entry = self.make_entry(
            form, "Driver Phone Number", 6, 1
        )
        Theme.secondary_button(
            form, "Truck History", self.search_truck_history, width=130
        ).grid(row=7, column=1, padx=8, pady=(0, 5), sticky="e")
        self.pump_meter_frame = ctk.CTkFrame(form, fg_color="transparent")
        self.pump_meter_frame.grid(
            row=8, column=0, columnspan=2, padx=8, pady=5, sticky="ew"
        )
        self.pump_meter_heading = ctk.CTkLabel(
            self.pump_meter_frame,
            text=("Opening meter by connected pump. Same-product deliveries "
                  "already in an open run keep the original opening."),
            wraplength=680, justify="left"
        )
        self.pump_meter_heading.pack(anchor="w", pady=(0, 4))

        ctk.CTkButton(
            form,
            text="Calculate Short / Over and Cost",
            command=self.calculate_receipt
        ).grid(
            row=9, column=0, columnspan=2,
            padx=8, pady=8
        )

        self.result_label = ctk.CTkLabel(
            form,
            text=(
                "Short/Over: 0.00 L  |  Variance Value: ₦0.00  |  "
                "Receipt Cost: ₦0.00"
            ),
            font=("Segoe UI", 13, "bold")
        )
        self.result_label.grid(
            row=10, column=0, columnspan=2,
            padx=8, pady=(2, 8)
        )

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(pady=8)
        self.save_receipt_button = ctk.CTkButton(
            actions, text="Save Fuel Receipt",
            command=self.save_receipt
        )
        self.save_receipt_button.pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Edit Selected Receipt",
            command=self.edit_selected_receipt
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Reconcile Selected Shortage",
            command=self.reconcile_selected_receipt
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Supplier / Driver Shortage Ledger",
            command=self.open_shortage_ledger
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            actions, text="Receipt Reconciliation History",
            command=self.open_receipt_history
        ).pack(side="left", padx=4)

        ctk.CTkLabel(
            self,
            text="Recent Fuel Receipts",
            font=("Segoe UI", 16, "bold")
        ).pack(pady=(8, 3))

        table_frame = ctk.CTkFrame(self)
        table_frame.pack(fill="both", expand=True, padx=14, pady=(4, 12))

        columns = (
            "Date", "Tank", "Product", "Invoice L", "Actual L",
            "Short/Over", "Unit Cost", "Total Cost", "Remaining",
            "Vehicle", "Driver", "Phone", "Adjusted Product Cost"
        )
        self.tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=9
        )

        headings = {
            "Date": "Date",
            "Tank": "Tank No.",
            "Product": "Product",
            "Invoice L": "Invoice L",
            "Actual L": "Actual L",
            "Short/Over": "Short/Over L",
            "Unit Cost": "Cost/L",
            "Total Cost": "Receipt Cost",
            "Remaining": "Stock Balance L",
            "Vehicle": "Vehicle",
            "Driver": "Driver",
            "Phone": "Driver Phone",
            "Adjusted Product Cost": "Adjusted Product Cost"
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=165 if column == "Adjusted Product Cost" else 110,
                anchor="center",
            )

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.tree.yview
        )
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.select_receipt)

    def make_entry(self, parent, placeholder, row, column, numeric=False):
        entry_type = FormattedNumberEntry if numeric else ctk.CTkEntry
        entry = entry_type(parent, placeholder_text=placeholder)
        entry.grid(
            row=row,
            column=column,
            padx=8,
            pady=6,
            sticky="ew"
        )
        return entry

    def make_suggestion_entry(
        self, parent, placeholder, row, column, values, command=None
    ):
        values_provider = values if callable(values) else lambda: values
        entry = SuggestionEntry(
            parent, values_provider=values_provider, command=command,
            placeholder_text=placeholder,
        )
        entry.grid(row=row, column=column, padx=8, pady=6, sticky="ew")
        return entry

    def load_suggestions(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_supplier_schema(conn)
                self.supplier_options = supplier_names(conn)
                receipts = conn.execute("""
                    SELECT COALESCE(supplier_name,''),COALESCE(driver_name,''),
                           COALESCE(driver_phone,''),COALESCE(vehicle_number,'')
                    FROM fuel_receipts
                    ORDER BY date(receipt_date) DESC,id DESC
                """).fetchall()
            self.driver_options = []
            self.driver_phones = {}
            self.vehicle_options = []
            for supplier, driver, phone, vehicle in receipts:
                if supplier and supplier.casefold() not in {
                    value.casefold() for value in self.supplier_options
                }:
                    self.supplier_options.append(supplier)
                if driver and driver.casefold() not in {
                    value.casefold() for value in self.driver_options
                }:
                    self.driver_options.append(driver)
                    self.driver_phones[driver.casefold()] = phone
                if vehicle and vehicle.casefold() not in {
                    value.casefold() for value in self.vehicle_options
                }:
                    self.vehicle_options.append(vehicle)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Fuel Receipt Suggestions",
                f"Could not load supplier, driver, and truck history:\n{error}",
                parent=self,
            )

    def on_driver_selected(self, driver_name):
        phone = self.driver_phones.get(driver_name.casefold(), "")
        current_phone = self.driver_phone_entry.get().strip()
        if phone and (
            not current_phone
            or current_phone == self.last_suggested_driver_phone
        ):
            self.driver_phone_entry.delete(0, "end")
            self.driver_phone_entry.insert(0, phone)
            self.last_suggested_driver_phone = phone

    def refresh_supplier_suggestions(self, _event=None):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                self.supplier_options = [
                    row[0] for row in conn.execute("""
                        SELECT name FROM suppliers
                        ORDER BY name COLLATE NOCASE
                    """)
                ]
        except sqlite3.Error as error:
            messagebox.showerror(
                "Supplier Suggestions",
                f"Could not refresh supplier names:\n{error}",
                parent=self,
            )

    def search_truck_history(self):
        vehicle = self.vehicle_entry.get().strip()
        if not vehicle:
            messagebox.showwarning(
                "Truck History", "Enter or select a truck number first.",
                parent=self,
            )
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_supplier_schema(conn)
                rows = conn.execute("""
                    SELECT receipt_date,invoice_number,COALESCE(product,''),
                           COALESCE(supplier_name,''),COALESCE(driver_name,''),
                           COALESCE(driver_phone,''),COALESCE(invoice_quantity,0),
                           COALESCE(quantity_received,0)
                    FROM fuel_receipts
                    WHERE UPPER(TRIM(vehicle_number))=UPPER(TRIM(?))
                    ORDER BY date(receipt_date) DESC,id DESC
                """, (vehicle,)).fetchall()
        except sqlite3.Error as error:
            messagebox.showerror("Truck History", str(error), parent=self)
            return

        if not rows:
            messagebox.showinfo(
                "Truck History",
                f"No previous fuel deliveries found for truck {vehicle}.",
                parent=self,
            )
            return

        window = ctk.CTkToplevel(self)
        window.title(f"Truck History — {vehicle}")
        window.geometry("1050x420")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window, text=f"Previous deliveries by {vehicle}",
            font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT,
        ).pack(anchor="w", padx=16, pady=(14, 6))
        columns = (
            "Date", "Invoice", "Product", "Supplier", "Driver",
            "Driver Phone", "Invoice L", "Actual L",
        )
        tree = ttk.Treeview(window, columns=columns, show="headings")
        for column, width in zip(
            columns, (105, 125, 85, 170, 150, 120, 105, 105)
        ):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(window, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(0, 12), pady=8)
        for row in rows:
            tree.insert("", "end", values=(
                format_display_date(row[0]), row[1] or "", row[2], row[3],
                row[4], row[5], f"{float(row[6] or 0):,.2f}",
                f"{float(row[7] or 0):,.2f}",
            ))

    def load_tanks(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, tank_number, name, product, capacity,
                           current_stock
                    FROM tanks
                    ORDER BY id
                """)
                rows = cursor.fetchall()

            self.tank_options.clear()
            choices = []
            for tank_id, number, name, product, capacity, stock in rows:
                number = number or f"Record {tank_id}"
                label = f"{number} | {product} | {name}"
                self.tank_options[label] = {
                    "id": tank_id,
                    "product": product,
                    "capacity": float(capacity),
                    "stock": float(stock or 0)
                }
                choices.append(label)

            if not choices:
                choices = ["No Tanks"]

            self.tank_menu.configure(values=choices)
            self.tank_menu.set(choices[0])
            self.load_pump_meter_inputs()

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load tanks:\n{error}",
                parent=self
            )

    def get_form_data(self):
        selected = self.tank_options.get(self.tank_menu.get())
        if selected is None:
            raise ValueError("Create a tank before entering a receipt.")

        supplier = self.supplier_entry.get().strip()
        invoice_number = self.invoice_entry.get().strip()
        delivery_note = self.delivery_entry.get().strip()
        vehicle_number = self.vehicle_entry.get().strip()
        driver_name = self.driver_entry.get().strip()
        driver_phone = self.driver_phone_entry.get().strip()

        receipt_type = self.receipt_type_menu.get()
        if receipt_type == "Opening Balance":
            supplier = supplier or "Opening Stock"
            invoice_number = invoice_number or "OPENING"
            vehicle_number = vehicle_number or "N/A"
            driver_name = driver_name or "N/A"
            driver_phone = driver_phone or "N/A"
        else:
            if not supplier:
                raise ValueError("Enter the supplier name.")
            if not invoice_number:
                raise ValueError("Enter the invoice number.")
            if not vehicle_number:
                raise ValueError("Enter the delivery vehicle number.")
            if not driver_name:
                raise ValueError("Enter the driver's name.")
            if not driver_phone:
                raise ValueError("Enter the driver's phone number.")

        try:
            receipt_date = parse_flexible_date(self.date_entry.get()).isoformat()
            invoice_qty = float(self.invoice_quantity_entry.get())
            actual_qty = float(self.actual_quantity_entry.get())
            unit_cost = float(self.cost_entry.get())
        except ValueError:
            raise ValueError(
                "Enter a valid date (DD-MM-YY), quantities, and cost."
            )

        if invoice_qty <= 0 or actual_qty <= 0 or unit_cost <= 0:
            raise ValueError(
                "Invoice quantity, actual quantity, and unit cost "
                "must be greater than zero."
            )
        if not all(math.isfinite(value) for value in (
            invoice_qty, actual_qty, unit_cost
        )):
            raise ValueError("Receipt quantities and cost must be finite numbers.")

        variance_litres = actual_qty - invoice_qty
        variance_value = variance_litres * unit_cost
        receipt_cost = actual_qty * unit_cost

        if (self.editing_receipt_id is None
                and selected["stock"] + actual_qty > selected["capacity"]):
            raise ValueError(
                "This delivery would exceed the selected tank's capacity."
            )

        return {
            "tank_id": selected["id"],
            "product": selected["product"],
            "receipt_type": receipt_type,
            "receipt_date": receipt_date,
            "supplier": supplier,
            "invoice_number": invoice_number,
            "delivery_note": delivery_note,
            "invoice_qty": invoice_qty,
            "actual_qty": actual_qty,
            "unit_cost": unit_cost,
            "variance_litres": variance_litres,
            "variance_value": variance_value,
            "receipt_cost": receipt_cost,
            "vehicle": vehicle_number,
            "driver": driver_name,
            "phone": driver_phone,
            "pump_openings": {
                pump_id: entry.get().strip()
                for pump_id, entry in self.pump_meter_entries.items()
            }
        }

    def on_tank_selected(self, _selection=None):
        self.load_pump_meter_inputs()

    def load_pump_meter_inputs(self):
        if not hasattr(self, "pump_meter_frame"):
            return
        for child in self.pump_meter_frame.winfo_children():
            if child is not self.pump_meter_heading:
                child.destroy()
        self.pump_meter_entries.clear()
        selected = self.tank_options.get(self.tank_menu.get())
        if not selected:
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_pump_run_schema(conn)
                pumps = conn.execute("""
                    SELECT id,pump_number FROM pumps
                    WHERE tank_id=? ORDER BY pump_number
                """, (selected["id"],)).fetchall()
                for pump_id, _pump_number in pumps:
                    active = conn.execute("""
                        SELECT product,tank_id,id FROM pump_product_runs
                        WHERE pump_id=? AND status='OPEN'
                        ORDER BY id DESC LIMIT 1
                    """, (pump_id,)).fetchone()
                    if active and (
                        active[1] == selected["id"]
                        and str(active[0]).casefold()
                        == str(selected["product"]).casefold()
                    ):
                        continue
                    previous = opening_meter_for_new_run(conn, pump_id)
                    row = ctk.CTkFrame(self.pump_meter_frame, fg_color="transparent")
                    row.pack(fill="x", pady=2)
                    ctk.CTkLabel(
                        row, text=f"Pump {_pump_number} opening meter (L)",
                        width=250, anchor="w"
                    ).pack(side="left", padx=4)
                    entry = FormattedNumberEntry(
                        row, placeholder_text="Enter physical opening reading"
                    )
                    entry.pack(side="left", fill="x", expand=True, padx=4)
                    if previous is not None:
                        entry.insert(0, f"{previous:.2f}")
                    self.pump_meter_entries[pump_id] = entry
                if not pumps:
                    ctk.CTkLabel(
                        self.pump_meter_frame,
                        text="No pumps are assigned to this tank yet."
                    ).pack(anchor="w")
                elif not self.pump_meter_entries:
                    ctk.CTkLabel(
                        self.pump_meter_frame,
                        text="All connected pumps have an open same-product run; "
                             "this receipt will join those runs without resetting meters."
                    ).pack(anchor="w")
        except sqlite3.Error as error:
            messagebox.showerror(
                "Pump Meter Readings",
                f"Could not load connected pump readings:\n{error}",
                parent=self
            )

    def calculate_receipt(self):
        try:
            data = self.get_form_data()
            variance_label = "OVER" if data["variance_litres"] > 0 else (
                "SHORT" if data["variance_litres"] < 0 else "MATCH"
            )
            self.result_label.configure(
                text=(
                    f"{variance_label}: {data['variance_litres']:+,.2f} L  |  "
                    f"Variance Value: ₦{data['variance_value']:+,.2f}  |  "
                    f"Receipt Cost: ₦{data['receipt_cost']:,.2f}"
                )
            )
        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )

    def save_receipt(self):
        try:
            data = self.get_form_data()

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_fifo_schema(conn)
                ensure_reconciliation_schema(conn)
                ensure_pump_run_schema(conn)
                ensure_supplier_schema(conn)
                cursor = conn.cursor()
                supplier_id = (
                    get_or_create_supplier_id(conn, data["supplier"])
                    if data["receipt_type"] != "Opening Balance" else None
                )

                if self.editing_receipt_id is not None:
                    self.update_receipt(cursor, conn, data, supplier_id)
                    receipt_id = self.editing_receipt_id
                else:
                    cursor.execute("""
                        INSERT INTO fuel_receipts (
                            supplier_name,
                            supplier_id,
                            tank_id,
                            invoice_number,
                            delivery_note,
                            quantity_received,
                            remaining_quantity,
                            cost_price,
                            total_cost,
                            receipt_date,
                            invoice_quantity,
                            product,
                            short_over_litres,
                            variance_value,
                            vehicle_number,
                            driver_name,
                            driver_phone,
                            receipt_type
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        data["supplier"],
                        supplier_id,
                        data["tank_id"],
                        data["invoice_number"],
                        data["delivery_note"],
                        data["actual_qty"],
                        data["actual_qty"],
                        data["unit_cost"],
                        data["receipt_cost"],
                        data["receipt_date"],
                        data["invoice_qty"],
                        data["product"],
                        data["variance_litres"],
                        data["variance_value"],
                        data["vehicle"],
                        data["driver"],
                        data["phone"],
                        data["receipt_type"]
                    ))
                    receipt_id = cursor.lastrowid

                    cursor.execute("""
                        UPDATE tanks
                        SET current_stock = current_stock + ?
                        WHERE id = ?
                    """, (data["actual_qty"], data["tank_id"]))

                    link_receipt_to_product_runs(
                        cursor, receipt_id, data["tank_id"], data["product"],
                        data["actual_qty"], data["receipt_cost"],
                        data["pump_openings"]
                    )

                has_sessions = cursor.execute("""
                    SELECT 1 FROM sqlite_master
                    WHERE type='table' AND name='pump_sessions'
                """).fetchone()
                if has_sessions:
                    rebuild_fifo_product(cursor, data["product"])

            self.load_tanks()
            self.load_receipts()
            self.load_suggestions()

            variance_label = "OVER" if data["variance_litres"] > 0 else (
                "SHORT" if data["variance_litres"] < 0 else "MATCH"
            )
            messagebox.showinfo(
                "Receipt Updated" if self.editing_receipt_id is not None
                else "Receipt Saved",
                f"Fuel receipt {'updated' if self.editing_receipt_id is not None else 'saved'}.\n"
                f"{variance_label}: {data['variance_litres']:+,.2f} L\n"
                f"Variance value: ₦{data['variance_value']:+,.2f}\n"
                f"Receipt cost: ₦{data['receipt_cost']:,.2f}",
                parent=self
            )
            self.clear_form()

        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not save fuel receipt:\n{error}",
                parent=self
            )

    def update_receipt(self, cursor, conn, data, supplier_id):
        receipt_id = self.editing_receipt_id
        old = cursor.execute("""
            SELECT tank_id,product,quantity_received,remaining_quantity
            FROM fuel_receipts WHERE id=?
        """, (receipt_id,)).fetchone()
        if not old:
            raise ValueError("The selected fuel receipt no longer exists.")
        old_tank_id, old_product, old_qty, old_remaining = old
        old_qty = float(old_qty or 0)
        old_remaining = float(old_remaining or 0)
        consumed = old_qty - old_remaining
        changed_source = (
            int(old_tank_id) != int(data["tank_id"])
            or str(old_product).casefold() != str(data["product"]).casefold()
        )
        run_links = cursor.execute("""
            SELECT COUNT(*) FROM pump_run_receipts WHERE receipt_id=?
        """, (receipt_id,)).fetchone()[0]
        if changed_source and (run_links or consumed > 0.000001):
            raise ValueError(
                "Tank or product cannot be changed after this receipt has been "
                "linked to a pump run or consumed. Edit the receipt details "
                "without changing its tank/product."
            )
        remaining = data["actual_qty"] if changed_source else (
            old_remaining + data["actual_qty"] - old_qty
        )
        if remaining < -0.000001:
            raise ValueError(
                "Received quantity cannot be reduced below litres already "
                "consumed from this receipt."
            )

        tank = cursor.execute(
            "SELECT current_stock,capacity FROM tanks WHERE id=?",
            (data["tank_id"],)
        ).fetchone()
        if not tank:
            raise ValueError("The selected tank no longer exists.")
        stock_delta = data["actual_qty"] - old_qty
        new_stock = float(tank[0] or 0) + (
            stock_delta if int(old_tank_id) == int(data["tank_id"])
            else data["actual_qty"]
        )
        if new_stock > float(tank[1] or 0) + 0.000001:
            raise ValueError("This edit would exceed the selected tank's capacity.")

        reconciled_l, reconciled_cost, station_l, station_cost = cursor.execute("""
            SELECT COALESCE(SUM(reconciled_litres),0),
                   COALESCE(SUM(reconciled_cost),0),
                   COALESCE(SUM(station_borne_litres),0),
                   COALESCE(SUM(station_borne_cost),0)
            FROM receipt_short_reconciliations WHERE receipt_id=?
        """, (receipt_id,)).fetchone()
        initial_short = max(data["invoice_qty"] - data["actual_qty"], 0)
        initial_short_cost = initial_short * data["unit_cost"]
        if reconciled_l + station_l > initial_short + 0.005:
            raise ValueError(
                "The edited delivery shortage would be smaller than the "
                "litres already reconciled. Preserve the original quantities "
                "or correct the reconciliation history first."
            )
        if reconciled_cost + station_cost > initial_short_cost + 0.005:
            raise ValueError(
                "The edited delivery shortage cost would be smaller than the "
                "amounts already reconciled or carried by the station."
            )

        if changed_source:
            cursor.execute(
                "UPDATE tanks SET current_stock=current_stock-? WHERE id=?",
                (old_qty, old_tank_id)
            )
            cursor.execute(
                "UPDATE tanks SET current_stock=current_stock+? WHERE id=?",
                (data["actual_qty"], data["tank_id"])
            )
        else:
            cursor.execute(
                "UPDATE tanks SET current_stock=current_stock+? WHERE id=?",
                (stock_delta, data["tank_id"])
            )
        cursor.execute("""
            UPDATE fuel_receipts
            SET supplier_name=?,supplier_id=?,tank_id=?,invoice_number=?,delivery_note=?,
                quantity_received=?,remaining_quantity=?,cost_price=?,
                total_cost=?,receipt_date=?,invoice_quantity=?,product=?,
                short_over_litres=?,variance_value=?,vehicle_number=?,
                driver_name=?,driver_phone=?,receipt_type=?
            WHERE id=?
        """, (
            data["supplier"], supplier_id, data["tank_id"], data["invoice_number"],
            data["delivery_note"], data["actual_qty"], max(remaining, 0),
            data["unit_cost"], data["receipt_cost"], data["receipt_date"],
            data["invoice_qty"], data["product"], data["variance_litres"],
            data["variance_value"], data["vehicle"], data["driver"],
            data["phone"], data["receipt_type"], receipt_id
        ))
        cursor.execute("""
            UPDATE pump_run_receipts
            SET quantity_received=?,total_cost=?
            WHERE receipt_id=?
        """, (data["actual_qty"], data["receipt_cost"], receipt_id))
        update_receipt_effective_cost(conn, receipt_id)
        if old_product and str(old_product).casefold() != str(data["product"]).casefold():
            rebuild_fifo_product(cursor, old_product)

    def load_receipts(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        r.id,
                        r.receipt_date,
                        COALESCE(t.tank_number, ''),
                        r.product,
                        r.invoice_quantity,
                        r.quantity_received,
                        r.short_over_litres,
                        r.cost_price,
                        r.total_cost,
                        r.remaining_quantity,
                        r.vehicle_number,
                        r.driver_name,
                        r.driver_phone
                    FROM (
                        SELECT * FROM fuel_receipts
                        ORDER BY date(receipt_date) DESC,id DESC
                        LIMIT 100
                    ) r
                    LEFT JOIN tanks t ON t.id = r.tank_id
                    ORDER BY date(r.receipt_date), r.id
                """)
                rows = cursor.fetchall()

            for row in rows:
                (receipt_id, receipt_date, tank, product, invoice_l, actual_l,
                 variance_l, unit_cost, total_cost, stock, vehicle, driver,
                 phone) = row
                with sqlite3.connect(DATABASE, timeout=10) as conn:
                    station_cost = conn.execute("""
                        SELECT COALESCE(SUM(station_borne_cost),0)
                        FROM receipt_short_reconciliations WHERE receipt_id=?
                    """, (receipt_id,)).fetchone()[0]
                adjusted_cost = float(total_cost or 0) + float(station_cost or 0)
                values = (
                    format_display_date(receipt_date), tank, product,
                    f"{float(invoice_l or 0):,.2f}",
                    f"{float(actual_l or 0):,.2f}",
                    f"{float(variance_l or 0):+,.2f}",
                    f"₦{float(unit_cost or 0):,.2f}",
                    f"₦{float(total_cost or 0):,.2f}",
                    f"{float(stock or 0):,.2f}",
                    vehicle, driver, phone,
                    f"₦{adjusted_cost:,.2f}",
                )
                self.tree.insert("", "end", iid=str(receipt_id), values=values)

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load receipts:\n{error}",
                parent=self
            )

    def select_receipt(self, _event=None):
        selected = self.tree.selection()
        self.selected_receipt_id = int(selected[0]) if selected else None

    def edit_selected_receipt(self):
        if self.selected_receipt_id is None:
            messagebox.showwarning(
                "Select Receipt", "Select a fuel receipt first.", parent=self
            )
            return
        receipt_id = self.selected_receipt_id
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT supplier_name,tank_id,invoice_number,delivery_note,
                           receipt_date,invoice_quantity,quantity_received,
                           cost_price,vehicle_number,driver_name,driver_phone,
                           receipt_type
                    FROM fuel_receipts WHERE id=?
                """, (receipt_id,)).fetchone()
            if not row:
                raise ValueError("The selected fuel receipt no longer exists.")
            entries = (
                self.supplier_entry, self.invoice_entry, self.delivery_entry,
                self.date_entry, self.invoice_quantity_entry,
                self.actual_quantity_entry, self.cost_entry,
                self.vehicle_entry, self.driver_entry, self.driver_phone_entry,
            )
            values = (
                row[0], row[2], row[3], format_display_date(row[4]), row[5], row[6],
                row[7], row[8], row[9], row[10],
            )
            for entry, value in zip(entries, values):
                entry.delete(0, "end")
                entry.insert(0, str(value or ""))
            tank_label = next(
                (label for label, tank in self.tank_options.items()
                 if tank["id"] == row[1]),
                None,
            )
            if tank_label is None:
                raise ValueError("The receipt's tank could not be found.")
            self.tank_menu.set(tank_label)
            self.receipt_type_menu.set(row[11] or "Delivery")
            self.editing_receipt_id = receipt_id
            self.save_receipt_button.configure(text="Update Fuel Receipt")
            self.load_pump_meter_inputs()
            messagebox.showinfo(
                "Editing Fuel Receipt",
                f"Receipt #{receipt_id} loaded. Saving will update its stock "
                "and FIFO cost. A tank/product change is blocked after pump "
                "run linkage or sales consumption.",
                parent=self,
            )
        except (sqlite3.Error, ValueError) as error:
            messagebox.showerror("Edit Fuel Receipt", str(error), parent=self)

    def reconcile_selected_receipt(self):
        if self.selected_receipt_id is None:
            messagebox.showwarning(
                "Select Receipt", "Select a fuel receipt first.", parent=self
            )
            return
        receipt_id = self.selected_receipt_id
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT supplier_name,driver_name,vehicle_number,
                           COALESCE(invoice_quantity,quantity_received),
                           COALESCE(quantity_received,0),COALESCE(cost_price,0),
                           COALESCE(total_cost,0),
                           COALESCE(effective_cost_price,cost_price)
                    FROM fuel_receipts WHERE id=?
                """, (receipt_id,)).fetchone()
                if not row:
                    raise ValueError("The selected fuel receipt was not found.")
                initial_l, initial_cost, open_l, open_cost = receipt_short_amounts(
                    conn, receipt_id
                )
                station_cost = conn.execute("""
                    SELECT COALESCE(SUM(station_borne_cost),0)
                    FROM receipt_short_reconciliations WHERE receipt_id=?
                """, (receipt_id,)).fetchone()[0]
        except (sqlite3.Error, ValueError) as error:
            messagebox.showerror("Receipt Reconciliation", str(error), parent=self)
            return
        if initial_l <= 0 or (open_l <= 0 and open_cost <= 0):
            messagebox.showinfo(
                "No Outstanding Shortage",
                "This receipt has no outstanding delivery shortage to reconcile.",
                parent=self
            )
            return

        window = ctk.CTkToplevel(self)
        window.title(f"Receipt #{receipt_id} Shortage Reconciliation")
        window.geometry("560x600")
        window.transient(self.winfo_toplevel())
        adjusted_receipt_cost = float(row[6] or 0) + float(station_cost or 0)
        adjusted_unit_cost = (
            adjusted_receipt_cost / float(row[4]) if float(row[4] or 0) else 0
        )
        invoice_cost = float(row[3] or 0) * float(row[5] or 0)
        ctk.CTkLabel(
            window,
            text=(f"Receipt #{receipt_id}: initial shortage {initial_l:,.2f} L "
                  f"(₦{initial_cost:,.2f}); outstanding "
                  f"{open_l:,.2f} L (₦{open_cost:,.2f})\n"
                  f"Invoice cost ₦{invoice_cost:,.2f} less driver/supplier "
                  f"recovery ₦{float(recovered_cost or 0):,.2f} = "
                  f"reconciled price ₦{invoice_cost-float(recovered_cost or 0):,.2f}.\n"
                  f"Received product cost ₦{float(row[6] or 0):,.2f} plus "
                  f"station share ₦{float(station_cost or 0):,.2f} = "
                  f"₦{adjusted_receipt_cost:,.2f} "
                  f"(₦{adjusted_unit_cost:,.2f}/L)."),
            wraplength=520, justify="left"
        ).pack(anchor="w", padx=16, pady=(16, 10))
        party_type = ctk.CTkOptionMenu(
            window, values=["Supplier", "Driver"]
        )
        party_type.pack(fill="x", padx=16, pady=5)
        party_name = ctk.CTkEntry(window, placeholder_text="Responsible party name")
        party_name.pack(fill="x", padx=16, pady=5)
        def choose_party(value):
            party_name.delete(0, "end")
            party_name.insert(0, {
                "Supplier": row[0] or "",
                "Driver": row[1] or "",
            }[value])
        party_type.configure(command=choose_party)
        choose_party("Supplier")

        entries = {}
        for key, placeholder in (
            ("settled_l", "Litres settled / credited by supplier or driver"),
            ("settled_cost", "NGN cost recovered / credited"),
            ("station_l", "Litres borne by station"),
            ("station_cost", "NGN cost borne by station"),
        ):
            entries[key] = FormattedNumberEntry(
                window, placeholder_text=placeholder
            )
            entries[key].pack(fill="x", padx=16, pady=5)
            entries[key].insert(0, "0")
        disputed = ctk.CTkCheckBox(window, text="Still disputed")
        disputed.pack(anchor="w", padx=16, pady=5)
        settled_date = ctk.CTkEntry(window, placeholder_text="Settlement date")
        settled_date.pack(fill="x", padx=16, pady=5)
        settled_date.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(settled_date)
        ctk.CTkLabel(
            window, text="Notes / evidence reference (optional)"
        ).pack(anchor="w", padx=16, pady=(6, 0))
        notes = ctk.CTkTextbox(window, height=100)
        notes.pack(fill="both", expand=True, padx=16, pady=5)

        def save_reconciliation():
            try:
                values = [entries[key].get().replace(",", "").strip() or "0"
                          for key in ("settled_l", "settled_cost",
                                      "station_l", "station_cost")]
                if not messagebox.askyesno(
                    "Confirm Receipt Reconciliation",
                    "Save this settlement and station-borne amount to the receipt audit ledger?",
                    parent=window
                ):
                    return
                reconcile_receipt_short(
                    DATABASE, receipt_id, party_type.get(), party_name.get(),
                    *values, disputed.get(), settled_date.get(),
                    notes.get("1.0", "end").strip()
                )
                self.load_receipts()
                window.destroy()
                messagebox.showinfo(
                    "Reconciled", "Receipt shortage reconciliation saved.",
                    parent=self
                )
            except (ValueError, sqlite3.Error) as error:
                messagebox.showerror("Reconciliation Error", str(error), parent=window)

        Theme.primary_button(
            window, "Save Reconciliation", save_reconciliation
        ).pack(pady=12)

    def open_shortage_ledger(self):
        window = ctk.CTkToplevel(self)
        window.title("Delivery Shortage Responsibility Ledger")
        window.geometry("1100x650")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window, text="Supplier / Driver Shortage Balances",
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", padx=16, pady=(14, 6))
        ctk.CTkLabel(
            window,
            text=("Only suppliers and drivers can be responsible for an outstanding "
                  "delivery shortage. A truck number identifies the delivery vehicle "
                  "and is shown in the receipt history, not as a liable party. Initial "
                  "shortage is the original audit amount; outstanding is what remains "
                  "after recoveries and station-borne amounts."),
            wraplength=1050, justify="left"
        ).pack(anchor="w", padx=16, pady=(0, 8))
        columns = ("Party type", "Party", "Deliveries", "Initial short L",
                   "Initial cost NGN", "Outstanding L", "Outstanding NGN")
        tree = ttk.Treeview(window, columns=columns, show="headings", height=10)
        for column, width in zip(columns, (110, 220, 100, 140, 160, 140, 160)):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        tree.pack(fill="both", expand=True, padx=14, pady=8)
        history_columns = ("Date", "Receipt", "Invoice", "Truck / Vehicle",
                           "Responsible party", "Invoice L", "Received L",
                           "Initial short L", "Outstanding L", "Outstanding NGN")
        history = ttk.Treeview(window, columns=history_columns, show="headings", height=8)
        for column, width in zip(history_columns, (100, 75, 110, 130, 150, 90, 90, 110, 110, 130)):
            history.heading(column, text=column)
            history.column(column, width=width, anchor="center")
        history.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        entity_rows = {}
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_reconciliation_schema(conn)
                receipts = conn.execute("""
                    SELECT id,receipt_date,supplier_name,driver_name,vehicle_number,
                           invoice_number,invoice_quantity,quantity_received,cost_price
                    FROM fuel_receipts ORDER BY date(receipt_date),id
                """).fetchall()
                for receipt in receipts:
                    receipt_id = receipt[0]
                    initial_l, initial_cost, outstanding_l, outstanding_cost = (
                        receipt_short_amounts(conn, receipt_id)
                    )
                    if initial_l <= 0.005 and initial_cost <= 0.005:
                        continue
                    responsible = conn.execute("""
                        SELECT party_type,party_name
                        FROM receipt_short_reconciliations
                        WHERE receipt_id=? AND party_type IN ('Supplier','Driver')
                        ORDER BY date(settlement_date) DESC,id DESC LIMIT 1
                    """, (receipt_id,)).fetchone()
                    if responsible:
                        kind, party = responsible
                    else:
                        kind, party = "Supplier", receipt[2]
                    party = str(party or "").strip()
                    if not party or party.upper() == "N/A":
                        continue
                    key = (kind, party.casefold())
                    summary = entity_rows.setdefault(key, {
                        "party": party, "count": 0, "initial_l": 0.0,
                        "initial_cost": 0.0, "open_l": 0.0, "open_cost": 0.0,
                        "receipts": [],
                    })
                    summary["count"] += 1
                    summary["initial_l"] += initial_l
                    summary["initial_cost"] += initial_cost
                    summary["open_l"] += outstanding_l
                    summary["open_cost"] += outstanding_cost
                    summary["receipts"].append(
                        (receipt_id, receipt[1], receipt[5], receipt[6],
                         receipt[7], initial_l, outstanding_l, outstanding_cost,
                         receipt[4], kind, party)
                    )
            for (kind, key), data in entity_rows.items():
                tree.insert("", "end", iid=f"{kind}|{key}", values=(
                    kind, data["party"], data["count"],
                    f"{data['initial_l']:,.2f}", f"₦{data['initial_cost']:,.2f}",
                    f"{data['open_l']:,.2f}", f"₦{data['open_cost']:,.2f}"
                ))
        except sqlite3.Error as error:
            messagebox.showerror("Shortage Ledger", str(error), parent=window)

        def show_party_history(_event=None):
            history.delete(*history.get_children())
            selected = tree.selection()
            if not selected:
                return
            kind, key = selected[0].split("|", 1)
            data = entity_rows[(kind, key)]
            for (receipt_id, receipt_date, invoice, invoice_l, received_l,
                 short_l, open_l, open_cost, vehicle, kind, party) in data["receipts"]:
                history.insert("", "end", values=(
                    format_display_date(receipt_date), f"#{receipt_id}", invoice,
                    vehicle, f"{kind}: {party}",
                    f"{float(invoice_l or 0):,.2f}",
                    f"{float(received_l or 0):,.2f}",
                    f"{short_l:,.2f}", f"{open_l:,.2f}", f"₦{open_cost:,.2f}"
                ))
        tree.bind("<<TreeviewSelect>>", show_party_history)
        first_item = tree.get_children()
        if first_item:
            tree.selection_set(first_item[0])
            tree.focus(first_item[0])
            show_party_history()
        else:
            ctk.CTkLabel(
                window,
                text="No outstanding supplier or driver shortage balances.",
            ).pack(anchor="w", padx=16, pady=(0, 10))

    def open_receipt_history(self):
        if self.selected_receipt_id is None:
            messagebox.showwarning(
                "Select Receipt", "Select a fuel receipt first.", parent=self
            )
            return
        receipt_id = self.selected_receipt_id
        window = ctk.CTkToplevel(self)
        window.title(f"Receipt #{receipt_id} Reconciliation History")
        window.geometry("900x520")
        window.transient(self.winfo_toplevel())
        columns = ("Date", "Party type", "Responsible party", "Settled L",
                   "Recovered/credited NGN", "Station borne L",
                   "Station borne NGN", "Disputed", "Notes / evidence")
        tree = ttk.Treeview(window, columns=columns, show="headings")
        for column, width in zip(
            columns, (100, 100, 150, 110, 165, 120, 160, 90, 260)
        ):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        tree.pack(fill="both", expand=True, padx=12, pady=12)
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                rows = conn.execute("""
                    SELECT settlement_date,party_type,party_name,
                           reconciled_litres,reconciled_cost,
                           station_borne_litres,station_borne_cost,
                           disputed,COALESCE(notes,'')
                    FROM receipt_short_reconciliations
                    WHERE receipt_id=? ORDER BY date(settlement_date),id
                """, (receipt_id,)).fetchall()
            for row in rows:
                tree.insert("", "end", values=(
                    format_display_date(row[0]), row[1], row[2], f"{float(row[3] or 0):,.2f}",
                    f"₦{float(row[4] or 0):,.2f}",
                    f"{float(row[5] or 0):,.2f}",
                    f"₦{float(row[6] or 0):,.2f}",
                    "Yes" if row[7] else "No", row[8],
                ))
        except sqlite3.Error as error:
            messagebox.showerror("Receipt History", str(error), parent=window)

    def clear_form(self):
        self.selected_receipt_id = None
        self.editing_receipt_id = None
        self.save_receipt_button.configure(text="Save Fuel Receipt")
        self.tree.selection_remove(self.tree.selection())
        for entry in (
            self.supplier_entry,
            self.invoice_entry,
            self.delivery_entry,
            self.invoice_quantity_entry,
            self.actual_quantity_entry,
            self.cost_entry,
            self.vehicle_entry,
            self.driver_entry,
            self.driver_phone_entry
        ):
            entry.delete(0, "end")

        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))
        self.receipt_type_menu.set("Delivery")
        self.load_pump_meter_inputs()
        self.result_label.configure(
            text=(
                "Short/Over: 0.00 L  |  Variance Value: ₦0.00  |  "
                "Receipt Cost: ₦0.00"
            )
        )
