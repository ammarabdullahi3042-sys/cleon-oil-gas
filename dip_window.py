import sqlite3
from datetime import date, datetime
from tkinter import messagebox, simpledialog, ttk

import customtkinter as ctk
from fifo_inventory import baseline_cost_for_stock, ensure_fifo_schema
from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from number_entry import FormattedNumberEntry
from report_data import tank_dip_variance_events


from app_settings import get_active_database

DATABASE = get_active_database()


class DipWindow(ctk.CTkFrame):

    def __init__(self, master, tank_id=None, owner=None, fixed_tank=False,
                 on_saved=None, minimum_date=None):
        super().__init__(master, fg_color=Theme.BG)

        self.tank_id = tank_id
        self.owner = owner
        self.fixed_tank = fixed_tank
        self.on_saved = on_saved
        self.minimum_date = minimum_date
        self.tank_options = {}
        self.selected_dip_id = None
        self.edit_dip_date = None
        self._opening_auto_value = None

        self.prepare_database()
        self.build_ui()
        self.load_tanks()
        if self.fixed_tank:
            self.tank_menu.configure(state="disabled")

    def prepare_database(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS tank_dips (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tank_id INTEGER NOT NULL,
                        opening_dip REAL NOT NULL,
                        closing_dip REAL NOT NULL,
                        dip_date TEXT NOT NULL
                    )
                """)

                cursor.execute("PRAGMA table_info(tanks)")
                tank_columns = [
                    column[1] for column in cursor.fetchall()
                ]

                if "current_stock_date" not in tank_columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN current_stock_date TEXT
                    """)
                if "desktop_stock" not in tank_columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN desktop_stock REAL NOT NULL DEFAULT 0
                    """)
                if "desktop_date" not in tank_columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN desktop_date TEXT
                    """)
                if "desktop_dip_id" not in tank_columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN desktop_dip_id INTEGER
                    """)
                if "desktop_cost" not in tank_columns:
                    cursor.execute("""
                        ALTER TABLE tanks
                        ADD COLUMN desktop_cost REAL NOT NULL DEFAULT 0
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
            text=(
                "Physical Tank Closing Dip"
                if self.fixed_tank else "Tank Dip Entry and History"
            ),
            font=("Segoe UI", 22, "bold")
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            self,
            text=(
                "Enter the measured tank level. The closing dip becomes "
                "the yellow desktop baseline."
                if self.fixed_tank else
                "Enter opening and closing stock in litres."
            ),
            font=("Segoe UI", 13)
        ).pack(pady=(0, 10))

        self.tank_menu = ctk.CTkOptionMenu(
            self,
            values=["Loading tanks..."],
            command=self.on_tank_selected
        )
        self.tank_menu.pack(fill="x", padx=20, pady=7)

        self.opening_dip = FormattedNumberEntry(
            self,
            placeholder_text="Opening stock (litres)"
        )
        self.opening_dip.pack(fill="x", padx=20, pady=7)

        self.closing_dip = FormattedNumberEntry(
            self,
            placeholder_text="Closing stock (litres)"
        )
        self.closing_dip.pack(fill="x", padx=20, pady=7)

        self.dip_date_entry = ctk.CTkEntry(
            self, placeholder_text="Dip date (DD-MM-YY)"
        )
        self.dip_date_entry.pack(fill="x", padx=20, pady=7)
        self.dip_date_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.dip_date_entry)
        self.dip_date_entry.bind("<FocusOut>", self.on_dip_date_changed)
        self.dip_date_entry.bind("<Return>", self.on_dip_date_changed)
        self.received_label = ctk.CTkLabel(
            self, text="Fuel received since previous dip: 0.00 L",
            font=Theme.BODY_FONT, text_color=Theme.INFO
        )
        if not self.fixed_tank:
            self.received_label.pack(anchor="w", padx=22, pady=3)

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(pady=5 if self.fixed_tank else 7)

        if not self.fixed_tank:
            ctk.CTkButton(
                button_frame,
                text="Calculate Variance",
                command=self.calculate_variance
            ).pack(side="left", padx=5, pady=6)

        self.save_button = ctk.CTkButton(
            button_frame,
            text="Save Closing Dip" if self.fixed_tank else "Save New Dip",
            command=self.save_dip
        )
        self.save_button.pack(side="left", padx=5, pady=6)
        if not self.fixed_tank:
            ctk.CTkButton(
                button_frame,
                text="Update Selected Dip",
                command=self.update_selected_dip
            ).pack(side="left", padx=5, pady=6)
            ctk.CTkButton(
                button_frame, text="Clear", command=self.clear_form
            ).pack(side="left", padx=5, pady=6)

        self.result_label = ctk.CTkLabel(
            self,
            text="First dip is the tank baseline; no variance is reported."
        )
        if not self.fixed_tank:
            self.result_label.pack(pady=5)

        if not self.fixed_tank:
            history_header = ctk.CTkFrame(self, fg_color="transparent")
            history_header.pack(fill="x", padx=15, pady=(12, 5))
            ctk.CTkLabel(
                history_header,
                text="Dip History",
                font=("Segoe UI", 18, "bold")
            ).pack(side="left")
            ctk.CTkButton(
                history_header,
                text="Delete Selected Dip",
                fg_color="#b3261e",
                hover_color="#8c1d18",
                command=self.delete_selected_dip,
                width=170,
            ).pack(side="right")

        table_frame = ctk.CTkFrame(self)
        if not self.fixed_tank:
            table_frame.pack(
                fill="both",
                expand=True,
                padx=15,
                pady=5
            )

        columns = ("Date", "Opening", "Received", "Closing", "Variance")

        self.history_tree = ttk.Treeview(
            table_frame,
            columns=columns,
            show="headings",
            height=10
        )

        self.history_tree.heading("Date", text="Date")
        self.history_tree.heading("Opening", text="Opening Stock (L)")
        self.history_tree.heading("Received", text="Received (L)")
        self.history_tree.heading("Closing", text="Closing Stock (L)")
        self.history_tree.heading("Variance", text="Overage/(shortage) (L)")

        self.history_tree.column("Date", width=150, anchor="center")
        self.history_tree.column("Opening", width=160, anchor="center")
        self.history_tree.column("Received", width=130, anchor="center")
        self.history_tree.column("Closing", width=160, anchor="center")
        self.history_tree.column("Variance", width=150, anchor="center")

        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.history_tree.yview
        )
        self.history_tree.configure(yscrollcommand=scrollbar.set)

        self.history_tree.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(8, 0),
            pady=8
        )
        self.history_tree.bind("<<TreeviewSelect>>", self.load_selected_dip)
        scrollbar.pack(side="right", fill="y", padx=(0, 8), pady=8)

    def load_tanks(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, tank_number, name, product, capacity,
                           COALESCE(is_active,1)
                    FROM tanks
                    WHERE COALESCE(is_active,1)=1 OR id=?
                    ORDER BY id
                """, (self.tank_id or -1,))
                tanks = cursor.fetchall()

            self.tank_options.clear()

            if not tanks:
                self.tank_menu.configure(values=["No tanks found"])
                self.tank_menu.set("No tanks found")
                self.tank_id = None
                self.load_history()
                return

            choices = []

            for tank_id, tank_number, tank_name, product, capacity, is_active in tanks:
                tank_number = tank_number or f"Record {tank_id}"
                label = f"{tank_number} | {product} | {tank_name}"
                if not is_active:
                    label += " | ARCHIVED"

                self.tank_options[label] = {
                    "id": tank_id,
                    "capacity": float(capacity),
                    "active": bool(is_active)
                }
                choices.append(label)

            self.tank_menu.configure(values=choices)

            selected_label = None
            if self.tank_id is not None:
                for label, tank_data in self.tank_options.items():
                    if tank_data["id"] == self.tank_id:
                        selected_label = label
                        break

            if selected_label is None:
                selected_label = choices[0]

            self.tank_menu.set(selected_label)
            self.on_tank_selected(selected_label)

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load tanks:\n{error}",
                parent=self
            )

    def on_tank_selected(self, selected_label):
        tank_data = self.tank_options.get(selected_label)
        self.tank_id = tank_data["id"] if tank_data else None
        if self.selected_dip_id is None:
            self.opening_dip.delete(0, "end")
            self._opening_auto_value = None
        self.load_previous_dip_closing()
        self.refresh_received_label()
        self.load_history()

    def load_previous_dip_closing(self):
        if self.tank_id is None or self.selected_dip_id is not None:
            return
        try:
            dip_date = self.get_dip_date()
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT closing_dip
                    FROM tank_dips
                    WHERE tank_id=? AND date(dip_date)<=date(?)
                    ORDER BY date(dip_date) DESC,id DESC
                    LIMIT 1
                """, (self.tank_id, dip_date)).fetchone()
            if row:
                self.opening_dip.delete(0, "end")
                self._opening_auto_value = f"{float(row[0] or 0):.2f}"
                self.opening_dip.insert(0, self._opening_auto_value)
            elif (self._opening_auto_value is not None
                  and self.opening_dip.get() == self._opening_auto_value):
                self.opening_dip.delete(0, "end")
                self._opening_auto_value = None
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Opening Dip", str(error), parent=self)

    def dip_period_data(self, tank_id, dip_date, dip_id=None):
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            if dip_id is not None:
                event = next((
                    item for item in tank_dip_variance_events(
                        conn, tank_id, dip_date
                    )
                    if item["id"] == dip_id
                ), None)
                if event is None or event["variance"] is None:
                    return None, (
                        event["received"] if event else 0.0
                    ), (event["sold"] if event else 0.0)
                return (
                    (dip_id, event["date"], event["baseline_litres"]),
                    event["received"], event["sold"],
                )

            previous = conn.execute("""
                SELECT id,dip_date,COALESCE(closing_dip,0)
                FROM tank_dips
                WHERE tank_id=?
                  AND (date(dip_date)<date(?) OR
                       (date(dip_date)=date(?) AND (? IS NULL OR id<?)))
                ORDER BY date(dip_date) DESC,id DESC LIMIT 1
            """, (
                tank_id, dip_date, dip_date, dip_id, dip_id,
            )).fetchone()
            if previous:
                baseline_date = previous[1]
                baseline_litres = float(previous[2] or 0)
                date_operator = ">"
            else:
                baseline_date = dip_date
                try:
                    baseline_litres = float(self.opening_dip.get())
                except ValueError:
                    baseline_litres = 0.0
                date_operator = ">="
            sold, received = conn.execute("""
                SELECT
                    COALESCE((SELECT SUM(ps.litres_sold)
                              FROM pumps p
                              JOIN pump_sessions ps ON ps.pump_id=p.id
                              WHERE p.tank_id=?
                                AND date(ps.session_date){date_operator}date(?)
                                AND date(ps.session_date)<=date(?)),0),
                    COALESCE((SELECT SUM(fr.quantity_received)
                              FROM fuel_receipts fr
                              WHERE fr.tank_id=?
                                AND date(fr.receipt_date){date_operator}date(?)
                                AND date(fr.receipt_date)<=date(?)),0)
            """.format(date_operator=date_operator), (
                tank_id, baseline_date, dip_date,
                tank_id, baseline_date, dip_date,
            )).fetchone()
        if not previous and not (float(sold or 0) or float(received or 0)):
            return None, 0.0, 0.0
        baseline = previous or (-1, baseline_date, baseline_litres)
        return baseline, float(received or 0), float(sold or 0)

    def received_for_date(self, tank_id, dip_date, dip_id=None):
        return self.dip_period_data(tank_id, dip_date, dip_id)[1]

    def refresh_received_label(self, dip_date=None):
        if dip_date is None and hasattr(self, "dip_date_entry"):
            dip_date = self.dip_date_entry.get().strip() or date.today().isoformat()
        dip_date = dip_date or date.today().isoformat()
        received = (
            self.received_for_date(self.tank_id, dip_date, self.selected_dip_id)
            if self.tank_id else 0
        )
        if hasattr(self, "received_label"):
            self.received_label.configure(
                text=f"Fuel received since previous dip: {received:,.2f} L"
            )

    def on_dip_date_changed(self, _event=None):
        dip_date = self.dip_date_entry.get().strip()
        try:
            dip_date = parse_flexible_date(dip_date).isoformat()
            self.load_previous_dip_closing()
            self.refresh_received_label(dip_date)
        except ValueError:
            self.received_label.configure(
                text="Enter a valid dip date (DD-MM-YY)."
            )

    def get_dip_date(self):
        try:
            return parse_flexible_date(self.dip_date_entry.get()).isoformat()
        except ValueError as error:
            raise ValueError(str(error)) from error

    def get_readings(self):
        try:
            opening = float(self.opening_dip.get())
            closing = float(self.closing_dip.get())
        except ValueError:
            raise ValueError("Enter valid numeric readings in litres.")

        if opening < 0 or closing < 0:
            raise ValueError("Readings cannot be negative.")

        tank_data = self.tank_options.get(self.tank_menu.get())
        if tank_data is None:
            raise ValueError("Select a tank.")

        capacity = tank_data["capacity"]
        if not tank_data.get("active", True):
            raise ValueError("This tank is archived; dip entry is disabled. Its history is available for viewing.")
        if opening > capacity or closing > capacity:
            raise ValueError(
                f"Readings cannot exceed tank capacity "
                f"({capacity:,.2f} litres)."
            )

        return opening, closing

    def calculate_variance(self):
        try:
            opening, closing = self.get_readings()
            dip_date = self.get_dip_date()
            previous, received, sold = self.dip_period_data(
                self.tank_id, dip_date, self.selected_dip_id
            )
            if previous is None:
                result = "First dip is the tank baseline; no variance is reported."
            else:
                variance = sold - (opening + received - closing)
                result = (
                    f"Sold: {sold:,.2f} L  |  Received: {received:,.2f} L  |  "
                    f"Overage/(shortage): {variance:+,.2f} L"
                )

            self.result_label.configure(
                text=result
            )

        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )

    def save_dip(self):
        if self.selected_dip_id is not None:
            self.update_selected_dip()
            return
        try:
            opening, closing = self.get_readings()
            if self.fixed_tank and closing <= 0:
                raise ValueError(
                    "The physical closing dip must be greater than zero; "
                    "the remaining fuel becomes the tank desktop."
                )

            if self.tank_id is None:
                raise ValueError("Select a tank.")

            dip_date = self.get_dip_date()
            if (
                self.fixed_tank and self.minimum_date
                and dip_date < self.minimum_date
            ):
                raise ValueError(
                    "The closing dip date must be on or after the last "
                    f"pump session ({format_display_date(self.minimum_date)})."
                )

            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute("""
                    INSERT INTO tank_dips (
                        tank_id,
                        opening_dip,
                        closing_dip,
                        dip_date
                    )
                    VALUES (?, ?, ?, ?)
                """, (self.tank_id, opening, closing, dip_date))
                dip_id = cursor.lastrowid

                if not cursor.execute(
                    "SELECT 1 FROM tanks WHERE id=?", (self.tank_id,)
                ).fetchone():
                    raise ValueError("The selected tank was not found.")
                self._sync_tank_stock(conn, self.tank_id)

            self.clear_form()
            self.load_history()
            self.refresh_parent_tank_list()

            messagebox.showinfo(
                "Saved",
                f"Dip reading saved for {dip_date}.\n"
                f"Current stock: {closing:,.2f} litres.",
                parent=self
            )
            if self.on_saved:
                self.on_saved(self.tank_id, dip_id, dip_date, closing)

        except ValueError as error:
            messagebox.showerror(
                "Check Entry",
                str(error),
                parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not save dip reading:\n{error}",
                parent=self
            )

    def load_history(self):
        if not hasattr(self, "history_tree"):
            return

        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        if self.tank_id is None:
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, dip_date, opening_dip, closing_dip
                    FROM tank_dips
                    WHERE tank_id=?
                    ORDER BY dip_date, id
                """, (self.tank_id,))
                rows = cursor.fetchall()
                variance_events = {
                    item["id"]: item
                    for item in tank_dip_variance_events(
                        conn, self.tank_id,
                        max((str(row[1]) for row in rows), default="0001-01-01"),
                    )
                }

            for dip_id, dip_date, opening, closing in rows:
                event = variance_events.get(dip_id)
                received = event["received"] if event else 0.0
                variance = event["variance"] if event else None
                variance_label = (
                    "Desktop baseline" if event and event["desktop"]
                    else "Baseline" if variance is None
                    else f"{float(variance):+,.2f}"
                )
                self.history_tree.insert(
                    "",
                    "end",
                    iid=str(dip_id),
                    values=(
                        format_display_date(dip_date),
                        f"{opening:,.2f}",
                        f"{received:,.2f}",
                        f"{closing:,.2f}",
                        variance_label
                    )
                )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not load dip history:\n{error}",
                parent=self
            )

    def load_selected_dip(self, _event=None):
        selected = self.history_tree.selection()
        if not selected:
            return
        dip_id = int(selected[0])
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                row = conn.execute("""
                    SELECT dip_date, opening_dip, closing_dip
                    FROM tank_dips WHERE id=? AND tank_id=?
                """, (dip_id, self.tank_id)).fetchone()
            if not row:
                return
            self.selected_dip_id = dip_id
            self.save_button.configure(text="Save Changes to Selected Dip")
            self.edit_dip_date = row[0]
            self.dip_date_entry.delete(0, "end")
            self.dip_date_entry.insert(0, format_display_date(row[0]))
            self.opening_dip.delete(0, "end")
            self.opening_dip.insert(0, str(row[1]))
            self._opening_auto_value = None
            self.closing_dip.delete(0, "end")
            self.closing_dip.insert(0, str(row[2]))
            self.refresh_received_label(row[0])
            previous, received, sold = self.dip_period_data(
                self.tank_id, row[0], dip_id
            )
            if previous:
                variance = sold - (
                    float(row[1] or 0) + received - float(row[2] or 0)
                )
                result = (
                    f"Sold: {sold:,.2f} L  |  Received: {received:,.2f} L  |  "
                    f"Overage/(shortage): {variance:+,.2f} L"
                )
            else:
                result = "First dip is the tank baseline; no variance is reported."
            self.result_label.configure(text=result)
        except sqlite3.Error as error:
            messagebox.showerror("Dip History", str(error), parent=self)

    def update_selected_dip(self):
        if self.selected_dip_id is None:
            messagebox.showwarning(
                "Select Dip", "Select a dip record in the history table first.",
                parent=self
            )
            return
        password = simpledialog.askstring(
            "Password Required",
            "Enter an authorized user password to update this dip:",
            parent=self, show="*"
        )
        if password is None:
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                authorized = conn.execute(
                    "SELECT 1 FROM users WHERE password=? LIMIT 1",
                    (password,)
                ).fetchone()
        except sqlite3.Error as error:
            messagebox.showerror("Authorization Error", str(error), parent=self)
            return
        if not authorized:
            messagebox.showerror("Access Denied", "The password is incorrect.", parent=self)
            return
        try:
            opening, closing = self.get_readings()
            dip_date = self.get_dip_date()
            previous, received, sold = self.dip_period_data(
                self.tank_id, dip_date, self.selected_dip_id
            )
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.execute("""
                    UPDATE tank_dips SET opening_dip=?, closing_dip=?, dip_date=?
                    WHERE id=? AND tank_id=?
                """, (opening, closing, dip_date, self.selected_dip_id, self.tank_id))
                if cursor.rowcount != 1:
                    raise ValueError("The selected dip record no longer exists; no new dip was created.")
                self._sync_tank_stock(conn, self.tank_id)
            self.load_history()
            self.refresh_parent_tank_list()
            self.clear_form()
            messagebox.showinfo(
                "Dip Updated",
                (
                    f"Dip updated. Overages/(shortages): "
                    f"{sold - (opening + received - closing):+,.2f} L."
                    if previous else
                    "Dip updated as the tank baseline; no variance is reported."
                ), parent=self
            )
        except ValueError as error:
            messagebox.showwarning("Check Entry", str(error), parent=self)
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", str(error), parent=self)

    @staticmethod
    def _sync_tank_stock(conn, tank_id):
        latest = conn.execute("""
            SELECT closing_dip, dip_date FROM tank_dips
            WHERE tank_id=? ORDER BY date(dip_date) DESC, id DESC LIMIT 1
        """, (tank_id,)).fetchone()
        if latest:
            conn.execute("""
                UPDATE tanks SET current_stock=?, current_stock_date=? WHERE id=?
            """, (latest[0], latest[1], tank_id))
        else:
            conn.execute("""
                UPDATE tanks SET current_stock=0, current_stock_date=NULL
                WHERE id=?
            """, (tank_id,))
        desktop_id = conn.execute(
            "SELECT desktop_dip_id FROM tanks WHERE id=?", (tank_id,)
        ).fetchone()
        if desktop_id and desktop_id[0] is not None:
            desktop = conn.execute("""
                SELECT closing_dip,dip_date FROM tank_dips
                WHERE id=? AND tank_id=?
            """, (desktop_id[0], tank_id)).fetchone()
            if desktop:
                ensure_fifo_schema(conn)
                product = conn.execute(
                    "SELECT product FROM tanks WHERE id=?", (tank_id,)
                ).fetchone()[0]
                desktop_cost = baseline_cost_for_stock(
                    conn.cursor(), product, desktop[0], desktop[1]
                )
                conn.execute("""
                    UPDATE tanks
                    SET desktop_stock=?,desktop_cost=?,desktop_date=?
                    WHERE id=?
                """, (desktop[0], desktop_cost, desktop[1], tank_id))
            else:
                conn.execute("""
                    UPDATE tanks
                    SET desktop_stock=0,desktop_cost=0,
                        desktop_date=NULL,desktop_dip_id=NULL
                    WHERE id=?
                """, (tank_id,))

    def clear_form(self):
        self.selected_dip_id = None
        self.save_button.configure(text="Save New Dip")
        self.edit_dip_date = None
        self.opening_dip.delete(0, "end")
        self._opening_auto_value = None
        self.closing_dip.delete(0, "end")
        self.dip_date_entry.delete(0, "end")
        self.dip_date_entry.insert(0, format_display_date(date.today().isoformat()))
        self.result_label.configure(
            text="Add a dip to view overage/shortage against the previous dip."
        )
        self.load_previous_dip_closing()
        self.refresh_received_label()
        if hasattr(self, "history_tree"):
            for item in self.history_tree.selection():
                self.history_tree.selection_remove(item)

    def delete_selected_dip(self):
        selected = self.history_tree.selection()

        if not selected:
            messagebox.showwarning(
                "Select Dip",
                "Select a dip record from the history table first.",
                parent=self
            )
            return

        password = simpledialog.askstring(
            "Password Required",
            "Enter an authorized user password to delete this dip record:",
            parent=self,
            show="*"
        )
        if password is None:
            return
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                authorized = conn.execute(
                    "SELECT 1 FROM users WHERE password=? LIMIT 1",
                    (password,)
                ).fetchone()
        except sqlite3.Error as error:
            messagebox.showerror("Authorization Error", str(error), parent=self)
            return
        if not authorized:
            messagebox.showerror("Access Denied", "The password is incorrect.", parent=self)
            return

        dip_id = int(selected[0])

        if not messagebox.askyesno(
            "Delete Dip Record",
            "Delete the selected dip record?",
            parent=self
        ):
            return

        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                cursor = conn.cursor()

                cursor.execute(
                    "SELECT tank_id,dip_date,closing_dip FROM tank_dips WHERE id=?",
                    (dip_id,)
                )
                record = cursor.fetchone()

                if record is None:
                    messagebox.showerror(
                        "Not Found",
                        "That dip record no longer exists.",
                        parent=self
                    )
                    self.load_history()
                    return

                record_tank_id, record_date, record_closing = record

                desktop = cursor.execute("""
                    SELECT desktop_dip_id,desktop_date,desktop_stock
                    FROM tanks WHERE id=?
                """, (record_tank_id,)).fetchone()

                cursor.execute(
                    "DELETE FROM tank_dips WHERE id=?",
                    (dip_id,)
                )
                if (
                    desktop and desktop[0] is None and desktop[1] == record_date
                    and desktop[2] is not None
                    and abs(float(desktop[2]) - float(record_closing or 0)) <= 0.01
                ):
                    cursor.execute("""
                        UPDATE tanks
                        SET desktop_stock=0,desktop_date=NULL,desktop_dip_id=NULL
                        WHERE id=?
                    """, (record_tank_id,))
                self._sync_tank_stock(conn, record_tank_id)

            self.clear_form()
            self.load_history()
            self.refresh_parent_tank_list()

            messagebox.showinfo(
                "Deleted",
                "Dip record deleted. Current stock was recalculated "
                "from the latest remaining dip.",
                parent=self
            )

        except sqlite3.Error as error:
            messagebox.showerror(
                "Database Error",
                f"Could not delete dip record:\n{error}",
                parent=self
            )

    def refresh_parent_tank_list(self):
        if self.owner is not None and hasattr(self.owner, "load_tanks"):
            self.owner.load_tanks()
