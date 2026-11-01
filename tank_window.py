import sqlite3
from tkinter import BooleanVar, messagebox, simpledialog, ttk

import customtkinter as ctk

from dip_window import DipWindow
from date_utils import format_display_date
from pump_runs import close_tank_product
from report_data import tank_dip_variance_adjustments
from theme import Theme
from number_entry import FormattedNumberEntry
from weekly_reports import send_product_finished_email


from app_settings import get_active_database

DATABASE = get_active_database()


class TankWindow(ctk.CTkFrame):

    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)

        self.tank_id = None
        self.show_archived = BooleanVar(value=False)

        self.prepare_database()
        self.build_ui()
        self.load_tanks()

    def prepare_database(self):
        """Create required tables and add missing tank columns."""
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tanks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        product TEXT NOT NULL,
                        capacity REAL NOT NULL,
                        current_stock REAL NOT NULL DEFAULT 0
                    )
                """)

                cursor.execute("PRAGMA table_info(tanks)")
                columns = [column[1] for column in cursor.fetchall()]

                if "tank_number" not in columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN tank_number TEXT
                    """)

                if "current_stock_date" not in columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN current_stock_date TEXT
                    """)

                if "desktop_cost" not in columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN desktop_cost REAL NOT NULL DEFAULT 0
                    """)

                if "is_active" not in columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
                    """)

                cursor.execute("""
                    UPDATE tanks SET tank_number=name
                    WHERE (tank_number IS NULL OR tank_number='')
                      AND name IS NOT NULL
                """)

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pumps (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        pump_number TEXT NOT NULL,
                        tank_id INTEGER
                    )
                """)

                cursor.execute("PRAGMA table_info(pumps)")
                pump_columns = [column[1] for column in cursor.fetchall()]

                if "tank_id" not in pump_columns:
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
            text="Tank Management",
            font=("Segoe UI", 22, "bold")
        ).pack(pady=12)

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabs.add("Tanks")
        self.tabs.add("Tank Dips")

        tank_tab = self.tabs.tab("Tanks")
        dip_tab = self.tabs.tab("Tank Dips")

        self.tank_number_entry = ctk.CTkEntry(
            tank_tab,
            placeholder_text="Tank Number (enter manually, e.g. TANK-01)"
        )
        self.tank_number_entry.pack(padx=20, pady=5, fill="x")

        self.name_entry = ctk.CTkEntry(
            tank_tab,
            placeholder_text="Tank Name"
        )
        self.name_entry.pack(padx=20, pady=5, fill="x")

        self.product_menu = ctk.CTkOptionMenu(
            tank_tab,
            values=["PMS", "AGO"]
        )
        self.product_menu.pack(padx=20, pady=5, fill="x")

        self.capacity_entry = FormattedNumberEntry(
            tank_tab,
            placeholder_text="Capacity in litres"
        )
        self.capacity_entry.pack(padx=20, pady=5, fill="x")

        button_frame = ctk.CTkFrame(tank_tab)
        button_frame.pack(pady=10)

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Save New Tank",
            command=self.save_tank
        )
        self.save_button.pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Update Tank",
            command=self.update_tank
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Archive Tank",
            fg_color="#b3261e",
            hover_color="#8c1d18",
            command=self.delete_tank
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Restore Tank",
            command=self.restore_tank
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkCheckBox(
            button_frame,
            text="Show archived",
            variable=self.show_archived,
            command=self.load_tanks
        ).pack(side="left", padx=8, pady=6)

        ctk.CTkButton(
            button_frame,
            text="Clear",
            command=self.clear_form
        ).pack(side="left", padx=5, pady=6)

        tool_frame = ctk.CTkFrame(tank_tab)
        tool_frame.pack(pady=5)

        ctk.CTkButton(
            tool_frame,
            text="Enter Tank Dip",
            command=self.open_tank_dips
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            tool_frame,
            text="Dip History",
            command=self.open_dip_history
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkButton(
            tool_frame,
            text="Product Finished",
            fg_color="#6D28D9",
            hover_color="#5B21B6",
            command=self.finish_tank_product
        ).pack(side="left", padx=5, pady=6)

        ctk.CTkLabel(
            tank_tab,
            text="PMS = Blue     |     AGO = Yellow",
            font=("Segoe UI", 12)
        ).pack(pady=(4, 0))

        columns = (
            "Tank Number",
            "Name",
            "Product",
            "Capacity",
            "Stock",
            "Stock Date",
            "Status",
            "Dip Variance",
        )

        self.tree = ttk.Treeview(
            tank_tab,
            columns=columns,
            displaycolumns=(
                "Name", "Product", "Capacity", "Stock", "Stock Date",
                "Status", "Dip Variance",
            ),
            show="headings"
        )

        headings = {
            "Tank Number": "Tank Number",
            "Name": "Tank Name",
            "Product": "Product",
            "Capacity": "Capacity (L)",
            "Stock": "Current Stock (L)",
            "Stock Date": "Stock Date",
            "Status": "Status",
            "Dip Variance": "Dip Variance",
        }

        widths = {
            "Tank Number": 130,
            "Name": 150,
            "Product": 90,
            "Capacity": 120,
            "Stock": 150,
            "Stock Date": 120,
            "Status": 100,
            "Dip Variance": 115,
        }

        for column in columns:
            self.tree.heading(column, text=headings[column])
            self.tree.column(
                column,
                width=widths[column],
                anchor="center"
            )

        self.tree.tag_configure(
            "PMS",
            background="#DCEBFF",
            foreground="#164A8A"
        )
        self.tree.tag_configure(
            "AGO",
            background="#FFF2B2",
            foreground="#664D00"
        )

        self.tree.pack(fill="both", expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self.select_record)
        self.tree.bind("<Button-1>", self.on_tree_click, add="+")

        self.dip_page = DipWindow(dip_tab, tank_id=None, owner=self)
        self.dip_page.pack(fill="both", expand=True)

    def load_tanks(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                status_filter = "" if self.show_archived.get() else "WHERE COALESCE(is_active,1)=1"
                cursor.execute(f"""
                    SELECT
                        id,
                        COALESCE(tank_number, ''),
                        name,
                        product,
                        capacity,
                        current_stock,
                        COALESCE(current_stock_date, ''),
                        CASE WHEN COALESCE(is_active,1)=1 THEN 'Active' ELSE 'Archived' END,
                        'View details'
                    FROM tanks
                    {status_filter}
                    ORDER BY id
                """)
                tanks = cursor.fetchall()

            for row in tanks:
                (
                    tank_id, number, name, product, capacity, stock,
                    stock_date, status, _details,
                ) = row
                tag = str(product).upper()

                self.tree.insert(
                    "",
                    "end",
                    iid=str(tank_id),
                    values=(
                        number or "Not set",
                        name,
                        product,
                        f"{capacity:,.2f}",
                        f"{(stock or 0):,.2f}",
                        stock_date or "Not recorded",
                        status,
                        "View details",
                    ),
                    tags=(tag,)
                )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load tanks:\n{error}",
                parent=self
            )

    def on_tree_click(self, event):
        if self.tree.identify_region(event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) != "#7":
            return
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.open_tank_dip_variance(int(item))
            return "break"

    def open_tank_dip_variance(self, tank_id):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                tank = conn.execute("""
                    SELECT COALESCE(tank_number,''),COALESCE(name,''),
                           COALESCE(product,'')
                    FROM tanks WHERE id=?
                """, (tank_id,)).fetchone()
                if not tank:
                    raise ValueError("The selected tank could not be found.")
                dates = conn.execute("""
                    SELECT MIN(date(dip_date)),MAX(date(dip_date))
                    FROM tank_dips WHERE tank_id=?
                """, (tank_id,)).fetchone()
                adjustment = {}
                if dates and dates[0] and dates[1]:
                    adjustment = tank_dip_variance_adjustments(
                        conn, dates[0], dates[1], tank_id=tank_id
                    ).get(tank_id, {})
                dip_count = conn.execute(
                    "SELECT COUNT(*) FROM tank_dips WHERE tank_id=?",
                    (tank_id,),
                ).fetchone()[0]
        except (sqlite3.Error, ValueError) as error:
            messagebox.showerror(
                "Tank Dip Details", str(error), parent=self
            )
            return

        window = ctk.CTkToplevel(self)
        window.title(f"Tank {tank[0]} Dip Variance Details")
        window.geometry("560x260")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window,
            text=f"{tank[0]} | {tank[1]} | {tank[2]}",
            font=Theme.SUBHEADING_FONT,
        ).pack(anchor="w", padx=18, pady=(18, 8))
        if dip_count < 2:
            message = (
                "A first dip sets the baseline. Add another tank dip "
                "to calculate overage or shortage."
            )
        else:
            litres = float(adjustment.get("litres", 0.0))
            amount = float(adjustment.get("amount", 0.0))
            if litres > 0:
                variance_label = f"Total overage: {litres:+,.2f} L"
            elif litres < 0:
                variance_label = f"Total shortage: {litres:,.2f} L"
            else:
                variance_label = "Total overage/shortage: 0.00 L"
            amount_label = (
                f"Cumulative value at effective selling prices: "
                f"₦{amount:+,.2f}"
            )
            message = (
                f"{variance_label}\n{amount_label}\n\n"
                f"From {format_display_date(dates[0])} through "
                f"{format_display_date(dates[1])}"
            )
        ctk.CTkLabel(
            window,
            text=message,
            font=Theme.BODY_FONT,
            justify="left",
        ).pack(anchor="w", padx=18, pady=8)

    def get_form_values(self):
        tank_number = self.tank_number_entry.get().strip()
        tank_name = self.name_entry.get().strip()
        product = self.product_menu.get()

        if not tank_number:
            raise ValueError("Enter a tank number.")

        if not tank_name:
            raise ValueError("Enter a tank name.")

        try:
            capacity = float(self.capacity_entry.get())
        except ValueError:
            raise ValueError("Capacity must be a number.")

        if capacity <= 0:
            raise ValueError("Capacity must be greater than zero.")

        return tank_number, tank_name, product, capacity

    def tank_number_is_used(self, tank_number, exclude_id=None):
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            cursor = conn.cursor()

            if exclude_id is None:
                cursor.execute(
                    "SELECT id FROM tanks WHERE tank_number=?",
                    (tank_number,)
                )
            else:
                cursor.execute(
                    """
                    SELECT id FROM tanks
                    WHERE tank_number=? AND id<>?
                    """,
                    (tank_number, exclude_id)
                )

            return cursor.fetchone() is not None

    def save_tank(self):
        if self.tank_id is not None:
            self.update_tank()
            return
        try:
            tank_number, tank_name, product, capacity = self.get_form_values()

            if self.tank_number_is_used(tank_number):
                raise ValueError("That tank number is already in use.")

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                conn.execute("""
                    INSERT INTO tanks (
                        tank_number,
                        name,
                        product,
                        capacity,
                        current_stock
                    )
                    VALUES (?, ?, ?, ?, 0)
                """, (tank_number, tank_name, product, capacity))

            self.load_tanks()
            self.clear_form()

            messagebox.showinfo(
                "Success",
                "Tank saved successfully.",
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
                f"Could not save tank:\n{error}",
                parent=self
            )

    def update_tank(self):
        if self.tank_id is None:
            messagebox.showwarning(
                "Select Tank",
                "Select a tank from the table first.",
                parent=self
            )
            return

        if not self.authorize_change("update this tank"):
            return

        try:
            tank_number, tank_name, product, capacity = self.get_form_values()

            if self.tank_number_is_used(tank_number, self.tank_id):
                raise ValueError("That tank number is already in use.")

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT current_stock FROM tanks WHERE id=?",
                    (self.tank_id,)
                )
                result = cursor.fetchone()

                if result is None:
                    raise ValueError("The selected tank could not be found.")

                current_stock = result[0] or 0
                if capacity < current_stock:
                    raise ValueError(
                        "Capacity cannot be lower than current stock."
                    )

                cursor.execute("""
                    UPDATE tanks
                    SET tank_number=?,
                        name=?,
                        product=?,
                        capacity=?
                    WHERE id=?
                """, (
                    tank_number,
                    tank_name,
                    product,
                    capacity,
                    self.tank_id
                ))

            self.load_tanks()

            messagebox.showinfo(
                "Success",
                "Tank updated successfully.",
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
                f"Could not update tank:\n{error}",
                parent=self
            )

    def authorize_change(self, action):
        password = simpledialog.askstring(
            "Password Required",
            f"Enter an authorized user password to {action}:",
            parent=self,
            show="*"
        )
        if password is None:
            return False
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                authorized = conn.execute(
                    "SELECT 1 FROM users WHERE password=? LIMIT 1",
                    (password,)
                ).fetchone()
        except sqlite3.Error as error:
            messagebox.showerror(
                "Authorization Error",
                f"Could not verify password:\n{error}",
                parent=self
            )
            return False
        if authorized:
            return True
        messagebox.showerror(
            "Access Denied", "The password is incorrect.", parent=self
        )
        return False

    def delete_tank(self):
        if self.tank_id is None:
            messagebox.showwarning(
                "Select Tank",
                "Select a tank from the table first.",
                parent=self
            )
            return

        if not self.authorize_change("archive this tank"):
            return

        if not messagebox.askyesno(
            "Archive Tank",
            "Archive this tank? It will be hidden from active operations,\n"
            "but its dip and operating history will be retained.",
            parent=self
        ):
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT COUNT(*) FROM pumps WHERE tank_id=?",
                    (self.tank_id,)
                )
                assigned_pumps = cursor.fetchone()[0]

                if assigned_pumps:
                    messagebox.showwarning(
                        "Tank Assigned",
                        "This tank is assigned to a pump. "
                        "Unassign the pump before deleting the tank.",
                        parent=self
                    )
                    return

                cursor.execute(
                    "UPDATE tanks SET is_active=0 WHERE id=?",
                    (self.tank_id,)
                )

            self.load_tanks()
            self.clear_form()

            messagebox.showinfo(
                "Tank Archived",
                "Tank archived. Its dip history has been retained.",
                parent=self
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not archive tank:\n{error}",
                parent=self
            )

    def restore_tank(self):
        if self.tank_id is None:
            messagebox.showwarning("Select Tank", "Select a tank first.", parent=self)
            return
        if not self.authorize_change("restore this tank"):
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                conn.execute("UPDATE tanks SET is_active=1 WHERE id=?", (self.tank_id,))
            self.load_tanks()
            messagebox.showinfo("Tank Restored", "Tank is active again.", parent=self)
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not restore tank:\n{error}", parent=self)

    def select_record(self, event=None):
        selected = self.tree.selection()
        if not selected:
            return

        values = self.tree.item(selected[0], "values")

        # Database ID remains the row's internal key, but is not displayed.
        self.tank_id = int(selected[0])
        self.save_button.configure(text="Save Changes to Selected Tank")

        self.tank_number_entry.delete(0, "end")
        self.tank_number_entry.insert(
            0,
            "" if values[0] == "Not set" else values[0]
        )

        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, values[1])

        self.product_menu.set(values[2])

        self.capacity_entry.delete(0, "end")
        self.capacity_entry.insert(
            0,
            str(values[3]).replace(",", "")
        )

    def clear_form(self):
        self.tank_id = None
        self.save_button.configure(text="Save New Tank")
        self.tank_number_entry.delete(0, "end")
        self.name_entry.delete(0, "end")
        self.capacity_entry.delete(0, "end")
        self.product_menu.set("PMS")

        for item in self.tree.selection():
            self.tree.selection_remove(item)

    def open_tank_dips(self):
        if self.tank_id is None:
            messagebox.showwarning(
                "Select Tank",
                "Select a tank first.",
                parent=self
            )
            return

        self.tabs.set("Tank Dips")
        self.dip_page.tank_id = self.tank_id
        self.dip_page.load_tanks()

    def open_dip_history(self):
        self.open_tank_dips()

    def finish_tank_product(self):
        if self.tank_id is None:
            messagebox.showwarning(
                "Select Tank",
                "Select a tank before finishing its product.",
                parent=self
            )
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                tank = conn.execute("""
                    SELECT COALESCE(tank_number,''),COALESCE(product,'')
                    FROM tanks WHERE id=?
                """, (self.tank_id,)).fetchone()
                if not tank:
                    raise ValueError("The selected tank could not be found.")
                open_runs = conn.execute("""
                    SELECT r.id,p.pump_number,r.product,
                           MAX(date(ps.session_date))
                    FROM pump_product_runs r
                    JOIN pumps p ON p.id=r.pump_id
                    LEFT JOIN pump_sessions ps ON ps.run_id=r.id
                    WHERE (p.tank_id=? OR r.tank_id=?) AND r.status='OPEN'
                    GROUP BY r.id,p.pump_number,r.product
                    ORDER BY p.pump_number,r.id
                """, (self.tank_id, self.tank_id)).fetchall()
                if not open_runs:
                    raise ValueError(
                        "The selected tank has no open pump runs to finish."
                    )
                if any(
                    str(run[2]).casefold() != tank[1].casefold()
                    for run in open_runs
                ):
                    raise ValueError(
                        "This tank has open pump runs assigned to a different "
                        "product. Resolve those assignments before finishing."
                    )
                session_dates = [
                    str(run[3]) for run in open_runs if run[3] is not None
                ]
                minimum_date = max(session_dates) if session_dates else None
                pump_numbers = ", ".join(str(run[1]) for run in open_runs)

            if not messagebox.askyesno(
                "Product Finished",
                f"Finish {tank[1]} in tank {tank[0]} for all connected pumps "
                f"({pump_numbers})? One physical closing dip will be recorded, "
                "all open pump runs will close together, and the remaining "
                "litres will become the yellow tank baseline. A connected "
                "pump with no sessions will carry forward its opening meter.",
                parent=self
            ):
                return

            window = ctk.CTkToplevel(self)
            window.title("Product Finished — Tank Closing Dip")
            window.geometry("590x420")
            window.minsize(520, 380)
            window.transient(self.winfo_toplevel())
            ctk.CTkLabel(
                window,
                text=f"Closing dip for Tank {tank[0]} | Pumps {pump_numbers}",
                font=Theme.SUBHEADING_FONT,
                text_color=Theme.TEXT,
            ).pack(fill="x", padx=14, pady=(8, 0))
            dip_entry = DipWindow(
                window,
                tank_id=self.tank_id,
                fixed_tank=True,
                minimum_date=minimum_date,
                on_saved=lambda *_: self.finish_tank_product_after_dip(
                    tank_id, window
                ),
            )
            dip_entry.pack(fill="both", expand=True)
            window.protocol("WM_DELETE_WINDOW", window.destroy)
            window.grab_set()
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Product Finished", str(error), parent=self)

    def finish_tank_product_after_dip(self, tank_id, window):
        try:
            finished_runs = close_tank_product(DATABASE, tank_id)
            email_results = [
                send_product_finished_email(
                    self.winfo_toplevel(), DATABASE, run_id
                )
                for run_id in finished_runs
            ]
            email_status = "\n".join(result[1] for result in email_results)
            email_started = all(result[0] for result in email_results)
            self.load_tanks()
            window.grab_release()
            window.destroy()
            if email_started:
                messagebox.showinfo(
                    "Product Finished",
                    f"The product is finished for {len(finished_runs)} "
                    "connected pump(s). Their meter readings will carry "
                    f"forward to the next runs.\n\n{email_status}",
                    parent=self
                )
            else:
                messagebox.showwarning(
                    "Product Finished — Email Not Sent",
                    f"The product is finished for {len(finished_runs)} "
                    "connected pump(s), but one or more report emails could "
                    f"not be sent:\n\n{email_status}",
                    parent=self
                )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Product Finished", str(error), parent=self)
