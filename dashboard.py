"""Main dark dashboard. Run this file to start the station application."""

import sqlite3
from datetime import date
from tkinter import Canvas, messagebox, simpledialog

import customtkinter as ctk

from database import initialize_database
from tank_window import TankWindow
from pump_window import PumpWindow
from attendant_window import AttendantWindow
from session_window import SessionWindow
from fuel_receipt_window import FuelReceiptWindow
from report_window import ReportWindow
from expense_window import ExpenseWindow
from account_window import AccountWindow
from theme import Theme
from app_settings import ensure_app_settings, get_active_station_name, verify_access
from settings_window import SettingsWindow
from date_utils import (
    attach_date_picker, format_display_date, open_calendar,
    parse_flexible_date,
)
from report_data import expense_totals, tank_dip_variance_adjustments
from website_sync import (
    configuration_error, open_public_website, publish_snapshot,
)
from short_reconciliation import adjusted_short_over_total
from short_reconciliation import ensure_reconciliation_schema
from price_management import ensure_price_schema


from app_settings import get_active_database

DATABASE = get_active_database()


class Dashboard(ctk.CTk):
    def __init__(self, login_username=None):
        super().__init__()
        self.login_username = login_username
        try:
            initialize_database(DATABASE)
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_app_settings(conn)
        except (sqlite3.Error, OSError) as error:
            messagebox.showerror(
                "Database Error", f"Could not prepare the database:\n{error}", parent=self)
            self.destroy()
            return

        Theme.setup()
        self.title(
            f"CLEON OIL & GAS | {get_active_station_name()} | Station Operations")
        self.geometry("1320x790")
        self.minsize(1080, 680)
        self.configure(fg_color=Theme.BG)
        self.kpi_value_labels = {}
        self.selected_date = date.today()
        self.build_ui()
        self.pages = {"Dashboard": self.dashboard_page}
        self.active_page = "Dashboard"
        self.refresh_dashboard()
        if not configuration_error():
            self._start_website_sync_watch()

    def build_ui(self):
        self.sidebar = ctk.CTkFrame(self, width=235, fg_color=Theme.SIDEBAR,
                                    corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        ctk.CTkLabel(self.sidebar, text="CLEON\nOIL & GAS",
                     font=("Segoe UI", 22, "bold"), text_color=Theme.TEXT,
                     justify="left").pack(anchor="w", padx=22, pady=(28, 6))
        ctk.CTkLabel(self.sidebar, text="STATION OPERATIONS",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_MUTED).pack(
                         anchor="w", padx=23, pady=(0, 25))

        for label, command in (
            ("Dashboard", self.show_dashboard),
            ("Tank Management", self.open_tanks),
            ("Pump Management", self.open_pumps),
            ("Attendants", self.open_attendants),
            ("Pump Sessions", self.open_sessions),
            ("Fuel Receipts", self.open_receipts),
            ("Reports Centre", self.open_reports),
            ("Accounts & Balances", self.open_accounts),
            ("Expenses", self.open_expenses),
            ("Settings", self.open_settings),
        ):
            Theme.primary_button(self.sidebar, label, command, width=195,
                                 anchor="w").pack(padx=18, pady=5)

        self.page_host = ctk.CTkFrame(self, fg_color=Theme.BG, corner_radius=0)
        self.page_host.pack(side="right", fill="both", expand=True,
                            padx=22, pady=18)
        self.dashboard_page = ctk.CTkFrame(self.page_host, fg_color=Theme.BG,
                                           corner_radius=0)
        self.dashboard_page.pack(fill="both", expand=True)
        self.content = self.dashboard_page
        heading = ctk.CTkFrame(self.content, fg_color="transparent")
        heading.pack(fill="x", pady=(8, 14))
        ctk.CTkLabel(heading, text="Operations Overview",
                     font=Theme.TITLE_FONT, text_color=Theme.TEXT).pack(side="left")
        self.website_sync_status = ctk.CTkLabel(
            heading, text="", font=Theme.SMALL_FONT,
            text_color=Theme.TEXT_LIGHT,
        )
        self.website_sync_status.pack(side="right", padx=(8, 0))
        date_controls = ctk.CTkFrame(heading, fg_color="transparent")
        date_controls.pack(side="right", padx=(8, 4))
        ctk.CTkLabel(date_controls, text="View date",
                     font=Theme.BODY_FONT,
                     text_color=Theme.TEXT_LIGHT).pack(side="left", padx=(0, 6))
        self.date_entry = ctk.CTkEntry(date_controls, width=125)
        self.date_entry.pack(side="left", padx=4)
        self.date_entry.insert(0, format_display_date(self.selected_date.isoformat()))
        attach_date_picker(self.date_entry)
        self.date_entry.bind(
            "<Return>", lambda _event: self.view_selected_date(), add="+"
        )
        ctk.CTkButton(
            date_controls, text="Calendar", width=82,
            command=lambda: open_calendar(self.date_entry)
        ).pack(side="left", padx=4)
        Theme.secondary_button(
            date_controls, "View", self.view_selected_date, width=66
        ).pack(side="left", padx=4)
        Theme.secondary_button(heading, "Refresh", self.refresh_dashboard,
                               width=86).pack(side="right", padx=4)
        Theme.secondary_button(
            heading, "Open Website",
            lambda: open_public_website(self), width=120
        ).pack(side="right", padx=4)
        self.records_date_label = ctk.CTkLabel(
            self.content, text="", font=Theme.SMALL_FONT,
            text_color=Theme.TEXT_LIGHT
        )
        self.records_date_label.pack(anchor="w", pady=(0, 10))

        body = ctk.CTkFrame(self.content, fg_color="transparent")
        body.pack(fill="both", expand=True)
        self.cards_frame = ctk.CTkFrame(body, fg_color="transparent")
        self.cards_frame.pack(side="left", fill="both", expand=True)
        for column in range(2):
            self.cards_frame.grid_columnconfigure(column, weight=1)
        for row in range(4):
            self.cards_frame.grid_rowconfigure(row, weight=1)
        cards = (
            ("Sales", "₦0.00", Theme.SUCCESS, 0, 0, 1),
            ("Fuel Stock", "0.00 L", Theme.PMS, 0, 1, 1),
            ("Net Litres Sold", "0.00 L", Theme.ACCENT, 1, 0, 2),
            ("Cash Short / Over", "₦0.00", Theme.TEXT, 2, 0, 1),
            ("RTT", "0.00 L", Theme.INFO, 2, 1, 1),
            ("RTT Cost", "₦0.00", Theme.WARNING, 3, 0, 1),
            ("Expenses", "₦0.00", Theme.WARNING, 3, 1, 1),
        )
        for title, value, color, row, column, columnspan in cards:
            self.create_card(self.cards_frame, title, value, color).grid(
                row=row, column=column, columnspan=columnspan,
                padx=8, pady=8, sticky="nsew")

        self.side_kpis = ctk.CTkFrame(body, fg_color="transparent", width=250)
        self.side_kpis.pack(side="right", fill="y", padx=(14, 3), pady=8)
        self.side_kpis.pack_propagate(False)
        self.gain_loss_card = Theme.card(self.side_kpis)
        self.gain_loss_card.pack(fill="both", expand=True, pady=(0, 6))
        ctk.CTkLabel(self.gain_loss_card, text="STOCK VARIANCE BY TANK",
                     font=Theme.BODY_BOLD_FONT,
                     text_color=Theme.TEXT_LIGHT).pack(pady=(14, 4))
        ctk.CTkLabel(self.gain_loss_card,
                     text="Net sold − (opening dip + received − closing dip)",
                     font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
                     justify="center", wraplength=220).pack(pady=(4, 8), padx=12)
        self.tank_variance_total_label = ctk.CTkLabel(
            self.gain_loss_card, text="Daily combined variance: —",
            font=("Segoe UI", 13, "bold"), text_color=Theme.TEXT,
            anchor="center", justify="center", wraplength=220,
        )
        self.tank_variance_total_label.pack(fill="x", padx=8, pady=(0, 4))
        self.tank_variances_frame = ctk.CTkScrollableFrame(
            self.gain_loss_card, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER,
            scrollbar_button_hover_color=Theme.TEXT_MUTED,
        )
        self.tank_variances_frame.pack(
            fill="both", expand=True, padx=8, pady=(0, 8)
        )

        self.price_card = Theme.card(self.side_kpis)
        self.price_card.pack(fill="both", expand=True, pady=(6, 0))
        ctk.CTkLabel(
            self.price_card, text="CURRENT SELLING PRICE",
            font=Theme.BODY_BOLD_FONT, text_color=Theme.TEXT_LIGHT
        ).pack(pady=(12, 6))
        self.price_list = ctk.CTkScrollableFrame(
            self.price_card, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER,
            scrollbar_button_hover_color=Theme.TEXT_MUTED,
        )
        self.price_list.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def create_card(self, master, title, value, color):
        card = Theme.card(master)
        featured = title == "Net Litres Sold"
        title_label = ctk.CTkLabel(
            card, text=title,
            font=Theme.BODY_BOLD_FONT if featured else Theme.BODY_FONT,
            text_color=Theme.TEXT_LIGHT,
            height=22 if featured else 20,
        )
        title_label.pack(
            anchor="center" if featured else "w",
            padx=18, pady=(8, 0) if featured else (5, 0)
        )
        value_font_size = 30 if featured else 20
        value_label = ctk.CTkLabel(card, text=value,
                                   font=("Segoe UI", value_font_size, "bold"),
                                   height=44 if featured else 30,
                                   text_color=color)
        value_label.pack(
            anchor="center" if featured else "w",
            padx=18, pady=(0, 1) if featured else (0, 5)
        )
        self.kpi_value_labels[title] = value_label
        if featured:
            self.net_litres_comparison = ctk.CTkLabel(
                card, text="No previous sales day",
                font=Theme.SMALL_FONT, height=18,
                text_color=Theme.TEXT_LIGHT
            )
            self.net_litres_comparison.pack(
                anchor="center", padx=12, pady=(0, 4)
            )
        if title == "Sales":
            self.sales_gauge = Canvas(
                card, height=18, highlightthickness=0, bg=Theme.CARD
            )
            self.sales_gauge.pack(fill="x", padx=18, pady=(0, 5))
            self.sales_gauge.bind(
                "<Configure>", lambda _event: self._draw_sales_gauge()
            )
            details = ctk.CTkFrame(card, fg_color="transparent")
            details.pack(fill="x", padx=18, pady=(0, 12))
            self.sales_value_labels = {}
            for row_name, metrics in (
                ("first", ("cash", "pos")),
                ("second", ("rtt", "expenses", "short_over")),
                ("third", ("expected",)),
            ):
                row = ctk.CTkFrame(details, fg_color="transparent")
                row.pack(fill="x", anchor="w")
                for metric in metrics:
                    label = ctk.CTkLabel(
                        row, text="", font=Theme.SMALL_FONT,
                        text_color=Theme.TEXT_LIGHT, anchor="w",
                    )
                    label.pack(side="left", padx=(0, 12), anchor="w")
                    self.sales_value_labels[metric] = label
        if title == "Fuel Stock":
            self.stock_warning_label = ctk.CTkLabel(
                card, text="", font=Theme.SMALL_FONT,
                text_color=Theme.WARNING, justify="left", wraplength=250
            )
            self.stock_warning_label.pack(anchor="w", padx=18, pady=(0, 6))
            ctk.CTkLabel(
                card, text="Yellow segment = tank desktop (baseline)",
                font=Theme.SMALL_FONT, text_color="#FACC15", anchor="w",
            ).pack(anchor="w", padx=18, pady=(0, 4))
            self.tank_levels_frame = ctk.CTkScrollableFrame(
                card, height=105, fg_color="transparent",
                scrollbar_button_color=Theme.BORDER,
                scrollbar_button_hover_color=Theme.TEXT_MUTED,
            )
            self.tank_levels_frame.pack(
                fill="x", expand=False, padx=12, pady=(0, 8)
            )
        return card

    def get_dashboard_metrics(self, selected_date):
        selected_date = selected_date.isoformat()
        metrics = {"sales_amount": 0.0, "litres_sold": 0.0,
                   "cash_short_over": 0.0,
                   "fuel_stock": 0.0, "rtt_litres": 0.0, "rtt_cost": 0.0,
                   "expenses": 0.0, "cash_collected": 0.0,
                   "pos_collected": 0.0, "rtt_sales_value": 0.0,
                   "session_expenses": 0.0, "expected_sales": 0.0,
                   "previous_sale_date": None, "previous_sale_litres": 0.0}
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            ensure_reconciliation_schema(conn)
            latest_sales_date = conn.execute("""
                SELECT MAX(date(session_date))
                FROM pump_sessions
                WHERE date(session_date)<=date(?)
            """, (selected_date,)).fetchone()[0]
            metrics["has_sales_records"] = latest_sales_date is not None
            records_date = latest_sales_date or selected_date
            metrics["records_date"] = records_date
            ensure_price_schema(conn)
            metrics["selling_prices"] = conn.execute("""
                WITH ranked_prices AS (
                    SELECT product,price_per_litre,effective_date,
                           ROW_NUMBER() OVER (
                               PARTITION BY UPPER(TRIM(product))
                               ORDER BY date(effective_date) DESC,id DESC
                           ) AS rank
                    FROM product_prices
                    WHERE date(effective_date)<=date(?)
                )
                SELECT current.product,current.price_per_litre,
                       previous.price_per_litre
                FROM ranked_prices current
                LEFT JOIN ranked_prices previous
                  ON UPPER(TRIM(previous.product))=UPPER(TRIM(current.product))
                 AND previous.rank=2
                WHERE current.rank=1
                ORDER BY UPPER(TRIM(current.product))
            """, (selected_date,)).fetchall()
            metrics["previous_sale_date"] = conn.execute("""
                SELECT MAX(date(session_date))
                FROM pump_sessions
                WHERE date(session_date)<date(?)
            """, (records_date,)).fetchone()[0]
            if metrics["previous_sale_date"]:
                metrics["previous_sale_litres"] = conn.execute("""
                    SELECT COALESCE(SUM(litres_sold),0)
                    FROM pump_sessions
                    WHERE date(session_date)=date(?)
                """, (metrics["previous_sale_date"],)).fetchone()[0]
            metrics["expenses"] = expense_totals(
                conn, records_date, records_date
            )
            metrics["sales_amount"], metrics["litres_sold"], \
                metrics["cash_short_over"], metrics["rtt_litres"], \
                metrics["rtt_cost"], metrics["cash_collected"], \
                metrics["pos_collected"], metrics["rtt_sales_value"], \
                metrics["session_expenses"], \
                metrics["expected_sales"] = conn.execute("""
                    SELECT COALESCE(SUM(sale_amount),0),
                           COALESCE(SUM(litres_sold),0),
                           COALESCE(SUM(short_over),0),
                           COALESCE(SUM(rtt_litres),0),
                           COALESCE(SUM(rtt_cost),0),
                           COALESCE(SUM(cash_collected),0),
                           COALESCE(SUM(pos_amount),0),
                           COALESCE(SUM(rtt_litres*price_per_litre),0),
                           COALESCE(SUM(expenses),0),
                           COALESCE(SUM(sale_amount+
                               rtt_litres*price_per_litre),0)
                    FROM pump_sessions WHERE date(session_date)=date(?)
                """, (records_date,)).fetchone()
            metrics["cash_short_over"] = adjusted_short_over_total(
                conn, records_date, records_date, records_date
            )
            # The desktop remains visible in its tank gauge but is excluded
            # from available fuel stock.
            metrics["fuel_stock"] = conn.execute("""
                SELECT COALESCE(SUM(MAX(
                    COALESCE((
                        SELECT d.closing_dip FROM tank_dips AS d
                        WHERE d.tank_id=t.id AND date(d.dip_date)<=date(?)
                        ORDER BY date(d.dip_date) DESC,d.id DESC LIMIT 1
                    ),t.current_stock,0)
                    - CASE WHEN t.desktop_date IS NOT NULL
                                AND date(t.desktop_date)<=date(?)
                           THEN COALESCE(t.desktop_stock,0) ELSE 0 END,
                    0
                )),0)
                FROM tanks AS t
            """, (records_date, records_date)).fetchone()[0]
            tank_level_rows = conn.execute("""
                SELECT t.id,t.tank_number,t.product,COALESCE(t.capacity,0),
                       COALESCE((
                           SELECT d.closing_dip FROM tank_dips AS d
                           WHERE d.tank_id=t.id AND date(d.dip_date)<=date(?)
                           ORDER BY date(d.dip_date) DESC,d.id DESC LIMIT 1
                       ),t.current_stock,0)
                       ,COALESCE(t.desktop_stock,0)
                       ,COALESCE((
                           SELECT SUM(ps.litres_sold)
                           FROM pump_sessions ps
                           JOIN pumps p ON p.id=ps.pump_id
                           WHERE p.tank_id=t.id
                             AND date(ps.session_date)=date(?)
                       ),0)
                       ,COALESCE((
                           SELECT SUM(fr.quantity_received)
                           FROM fuel_receipts fr
                           WHERE fr.tank_id=t.id
                             AND date(fr.receipt_date)=date(?)
                       ),0)
                       ,(SELECT d.closing_dip FROM tank_dips AS d
                         WHERE d.tank_id=t.id AND date(d.dip_date)=date(?)
                         ORDER BY date(d.dip_date) DESC,d.id DESC LIMIT 1)
                FROM tanks AS t
                ORDER BY t.tank_number,t.id
            """, (
                records_date, records_date, records_date, records_date,
            )).fetchall()
            dip_adjustments = tank_dip_variance_adjustments(
                conn, records_date, records_date
            )
            metrics["tank_levels"] = [
                (
                    row[1], row[2], row[3], row[4], row[6], row[7],
                    None, row[8],
                    dip_adjustments.get(row[0], {}).get("litres"),
                    row[5],
                )
                for row in tank_level_rows
            ]
            metrics["low_stock_tanks"] = conn.execute("""
                SELECT t.tank_number, t.product,
                       COALESCE((SELECT d.closing_dip FROM tank_dips AS d
                                 WHERE d.tank_id=t.id AND date(d.dip_date)<=date(?)
                                 ORDER BY date(d.dip_date) DESC,d.id DESC LIMIT 1),
                                t.current_stock,0) AS dip_stock
                FROM tanks AS t
                WHERE COALESCE((SELECT d.closing_dip FROM tank_dips AS d
                                WHERE d.tank_id=t.id AND date(d.dip_date)<=date(?)
                                ORDER BY date(d.dip_date) DESC,d.id DESC LIMIT 1),
                               t.current_stock,0)<=5000
                ORDER BY dip_stock ASC,t.tank_number
            """, (records_date, records_date)).fetchall()
            metrics["tank_count"] = conn.execute(
                "SELECT COUNT(*) FROM tanks"
            ).fetchone()[0]
        for key, value in tuple(metrics.items()):
            if key not in (
                "low_stock_tanks", "records_date", "has_sales_records",
                "tank_count", "tank_levels", "previous_sale_date",
                "selling_prices",
            ):
                metrics[key] = float(value or 0)
        return metrics

    def view_selected_date(self):
        try:
            selected_date = parse_flexible_date(self.date_entry.get())
        except ValueError as error:
            messagebox.showerror("Invalid Date", str(error), parent=self)
            return
        self.selected_date = selected_date
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, format_display_date(selected_date.isoformat()))
        self.refresh_dashboard()

    def refresh_dashboard(self):
        try:
            m = self.get_dashboard_metrics(self.selected_date)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Dashboard Error", f"Could not load dashboard data:\n{error}", parent=self)
            return
        records_date = date.fromisoformat(m["records_date"])
        selected_label = self.selected_date.strftime("%A, %d %B %Y")
        records_label = records_date.strftime("%A, %d %B %Y")
        if not m["has_sales_records"]:
            status = f"No sales records found on or before {selected_label}."
        elif records_date < self.selected_date:
            status = (
                f"No sales on {selected_label}; showing the latest available "
                f"records from {records_label}."
            )
        else:
            status = f"Showing records for {records_label}."
        self.records_date_label.configure(text=status)
        values = {
            "Sales": f"₦{m['sales_amount']:,.2f}",
            "Fuel Stock": f"{m['fuel_stock']:,.2f} L",
            "Cash Short / Over": f"₦{m['cash_short_over']:,.2f}",
            "Net Litres Sold": f"{m['litres_sold']:,.2f} L",
            "RTT": f"{m['rtt_litres']:,.2f} L",
            "RTT Cost": f"₦{m['rtt_cost']:,.2f}",
            "Expenses": f"₦{m['expenses']:,.2f}",
        }
        for label, value in values.items():
            self.kpi_value_labels[label].configure(text=value)
        previous_litres = m["previous_sale_litres"]
        if not m["previous_sale_date"]:
            comparison = "No previous sales day"
            comparison_color = Theme.TEXT_LIGHT
        elif previous_litres == 0:
            comparison = "Previous sales day: 0.00 L; change n/a"
            comparison_color = Theme.TEXT_LIGHT
        else:
            change_percent = (
                (m["litres_sold"] - previous_litres) / previous_litres * 100
            )
            if change_percent > 0:
                comparison = f"▲ {change_percent:.1f}% vs previous sales day"
                comparison_color = Theme.SUCCESS
            elif change_percent < 0:
                comparison = f"▼ {abs(change_percent):.1f}% vs previous sales day"
                comparison_color = Theme.DANGER
            else:
                comparison = "No change vs previous sales day"
                comparison_color = Theme.TEXT_LIGHT
        self.net_litres_comparison.configure(
            text=comparison, text_color=comparison_color
        )
        displayed_short_over = m["cash_short_over"]
        self.draw_sales_gauge(
            m["cash_collected"], m["pos_collected"],
            m["rtt_sales_value"], m["session_expenses"],
            displayed_short_over, m["expected_sales"]
        )
        self.render_tank_levels(m.get("tank_levels", []))
        self.render_tank_variances(m.get("tank_levels", []))
        self.render_selling_prices(m.get("selling_prices", []))
        cash_color = (
            Theme.DANGER if displayed_short_over < 0 else
            Theme.SUCCESS if displayed_short_over > 0 else Theme.TEXT
        )
        self.kpi_value_labels["Cash Short / Over"].configure(
            text=f"₦{displayed_short_over:+,.2f}",
            text_color=cash_color
        )
        total_stock = float(m.get("fuel_stock", 0) or 0)
        self.kpi_value_labels["Fuel Stock"].configure(
            text_color=(
                Theme.SUCCESS if total_stock > 5000 else Theme.DANGER
            )
        )
        if hasattr(self, "stock_warning_label"):
            low = m.get("low_stock_tanks", [])
            if low:
                names = ", ".join(
                    f"{tank} {product} ({stock:,.2f} L)"
                    for tank, product, stock in low
                )
                empty_tanks = [
                    f"{tank} {product}" for tank, product, stock in low
                    if stock <= 0
                ]
                if empty_tanks:
                    warning = (
                        f"RESTOCK NOW — {', '.join(empty_tanks)} is empty. "
                        "Record a delivery in Fuel Receipts."
                    )
                else:
                    warning = (
                        f"RESTOCK ADVISED — {names} is below 5,000 L. "
                        "Plan a fuel delivery and record it in Fuel Receipts."
                    )
                self.stock_warning_label.configure(
                    text=warning,
                    text_color=Theme.DANGER
                )
            elif m.get("tank_count", 0) > 0:
                self.stock_warning_label.configure(
                    text="All tanks are above 5,000 L.",
                    text_color=Theme.SUCCESS
                )
            else:
                self.stock_warning_label.configure(
                    text="No tanks have been added.",
                    text_color=Theme.TEXT_LIGHT
                )
        self.website_sync_status.configure(text="Publishing dashboard…")
        publish_snapshot(
            self, "dashboard",
            {
                "date": self.selected_date.isoformat(),
                "metrics": m,
            },
            self._website_sync_result,
        )

    def _website_sync_result(self, message, success):
        self.website_sync_status.configure(
            text=message,
            text_color=Theme.SUCCESS if success else Theme.DANGER,
        )

    def _start_website_sync_watch(self):
        try:
            self._website_db_watch = sqlite3.connect(DATABASE, timeout=2)
            self._website_db_version = self._website_db_watch.execute(
                "PRAGMA data_version"
            ).fetchone()[0]
            self.bind("<Destroy>", self._close_website_db_watch, add="+")
            self._ensure_website_report_page()
            self.after(5000, self._poll_website_db)
        except sqlite3.Error as error:
            self.website_sync_status.configure(
                text=f"Could not start automatic website updates: {error}",
                text_color=Theme.DANGER,
            )

    def _close_website_db_watch(self, event):
        if event.widget is self:
            connection = getattr(self, "_website_db_watch", None)
            if connection is not None:
                connection.close()
                self._website_db_watch = None

    def _ensure_website_report_page(self):
        if "Reports Centre" not in self.pages:
            self.pages["Reports Centre"] = ReportWindow(self.page_host)

    def _poll_website_db(self):
        connection = getattr(self, "_website_db_watch", None)
        if connection is None or not self.winfo_exists():
            return
        try:
            version = connection.execute("PRAGMA data_version").fetchone()[0]
        except sqlite3.Error as error:
            self.website_sync_status.configure(
                text=f"Could not check for website updates: {error}",
                text_color=Theme.DANGER,
            )
        else:
            if version != self._website_db_version:
                self._website_db_version = version
                self.refresh_dashboard()
                reports = self.pages.get("Reports Centre")
                if reports is None:
                    self._ensure_website_report_page()
                else:
                    reports.refresh_reports()
        if self.winfo_exists():
            self.after(5000, self._poll_website_db)

    def render_tank_variances(self, tanks):
        for child in self.tank_variances_frame.winfo_children():
            child.destroy()
        if not tanks:
            self.tank_variance_total_label.configure(
                text="Daily combined variance: —", text_color=Theme.TEXT_LIGHT
            )
            ctk.CTkLabel(
                self.tank_variances_frame,
                text="No tanks to calculate.",
                font=Theme.SMALL_FONT, text_color=Theme.TEXT_MUTED,
            ).pack(anchor="w", padx=6, pady=4)
            return
        variances = [
            float(tank[8]) for tank in tanks if tank[8] is not None
        ]
        combined = sum(variances)
        total_color = (
            Theme.DANGER if combined < 0 else
            Theme.SUCCESS if combined > 0 else Theme.TEXT_LIGHT
        )
        self.tank_variance_total_label.configure(
            text=f"Daily combined variance: {combined:+,.2f} L",
            text_color=total_color,
        )
        for tank in tanks:
            tank_number, product = tank[0], tank[1]
            sold, closing_dip, variance = tank[4], tank[7], tank[8]
            if variance is None:
                if closing_dip is not None:
                    text = f"{tank_number} {product}: first dip is the baseline"
                else:
                    text = (
                        f"{tank_number} {product}: {float(sold or 0):,.2f} L sold"
                        " | no dip"
                    )
                color = Theme.TEXT_LIGHT
            elif variance > 0:
                text = f"{tank_number} {product}: overage +{variance:,.2f} L"
                color = Theme.SUCCESS
            elif variance < 0:
                text = f"{tank_number} {product}: shortage {variance:,.2f} L"
                color = Theme.DANGER
            else:
                text = f"{tank_number} {product}: no overage/shortage (0.00 L)"
                color = Theme.TEXT_LIGHT
            ctk.CTkLabel(
                self.tank_variances_frame, text=text,
                font=("Segoe UI", 12, "bold"), text_color=color,
                anchor="w", justify="left", wraplength=210,
            ).pack(anchor="w", fill="x", padx=5, pady=5)

    def render_tank_levels(self, tanks):
        if not hasattr(self, "tank_levels_frame"):
            return
        for child in self.tank_levels_frame.winfo_children():
            child.destroy()
        if not tanks:
            ctk.CTkLabel(
                self.tank_levels_frame, text="No tank levels to display.",
                font=Theme.SMALL_FONT, text_color=Theme.TEXT_MUTED
            ).pack(anchor="w", padx=5, pady=4)
            return
        for tank in tanks:
            tank_number, product = tank[0], tank[1]
            capacity, stock, desktop = tank[2], tank[3], tank[9]
            capacity = max(float(capacity or 0), 0.0)
            stock = max(float(stock or 0), 0.0)
            fraction = min(stock / capacity, 1.0) if capacity else 0.0
            desktop = min(max(float(desktop or 0), 0.0), stock)
            desktop_fraction = min(desktop / capacity, fraction) if capacity else 0.0
            fill_width = 103 * fraction
            if desktop > 0 and fill_width > 0:
                fill_width = max(4.0, fill_width)
            desktop_width = min(
                fill_width,
                max(4.0, 103 * desktop_fraction) if desktop > 0 else 0.0,
            )
            row = ctk.CTkFrame(self.tank_levels_frame, fg_color="transparent")
            row.pack(fill="x", padx=3, pady=3)
            name = f"{tank_number or 'Tank'} | {product or 'Product'}"
            ctk.CTkLabel(
                row, text=name, font=Theme.SMALL_FONT,
                text_color=Theme.TEXT, anchor="w"
            ).pack(anchor="w", fill="x")
            battery = Canvas(
                row, width=126, height=26, highlightthickness=0,
                bg=Theme.CARD,
            )
            battery.pack(anchor="w", pady=(3, 1))
            battery.create_rectangle(
                2, 3, 113, 23, outline=Theme.TEXT_LIGHT, width=2
            )
            battery.create_rectangle(
                114, 9, 120, 17, fill=Theme.TEXT_LIGHT,
                outline=Theme.TEXT_LIGHT,
            )
            if fraction > 0:
                if desktop_width > 0:
                    battery.create_rectangle(
                        6, 7, 6 + desktop_width, 19,
                        fill="#FACC15", outline="",
                    )
                if fill_width > desktop_width:
                    battery.create_rectangle(
                        6 + desktop_width, 7,
                        6 + fill_width, 19,
                        fill=Theme.DANGER if stock <= 5000 else Theme.SUCCESS,
                        outline="",
                    )
            ctk.CTkLabel(
                row,
                text=(
                    f"{stock:,.0f} / {capacity:,.0f} L"
                    + (f" | Desktop {desktop:,.0f} L" if desktop > 0 else "")
                ),
                font=Theme.SMALL_FONT,
                text_color=Theme.TEXT_LIGHT,
                anchor="w"
            ).pack(anchor="w", fill="x")

    def render_selling_prices(self, prices):
        if not hasattr(self, "price_list"):
            return
        for child in self.price_list.winfo_children():
            child.destroy()
        if not prices:
            ctk.CTkLabel(
                self.price_list,
                text="No selling prices recorded in Accounts.",
                font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT,
                justify="center", wraplength=205
            ).pack(fill="x", padx=4, pady=8)
            return
        for product, current_price, previous_price in prices:
            item = ctk.CTkFrame(
                self.price_list, fg_color=Theme.SURFACE,
                corner_radius=Theme.BUTTON_RADIUS
            )
            item.pack(fill="x", padx=2, pady=3)
            ctk.CTkLabel(
                item, text=str(product).upper(),
                font=Theme.SMALL_FONT, text_color=Theme.TEXT_LIGHT
            ).pack(anchor="w", padx=8, pady=(5, 0))
            ctk.CTkLabel(
                item, text=f"₦{float(current_price):,.2f} / L",
                font=Theme.BODY_BOLD_FONT, text_color=Theme.SUCCESS
            ).pack(anchor="w", padx=8, pady=(0, 1))
            if previous_price is None or float(previous_price) == 0:
                change_text = "No previous price"
                change_color = Theme.TEXT_MUTED
            else:
                change = (
                    (float(current_price) - float(previous_price))
                    / float(previous_price) * 100
                )
                if change > 0:
                    change_text = f"▲ {change:.1f}% from last price"
                    change_color = Theme.SUCCESS
                elif change < 0:
                    change_text = f"▼ {abs(change):.1f}% from last price"
                    change_color = Theme.DANGER
                else:
                    change_text = "No change from last price"
                    change_color = Theme.TEXT_MUTED
            ctk.CTkLabel(
                item, text=change_text, font=Theme.SMALL_FONT,
                text_color=change_color
            ).pack(anchor="w", padx=8, pady=(0, 5))

    def draw_sales_gauge(self, cash, pos, rtt_value, expenses, short_over,
                         expected):
        if not hasattr(self, "sales_gauge"):
            return
        short_over = float(short_over or 0)
        self._sales_gauge_values = (
            max(float(cash or 0), 0.0),
            max(float(pos or 0), 0.0),
            max(float(rtt_value or 0), 0.0),
            max(float(expenses or 0), 0.0),
            max(-short_over, 0.0),
            max(float(expected or 0), 0.0),
        )
        self._sales_short_over = short_over
        short_color = (
            Theme.DANGER if short_over < 0 else
            Theme.SUCCESS if short_over > 0 else Theme.TEXT_LIGHT
        )
        for metric, text, color in (
            ("cash", f"Cash ₦{self._sales_gauge_values[0]:,.2f}", Theme.SUCCESS),
            ("pos", f"POS ₦{self._sales_gauge_values[1]:,.2f}", Theme.INFO),
            ("rtt", f"RTT ₦{self._sales_gauge_values[2]:,.2f}", Theme.ACCENT),
            ("expenses", f"Expenses ₦{self._sales_gauge_values[3]:,.2f}", Theme.WARNING),
            ("short_over", f"Short/Over ₦{short_over:+,.2f}", short_color),
            ("expected", f"Expected ₦{self._sales_gauge_values[5]:,.2f}", Theme.TEXT_LIGHT),
        ):
            self.sales_value_labels[metric].configure(
                text=text, text_color=color
            )
        self._draw_sales_gauge()

    def _draw_sales_gauge(self):
        if not hasattr(self, "sales_gauge"):
            return
        canvas = self.sales_gauge
        canvas.delete("all")
        width = max(canvas.winfo_width(), 80)
        height = max(canvas.winfo_height(), 14)
        canvas.create_rectangle(
            1, 2, width - 2, height - 2,
            outline=Theme.BORDER, width=1
        )
        cash, pos, rtt, expenses, short, expected = getattr(
            self, "_sales_gauge_values", (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        )
        if expected <= 0:
            return
        inner_width = max(width - 6, 0)
        segments = (
            (cash, Theme.SUCCESS),
            (pos, Theme.INFO),
            (rtt, Theme.ACCENT),
            (expenses, Theme.WARNING),
            (short, Theme.DANGER),
        )
        offset = 0.0
        for amount, color in segments:
            segment_width = min(
                amount / expected, max(1.0 - offset / inner_width, 0)
            ) * inner_width
            if segment_width > 0:
                canvas.create_rectangle(
                    3 + offset, 4, 3 + offset + segment_width, height - 4,
                    fill=color, outline=""
                )
                offset += segment_width
        if offset > inner_width:
            offset = inner_width
        # An overage is positive and is marked green; a shortage is negative
        # and appears as a red segment above.
        short_over = getattr(self, "_sales_short_over", 0.0)
        if short_over > 0:
            canvas.create_rectangle(
                max(3, 3 + offset - 3), 4,
                min(width - 3, 3 + offset), height - 4,
                fill=Theme.SUCCESS, outline=""
            )

    def show_page(self, name, factory=None):
        """Raise a cached in-dashboard page, creating it the first time."""
        if name not in self.pages:
            if factory is None:
                raise ValueError(f"No page factory was provided for {name}.")
            self.pages[name] = factory(self.page_host)
        for page in self.pages.values():
            page.pack_forget()
        page = self.pages[name]
        page.pack(fill="both", expand=True)
        self.active_page = name
        if name != "Dashboard":
            for method in ("refresh_page", "load_tanks", "load_attendants",
                           "load_expenses", "refresh_reports", "refresh"):
                callback = getattr(page, method, None)
                if callable(callback):
                    callback()
                    break
        return page

    def show_dashboard(self):
        self.show_page("Dashboard")
        self.refresh_dashboard()

    def open_tanks(self): self.show_page(
        "Tank Management", lambda parent: TankWindow(parent))

    def open_pumps(self): self.show_page(
        "Pump Management", lambda parent: PumpWindow(parent))

    def open_attendants(self): self.show_page(
        "Attendants", lambda parent: AttendantWindow(parent))

    def open_sessions(self): self.show_page(
        "Pump Sessions", lambda parent: SessionWindow(parent))

    def open_receipts(self): self.show_page(
        "Fuel Receipts", lambda parent: FuelReceiptWindow(parent))

    def open_reports(self): self.show_page(
        "Reports Centre", lambda parent: ReportWindow(parent))

    def _authorized_open(self, key, title):
        password = simpledialog.askstring(
            f"{title} Password", f"Enter the separate {title.lower()} password:",
            parent=self, show="*"
        )
        if password is None:
            return False
        if not verify_access(key, password, DATABASE):
            messagebox.showerror(
                "Access Denied", f"Incorrect {title.lower()} password.", parent=self)
            return False
        return True

    def open_accounts(self):
        if self._authorized_open("accounts", "Accounts"):
            self.show_page("Accounts & Balances",
                           lambda parent: AccountWindow(parent))

    def open_expenses(self): self.show_page(
        "Expenses", lambda parent: ExpenseWindow(parent))

    def open_settings(self):
        if self._authorized_open("settings", "Settings"):
            self.settings_window = SettingsWindow(self, self)

    def refresh_all_pages(self):
        """Refresh cached screens from saved database records."""
        if "Dashboard" in self.pages:
            self.refresh_dashboard()
        refreshers = {
            "Tank Management": ("load_tanks",),
            "Pump Management": ("load_pumps",),
            "Attendants": ("load_attendants",),
            "Pump Sessions": ("load_pumps", "load_attendants"),
            "Fuel Receipts": ("load_tanks", "load_receipts"),
            "Reports Centre": ("refresh_reports",),
            "Accounts & Balances": ("refresh",),
            "Expenses": ("load_expenses",),
        }
        for page_name, method_names in refreshers.items():
            page = self.pages.get(page_name)
            if page is None:
                continue
            for method_name in method_names:
                callback = getattr(page, method_name, None)
                if callable(callback):
                    callback()
        if not configuration_error():
            self._ensure_website_report_page()


if __name__ == "__main__":
    app = Dashboard()
    app.mainloop()
