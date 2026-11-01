import sqlite3
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk
from theme import Theme
from date_utils import format_display_date


from app_settings import get_active_database

DATABASE = get_active_database()


class PumpWindow(ctk.CTkFrame):

    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)

        self.pump_id = None
        self.tank_options = {}

        self.prepare_database()
        self.build_ui()
        self.load_tanks()
        self.load_pumps()

    def prepare_database(self):
        """Create pumps table or add tank_id to an existing table."""
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pumps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pump_number TEXT NOT NULL,
                        tank_id INTEGER
                    )
                """)

                cursor.execute("PRAGMA table_info(pumps)")
                columns = [column[1] for column in cursor.fetchall()]

                if "tank_id" not in columns:
                    cursor.execute("""
                        ALTER TABLE pumps
                        ADD COLUMN tank_id INTEGER
                    """)

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not prepare the database:\n{error}",
                parent=self
            )

    def build_ui(self):
        ctk.CTkLabel(
            self,
            text="Pump Management",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=15)

        self.pump_entry = ctk.CTkEntry(
            self,
            placeholder_text="Pump Number (enter manually)"
        )
        self.pump_entry.pack(padx=20, pady=8, fill="x")

        self.tank_menu = ctk.CTkOptionMenu(
            self,
            values=["Loading tanks..."]
        )
        self.tank_menu.pack(padx=20, pady=8, fill="x")

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=10)

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Save New Pump",
            command=self.save_pump
        )
        self.save_button.pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Update",
            command=self.update_pump
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Delete",
            fg_color="#b3261e",
            hover_color="#8c1d18",
            command=self.delete_pump
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Clear",
            command=self.clear_form
        ).pack(side="left", padx=5, pady=6)

        columns = (
            "ID",
            "Pump",
            "Tank Number",
            "Tank Product",
            "Tank Name",
            "Sales Details",
        )

        self.tree = ttk.Treeview(
            self,
            columns=columns,
            displaycolumns=("Pump", "Tank Number", "Tank Product", "Tank Name",
                            "Sales Details"),
            show="headings"
        )

        headings = {
            "ID": "Record ID",
            "Pump": "Pump Number",
            "Tank Number": "Assigned Tank Number",
            "Tank Product": "Product",
            "Tank Name": "Tank Name",
            "Sales Details": "Sales",
        }

        widths = {
            "ID": 75,
            "Pump": 140,
            "Tank Number": 180,
            "Tank Product": 120,
            "Tank Name": 200,
            "Sales Details": 115,
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                anchor="center"
            )

        self.tree.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=10
        )
        self.tree.bind("<<TreeviewSelect>>", self.select_record)
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")
        self.tree.bind("<Double-1>", self.open_selected_pump_details)

    def load_tanks(self):
        """Dropdown labels show manually entered tank number and product."""
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, tank_number, name, product
                    FROM tanks
                    WHERE COALESCE(is_active,1)=1
                      AND tank_number IS NOT NULL
                      AND TRIM(tank_number) <> ''
                    ORDER BY tank_number
                """)
                tanks = cursor.fetchall()

            self.tank_options.clear()

            choices = []
            for tank_id, tank_number, tank_name, product in tanks:
                label = f"{tank_number} | {product} | {tank_name}"
                self.tank_options[label] = {
                    "id": tank_id,
                    "tank_number": tank_number,
                    "product": product,
                    "name": tank_name
                }
                choices.append(label)

            if not choices:
                choices = ["No numbered tanks - add tank numbers first"]

            self.tank_menu.configure(values=choices)
            self.tank_menu.set(choices[0])

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load tanks:\n{error}",
                parent=self
            )

    def get_selected_tank_id(self):
        selected_label = self.tank_menu.get()
        tank_data = self.tank_options.get(selected_label)

        if tank_data is None:
            return None

        return tank_data["id"]

    def load_pumps(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT
                        p.id,
                        p.pump_number,
                        COALESCE(t.tank_number, 'Not assigned'),
                        COALESCE(t.product, ''),
                        COALESCE(t.name, ''),
                        'View details'
                    FROM pumps AS p
                    LEFT JOIN tanks AS t
                        ON p.tank_id = t.id
                    ORDER BY p.id
                """)
                pumps = cursor.fetchall()

            for pump in pumps:
                self.tree.insert("", "end", values=pump)

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load pumps:\n{error}",
                parent=self
            )

    def on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#5":
            return
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.open_pump_details(int(self.tree.item(item, "values")[0]))
            return "break"

    def open_selected_pump_details(self, event=None):
        selected = self.tree.selection()
        if selected:
            self.open_pump_details(int(self.tree.item(selected[0], "values")[0]))

    def open_pump_details(self, pump_id):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                pump = conn.execute("""
                    SELECT p.pump_number,COALESCE(t.product,''),p.tank_id
                    FROM pumps p LEFT JOIN tanks t ON t.id=p.tank_id
                    WHERE p.id=?
                """, (pump_id,)).fetchone()
                if not pump:
                    raise ValueError("The selected pump could not be found.")
                receipts = conn.execute("""
                    SELECT fr.id,fr.receipt_date,fr.invoice_number,
                           fr.product,r.id
                    FROM pump_run_receipts rr
                    JOIN pump_product_runs r ON r.id=rr.run_id
                    JOIN fuel_receipts fr ON fr.id=rr.receipt_id
                    WHERE r.pump_id=?
                    ORDER BY date(fr.receipt_date),fr.id
                """, (pump_id,)).fetchall()
        except (sqlite3.Error, ValueError) as error:
            messagebox.showerror("Pump Sales Error", str(error), parent=self)
            return

        window = ctk.CTkToplevel(self)
        window.title(f"Pump {pump[0]} Sales Details")
        window.geometry("900x520")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window,
            text=f"Pump {pump[0]} — {pump[1] or 'Product not assigned'}",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 4))
        receipt_options = {
            f"#{receipt[0]} | {format_display_date(receipt[1])} | {receipt[2] or 'No invoice'} | "
            f"{receipt[3] or ''}": (receipt[0], receipt[4])
            for receipt in receipts
        }
        if not receipt_options:
            ctk.CTkLabel(
                window,
                text="No receipt/product run is linked to this pump yet."
            ).pack(anchor="w", padx=18, pady=8)
            return
        receipt_menu = ctk.CTkOptionMenu(
            window, values=list(receipt_options)
        )
        receipt_menu.pack(fill="x", padx=18, pady=6)
        summary = ctk.CTkLabel(window, text="", justify="left")
        summary.pack(anchor="w", padx=18, pady=(4, 10))

        frame = ctk.CTkFrame(window)
        frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        columns = ("Date", "Receipt", "Product", "Starting meter",
                   "Ending meter", "Gross meter L", "RTT L", "Net sold L")
        tree = ttk.Treeview(frame, columns=columns, show="headings")
        for column, width in zip(columns, (105, 105, 110, 125, 125, 120, 90, 110)):
            tree.heading(column, text=column)
            tree.column(column, width=width, anchor="center")
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def load_receipt_breakdown(_selection=None):
            receipt_id, run_id = receipt_options[receipt_menu.get()]
            try:
                with sqlite3.connect(DATABASE, timeout=10) as conn:
                    run = conn.execute("""
                        SELECT product,opening_meter,closing_meter,status
                        FROM pump_product_runs WHERE id=? AND pump_id=?
                    """, (run_id, pump_id)).fetchone()
                    linked = conn.execute("""
                        SELECT fr.id,fr.invoice_number,fr.quantity_received,fr.total_cost
                        FROM pump_run_receipts rr
                        JOIN fuel_receipts fr ON fr.id=rr.receipt_id
                        WHERE rr.run_id=? ORDER BY fr.id
                    """, (run_id,)).fetchall()
                    shift_rows = conn.execute("""
                        SELECT ps.session_date,ps.opening_meter,ps.closing_meter,
                               COALESCE(ps.rtt_litres,0),
                               COALESCE(ps.litres_sold,0)
                        FROM pump_sessions ps WHERE ps.run_id=?
                        ORDER BY date(ps.session_date),ps.id
                    """, (run_id,)).fetchall()
                if not run:
                    raise ValueError("The linked product run was not found.")
                run_rtt = sum(float(item[3] or 0) for item in shift_rows)
                run_sold = sum(float(item[4] or 0) for item in shift_rows)
                gross = (
                    float(run[2]) - float(run[1])
                    if run[1] is not None and run[2] is not None else 0.0
                )
                linked_label = "; ".join(
                    f"#{item[0]} {item[1] or ''}: {float(item[2] or 0):,.2f} L "
                    f"(NGN {float(item[3] or 0):,.2f})"
                    for item in linked
                )
                summary.configure(text=(
                    f"Receipt #{receipt_id} — shared run #{run_id} ({run[3]}), "
                    f"{run[0]}. Linked receipts: {linked_label}\n"
                    f"Run totals for this pump: gross meter {gross:,.2f} L, "
                    f"RTT {run_rtt:,.2f} L, net litres sold {run_sold:,.2f} L. "
                    "Overlapping same-product receipts intentionally share these totals."
                ))
                tree.delete(*tree.get_children())
                for shift in shift_rows:
                    tree.insert("", "end", values=(
                        format_display_date(str(shift[0] or "")[:10]),
                        f"#{receipt_id}",
                        run[0],
                        f"{float(shift[1] or 0):,.2f}",
                        f"{float(shift[2] or 0):,.2f}",
                        f"{float(shift[2] or 0)-float(shift[1] or 0):,.2f}",
                        f"{float(shift[3] or 0):,.2f}",
                        f"{float(shift[4] or 0):,.2f}",
                    ))
            except (sqlite3.Error, ValueError) as error:
                messagebox.showerror("Pump Sales Error", str(error), parent=window)

        receipt_menu.configure(command=load_receipt_breakdown)
        load_receipt_breakdown()

    def pump_number_exists(self, pump_number, exclude_id=None):
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            cursor = conn.cursor()

            if exclude_id is None:
                cursor.execute(
                    "SELECT id FROM pumps WHERE pump_number=?",
                    (pump_number,)
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM pumps
                    WHERE pump_number=? AND id<>?
                    """,
                    (pump_number, exclude_id)
                )

            return cursor.fetchone() is not None

    def save_pump(self):
        if self.pump_id is not None:
            self.update_pump()
            return
        pump_number = self.pump_entry.get().strip()
        tank_id = self.get_selected_tank_id()

        if not pump_number:
            messagebox.showwarning(
                "Pump Number",
                "Enter a pump number.",
                parent=self
            )
            return

        if tank_id is None:
            messagebox.showwarning(
                "Tank Number",
                "Select a numbered tank. Add a tank number in Tank Management first.",
                parent=self
            )
            return

        try:
            if self.pump_number_exists(pump_number):
                messagebox.showwarning(
                    "Duplicate Pump",
                    "That pump number already exists. Select it and use Update.",
                    parent=self
                )
                return

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                conn.execute("""
                    INSERT INTO pumps (pump_number, tank_id)
                    VALUES (?, ?)
                """, (pump_number, tank_id))

            self.load_pumps()
            self.clear_form()

            messagebox.showinfo(
                "Success",
                "Pump saved and assigned to the selected tank.",
                parent=self
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not save pump:\n{error}",
                parent=self
            )

    def update_pump(self):
        if self.pump_id is None:
            messagebox.showwarning(
                "Select Pump",
                "Select a pump from the table first.",
                parent=self
            )
            return

        if not self.authorize_change("update this pump"):
            return

        pump_number = self.pump_entry.get().strip()
        tank_id = self.get_selected_tank_id()

        if not pump_number:
            messagebox.showwarning(
                "Pump Number",
                "Enter a pump number.",
                parent=self
            )
            return

        if tank_id is None:
            messagebox.showwarning(
                "Tank Number",
                "Select a numbered tank.",
                parent=self
            )
            return

        try:
            if self.pump_number_exists(pump_number, self.pump_id):
                messagebox.showwarning(
                    "Duplicate Pump",
                    "That pump number is already used by another pump.",
                    parent=self
                )
                return

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                conn.execute("""
                    UPDATE pumps
                    SET pump_number=?, tank_id=?
                    WHERE id=?
                """, (pump_number, tank_id, self.pump_id))

            self.load_pumps()
            self.clear_form()

            messagebox.showinfo(
                "Success",
                "Pump updated successfully.",
                parent=self
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not update pump:\n{error}",
                parent=self
            )

    def delete_pump(self):
        if self.pump_id is None:
            messagebox.showwarning(
                "Select Pump",
                "Select a pump from the table first.",
                parent=self
            )
            return

        if not self.authorize_change("delete this pump"):
            return

        if not messagebox.askyesno(
            "Delete Pump",
            "Delete the selected pump?",
            parent=self
        ):
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                conn.execute(
                    "DELETE FROM pumps WHERE id=?",
                    (self.pump_id,)
                )

            self.load_pumps()
            self.clear_form()

            messagebox.showinfo(
                "Success",
                "Pump deleted successfully.",
                parent=self
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not delete pump:\n{error}",
                parent=self
            )

    def select_record(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")
        self.pump_id = int(values[0])
        self.save_button.configure(text="Save Changes to Selected Pump")

        self.pump_entry.delete(0, "end")
        self.pump_entry.insert(0, values[1])

        # Find the dropdown label for this row's tank number and product.
        target_number = values[2]
        target_product = values[3]
        target_name = values[4]

        for label, tank_data in self.tank_options.items():
            if (
                tank_data["tank_number"] == target_number
                and tank_data["product"] == target_product
                and tank_data["name"] == target_name
            ):
                self.tank_menu.set(label)
                break

    def clear_form(self):
        self.pump_id = None
        self.save_button.configure(text="Save New Pump")
        self.pump_entry.delete(0, "end")

        choices = self.tank_menu.cget("values")
        if choices:
            self.tank_menu.set(choices[0])

        for item in self.tree.selection():
            self.tree.selection_remove(item)

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
