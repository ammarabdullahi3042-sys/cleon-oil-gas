"""Dark report centre for the fuel station management application.

Open with: ReportWindow(master)
Exports the currently selected report to CSV, CLEON letterhead PDF, or styled Excel.
"""

import csv
import sqlite3
import threading
from datetime import date, datetime
from tkinter import Canvas, TclError, filedialog, messagebox, simpledialog, ttk

import customtkinter as ctk

from theme import Theme
from fifo_inventory import ensure_fifo_schema
from account import ensure_account_schema
from date_utils import (
    attach_date_picker, format_display_date, parse_flexible_date,
)
from report_data import (
    expense_report_rows, expense_totals, profit_adjustments,
    product_delivery_report, product_delivery_detail,
    tank_dip_variance_adjustments, tank_desktop_baselines,
    reconciled_tank_dip_profit,
)
from weekly_reports import (
    save_product_finished_email_settings,
    product_finished_email_settings,
)
from short_reconciliation import (
    adjusted_session_short_over, ensure_reconciliation_schema,
)
from number_entry import FormattedNumberEntry
from website_sync import (
    configuration_error, download_published_document,
    list_published_documents, open_public_website, publish_snapshot,
    upload_published_document,
)


from app_settings import get_active_database, verify_access

DATABASE = get_active_database()


class ReportWindow(ctk.CTkFrame):
    REPORTS = ("Summary", "Product / Delivery", "Profit & Loss", "Sales",
               "Tank Stock", "Fuel Receipts", "Attendants",
               "Expenses", "RTT")

    def __init__(self, master=None):
        super().__init__(master, fg_color=Theme.BG)
        Theme.setup()
        self.tables = {}
        self.current_report = "Summary"
        self.report_rows = []
        self.report_headers = []
        self.build_ui()
        self.refresh_reports()

    def build_ui(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(8, 3))
        ctk.CTkLabel(header, text="Reports Centre", font=Theme.TITLE_FONT,
                     text_color=Theme.TEXT).pack(side="left")
        ctk.CTkLabel(header, text="Operational, stock and reconciliation reports",
                     font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT).pack(
                         side="left", padx=14, pady=(6, 0))
        self.website_sync_status = ctk.CTkLabel(
            header, text="", font=Theme.SMALL_FONT,
            text_color=Theme.TEXT_LIGHT,
        )
        self.website_sync_status.pack(side="right", padx=8)
        Theme.secondary_button(
            header, "Open Website",
            lambda: open_public_website(self), width=120
        ).pack(side="right", padx=4)

        controls = Theme.card(self)
        controls.pack(fill="x", padx=16, pady=4)
        ctk.CTkLabel(controls, text="From", text_color=Theme.TEXT_LIGHT).pack(
            side="left", padx=(10, 4), pady=7)
        self.from_date = ctk.CTkEntry(controls, width=125,
                                      placeholder_text="DD-MM-YY")
        self.from_date.pack(side="left", padx=4, pady=6)
        self.from_date.insert(0, format_display_date(
            date.today().replace(day=1).isoformat()))
        attach_date_picker(self.from_date)
        ctk.CTkLabel(controls, text="To", text_color=Theme.TEXT_LIGHT).pack(
            side="left", padx=(8, 4), pady=7)
        self.to_date = ctk.CTkEntry(controls, width=125,
                                    placeholder_text="DD-MM-YY")
        self.to_date.pack(side="left", padx=4, pady=6)
        self.to_date.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.to_date)
        ctk.CTkLabel(controls, text="Tax %", text_color=Theme.TEXT_LIGHT).pack(
            side="left", padx=(6, 3), pady=7)
        self.tax_rate_entry = FormattedNumberEntry(
            controls, width=65, placeholder_text="0"
        )
        self.tax_rate_entry.pack(side="left", padx=3, pady=6)
        self.tax_rate_entry.insert(0, "0")
        Theme.primary_button(controls, "Refresh", self.refresh_reports,
                             width=94).pack(side="left", padx=8, pady=6)
        Theme.secondary_button(controls, "Export CSV", self.export_csv,
                               width=104).pack(side="right", padx=8, pady=6)
        Theme.primary_button(controls, "Export PDF", self.export_pdf,
                             width=104).pack(side="right", padx=3, pady=6)
        Theme.secondary_button(controls, "Export Excel", self.export_excel,
                               width=112).pack(side="right", padx=3, pady=6)

        email_settings = Theme.card(self)
        email_settings.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(
            email_settings, text="Product-finished report email",
            font=Theme.SUBHEADING_FONT, text_color=Theme.TEXT
        ).grid(row=0, column=0, padx=(10, 6), pady=(5, 1), sticky="w")
        ctk.CTkLabel(
            email_settings, text="Sender",
            text_color=Theme.TEXT_LIGHT
        ).grid(row=1, column=0, padx=(10, 3), pady=3, sticky="e")
        self.finished_sender = ctk.CTkEntry(email_settings, width=190)
        self.finished_sender.grid(row=1, column=1, padx=3, pady=3, sticky="w")
        ctk.CTkLabel(
            email_settings, text="Recipient",
            text_color=Theme.TEXT_LIGHT
        ).grid(row=1, column=2, padx=(6, 3), pady=3, sticky="e")
        self.finished_recipient = ctk.CTkEntry(email_settings, width=190)
        self.finished_recipient.grid(
            row=1, column=3, padx=3, pady=3, sticky="w")
        self.finished_enabled = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            email_settings, text="Email on Product Finished",
            variable=self.finished_enabled
        ).grid(row=1, column=4, padx=8, pady=3, sticky="w")
        Theme.primary_button(
            email_settings, "Save email settings",
            self.save_email_settings, width=144
        ).grid(row=1, column=5, padx=5, pady=3, sticky="w")
        self.email_status = ctk.CTkLabel(
            email_settings, text="", text_color=Theme.TEXT_LIGHT,
            wraplength=200, justify="left", font=Theme.SMALL_FONT
        )
        self.email_status.grid(row=0, column=1, columnspan=5,
                               padx=8, pady=(5, 1), sticky="e")
        email_settings.grid_columnconfigure(6, weight=1)
        self.load_email_settings()

        self.tabs = ctk.CTkTabview(self, fg_color=Theme.BG,
                                   segmented_button_fg_color=Theme.SIDEBAR,
                                   segmented_button_selected_color=Theme.ACCENT,
                                   segmented_button_selected_hover_color=Theme.ACCENT_HOVER,
                                   segmented_button_unselected_color=Theme.SURFACE)
        self.tabs.pack(fill="both", expand=True, padx=16, pady=(3, 8))
        for name in self.REPORTS:
            self.tabs.add(name)
            if name == "Summary":
                self._build_summary(self.tabs.tab(name))
            else:
                self.tables[name] = self._build_table(self.tabs.tab(name))
                if name == "Product / Delivery":
                    self.tables[name].bind(
                        "<Double-1>", self.open_product_detail
                    )
        self.tabs.add("Documents")
        self._build_documents(self.tabs.tab("Documents"))
        self.tabs.configure(command=self._tab_changed)
        self._apply_report_typography(self)

    def _apply_report_typography(self, parent):
        """Keep report text bold and readable while preserving its size."""
        for widget in parent.winfo_children():
            try:
                font = widget.cget("font")
                if isinstance(font, (tuple, list)) and len(font) >= 2:
                    family, size = font[0], font[1]
                    attributes = tuple(font[2:])
                elif hasattr(font, "cget"):
                    family, size = font.cget("family"), font.cget("size")
                    attributes = ()
                else:
                    family = size = None
                    attributes = ()
                attributes = tuple(
                    item for item in attributes
                    if str(item).lower() not in ("normal", "bold")
                )
                if family and size:
                    widget.configure(font=(family, size, *attributes, "bold"))
            except (AttributeError, TypeError, ValueError, TclError):
                pass
            self._apply_report_typography(widget)

        report_style = ttk.Style(self)
        report_style.configure(
            "CLEONReport.Treeview", font=("Segoe UI", 10, "bold"),
            rowheight=27, background=Theme.SURFACE,
            fieldbackground=Theme.SURFACE, foreground=Theme.TEXT,
        )
        report_style.configure(
            "CLEONReport.Treeview.Heading",
            font=("Segoe UI", 10, "bold"),
            background=Theme.CARD, foreground=Theme.TEXT_LIGHT,
        )
        report_style.map(
            "CLEONReport.Treeview",
            background=[("selected", Theme.ACCENT)],
            foreground=[("selected", Theme.TEXT)],
        )

    def _build_documents(self, parent):
        controls = Theme.card(parent)
        controls.pack(fill="x", padx=8, pady=8)
        ctk.CTkLabel(
            controls,
            text="Published documents (PDF, images, and Office files; max 10 MB)",
            font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT,
        ).pack(side="left", padx=10, pady=10)
        Theme.primary_button(
            controls, "Upload Document", self.upload_document, width=145
        ).pack(side="right", padx=6, pady=8)
        Theme.secondary_button(
            controls, "Download Selected", self.download_document, width=155
        ).pack(side="right", padx=6, pady=8)
        Theme.secondary_button(
            controls, "Refresh List", self.refresh_documents, width=115
        ).pack(side="right", padx=6, pady=8)

        wrapper = ctk.CTkFrame(parent, fg_color=Theme.SURFACE,
                               corner_radius=Theme.CARD_RADIUS)
        wrapper.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        self.documents_table = ttk.Treeview(
            wrapper, columns=("filename", "type", "uploaded"),
            show="headings", selectmode="browse",
            style="CLEONReport.Treeview",
        )
        self.documents_table.heading("filename", text="Document")
        self.documents_table.heading("type", text="File type")
        self.documents_table.heading("uploaded", text="Uploaded")
        self.documents_table.column("filename", width=460, minwidth=180)
        self.documents_table.column("type", width=220, minwidth=120)
        self.documents_table.column("uploaded", width=190, minwidth=140)
        scrollbar = ttk.Scrollbar(
            wrapper, orient="vertical", command=self.documents_table.yview
        )
        self.documents_table.configure(yscrollcommand=scrollbar.set)
        self.documents_table.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)
        self.documents_status = ctk.CTkLabel(
            parent, text="", font=Theme.SMALL_FONT,
            text_color=Theme.TEXT_LIGHT,
        )
        self.documents_status.pack(anchor="w", padx=12, pady=(0, 6))

    def _verify_document_admin(self):
        password = simpledialog.askstring(
            "Administrator Verification",
            "Enter the separate Settings administrator password:",
            parent=self, show="*",
        )
        if password is None:
            return False
        try:
            valid = verify_access("settings", password, DATABASE)
        except sqlite3.Error as error:
            messagebox.showerror(
                "Administrator Verification",
                f"Could not verify administrator access:\n{error}",
                parent=self,
            )
            return False
        if not valid:
            messagebox.showerror(
                "Access Denied", "Incorrect administrator password.",
                parent=self,
            )
            return False
        return True

    def _documents_result(self, message, success, documents=None):
        if documents is not None:
            self.documents_table.delete(*self.documents_table.get_children())
            for document in documents:
                self.documents_table.insert(
                    "", "end", iid=document["document_id"],
                    values=(
                        document["filename"],
                        document["content_type"],
                        document["uploaded_at"],
                    ),
                )
        self.documents_status.configure(
            text=message,
            text_color=Theme.SUCCESS if success else Theme.DANGER,
        )

    def _run_document_task(self, action, *args):
        self.documents_status.configure(
            text="Working with published documents…",
            text_color=Theme.TEXT_LIGHT,
        )

        def run():
            try:
                result = action(*args)
                if action is upload_published_document:
                    try:
                        documents = list_published_documents()
                    except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                        documents = None
                        message = (
                            "Upload completed, but the document list could not "
                            f"refresh: {error}. Select Refresh List to check."
                        )
                    else:
                        message = "Document uploaded and list refreshed."
                elif action is list_published_documents:
                    documents = result
                    message = f"{len(documents)} document(s) available."
                else:
                    documents = None
                    message = result
                try:
                    self.after(
                        0, self._documents_result, message, True, documents
                    )
                except (RuntimeError, TclError):
                    pass
            except (OSError, RuntimeError, ValueError, sqlite3.Error) as error:
                try:
                    self.after(
                        0, self._documents_result,
                        f"Document action failed: {error}", False,
                    )
                except (RuntimeError, TclError):
                    pass

        threading.Thread(target=run, daemon=True).start()

    def refresh_documents(self):
        self._run_document_task(list_published_documents)

    def upload_document(self):
        if not self._verify_document_admin():
            return
        file_path = filedialog.askopenfilename(
            parent=self,
            title="Choose a document to publish",
            filetypes=[
                ("Supported documents",
                 "*.pdf *.png *.jpg *.jpeg *.gif *.webp *.doc *.docx *.xls *.xlsx *.ppt *.pptx"),
                ("All files", "*.*"),
            ],
        )
        if file_path:
            self._run_document_task(upload_published_document, file_path)

    def download_document(self):
        if not self._verify_document_admin():
            return
        selected = self.documents_table.selection()
        if not selected:
            messagebox.showinfo(
                "Choose a Document", "Select a document to download.",
                parent=self,
            )
            return
        document_id = selected[0]
        filename = self.documents_table.set(document_id, "filename")
        destination = filedialog.asksaveasfilename(
            parent=self, title="Save document", initialfile=filename,
        )
        if not destination:
            return

        def download():
            data = download_published_document(document_id)
            with open(destination, "wb") as file:
                file.write(data)
            return f"Downloaded {filename}."

        self._run_document_task(download)

    def _build_summary(self, parent):
        self.summary_grid = ctk.CTkFrame(parent, fg_color="transparent")
        self.summary_grid.pack(fill="x", expand=False, padx=8, pady=(6, 3))
        self.summary_cards = {}
        self.summary_title_labels = {}
        summary_titles = (
            "Net litres sold", "Litres received",
            "Cumulative tank dip variance",
            "Dip variance estimate (not profit)",
            "Sales value", "Gross profit", "Recorded expenses",
            "Net profit", "Current stock", "RTT returned", "RTT cost",
            "Tank baseline cost (not profit)",
            "True tank variance"
        )

        for index, title in enumerate(summary_titles):
            card = Theme.card(self.summary_grid)
            card.grid(row=index // 6, column=index % 6, sticky="nsew",
                      padx=4, pady=4)
            title_label = ctk.CTkLabel(
                card, text=title, text_color=Theme.TEXT,
                font=("Segoe UI", 10, "bold"), wraplength=145,
                justify="left"
            )
            title_label.pack(anchor="w", padx=8, pady=(6, 2))
            value = ctk.CTkLabel(card, text="—", text_color=Theme.TEXT,
                                 font=("Segoe UI", 15, "bold"))
            value.pack(anchor="w", padx=8, pady=(0, 6))
            self.summary_cards[title] = value
            self.summary_title_labels[title] = title_label
        for col in range(6):
            self.summary_grid.grid_columnconfigure(col, weight=1)
        for row in range((len(summary_titles) + 5) // 6):
            self.summary_grid.grid_rowconfigure(row, weight=0)
        chart_frame = Theme.card(parent)
        chart_frame.pack(fill="both", expand=True, padx=8, pady=(3, 8))
        ctk.CTkLabel(
            chart_frame,
            text="Profit & Loss Breakdown & Tank Variance (NGN)",
            font=Theme.SUBHEADING_FONT,
            text_color=Theme.TEXT,
        ).pack(anchor="w", padx=12, pady=(6, 0))
        self.profit_chart = Canvas(chart_frame, height=210, highlightthickness=0,
                                   bg=Theme.CARD)
        self.profit_chart.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        self.profit_chart.bind(
            "<Configure>", lambda _event: self._draw_profit_chart())
        # Inventory Reference Panel
        self.inventory_reference = Theme.card(parent)
        self.inventory_reference.pack(
            fill="x",
            padx=8,
            pady=(0, 8)
        )

        ctk.CTkLabel(
            self.inventory_reference,
            text="Inventory & Variance Analysis",
            font=Theme.SUBHEADING_FONT,
            text_color=Theme.TEXT,
        ).pack(anchor="w", padx=12, pady=(8, 4))

        self.baseline_info = ctk.CTkLabel(
            self.inventory_reference,
            text="Loading...",
            justify="left",
            font=Theme.BODY_FONT,
            text_color=Theme.TEXT_LIGHT,
        )
        self.baseline_info.pack(
            anchor="w",
            padx=12,
            pady=(0, 10)
        )

    def _build_table(self, parent):
        wrapper = ctk.CTkFrame(parent, fg_color=Theme.SURFACE,
                               corner_radius=Theme.CARD_RADIUS)
        wrapper.pack(fill="both", expand=True, padx=8, pady=8)
        tree = ttk.Treeview(wrapper, show="headings")
        tree.configure(style="CLEONReport.Treeview")
        vertical = ttk.Scrollbar(
            wrapper, orient="vertical", command=tree.yview)
        horizontal = ttk.Scrollbar(
            wrapper, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vertical.set,
                       xscrollcommand=horizontal.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)
        return tree

    def _dates(self):
        try:
            start = parse_flexible_date(self.from_date.get())
            end = parse_flexible_date(self.to_date.get())
        except ValueError as error:
            raise ValueError(str(error)) from error
        if start > end:
            raise ValueError(
                "The start date must be on or before the end date.")
        return start.isoformat(), end.isoformat()

    @staticmethod
    def _columns(conn, table):
        return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}

    def _query(self, report):
        start, end = self._dates()
        if report == "Product / Delivery":
            return product_delivery_report(DATABASE, start, end)
        if report == "Expenses":
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                rows = expense_report_rows(conn, start, end)
            return ["Date", "Source", "Description", "Amount (NGN)"], rows
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            conn.row_factory = sqlite3.Row
            ensure_fifo_schema(conn)
            ensure_account_schema(conn)
            ensure_reconciliation_schema(conn)
            if report == "Sales":
                sql = """SELECT s.id AS [Session ID], s.session_date AS Date,
                    a.name AS Attendant,
                    p.pump_number AS Pump, t.tank_number AS Tank, s.product AS Product,
                    s.litres_sold AS [Net Litres Sold], s.price_per_litre AS [Selling Price/L],
                    s.cash_collected AS [Cash Collected],
                    s.pos_amount AS [POS Collected],
                    s.sale_amount AS [Sales Value], s.cost_of_goods_sold AS [Fuel Cost],
                    s.gross_profit AS [Gross Profit],
                    COALESCE(s.short_over,0) AS [Cash Short/Over]
                    FROM pump_sessions s LEFT JOIN attendants a ON a.id=s.attendant_id
                    LEFT JOIN pumps p ON p.id=s.pump_id LEFT JOIN tanks t ON t.id=p.tank_id
                    WHERE date(s.session_date) BETWEEN date(?) AND date(?)
                    ORDER BY date(s.session_date), s.id"""
            elif report == "Tank Stock":
                sql = """SELECT t.tank_number AS Tank, t.product AS Product,
                    t.capacity AS [Capacity L],
                    t.current_stock AS [Recorded Stock L],
                    t.desktop_stock AS [Baseline Litres],
                    t.desktop_cost AS [Baseline Cost (excluded from profit)]
                    FROM tanks t ORDER BY t.tank_number"""
            elif report == "Fuel Receipts":
                sql = """SELECT r.receipt_date AS Date, t.tank_number AS Tank,
                    COALESCE(r.product,t.product,'') AS [Product Type],
                    r.supplier_name AS Supplier, r.invoice_number AS [Invoice Number],
                    COALESCE(r.invoice_quantity,r.quantity_received,0) AS [Invoice L],
                    COALESCE(r.quantity_received,0) AS [Actual L],
                    r.short_over_litres AS [Short/Over L], r.cost_price AS [Cost/L],
                    COALESCE(r.invoice_quantity,r.quantity_received,0) *
                        COALESCE(r.cost_price,0) AS [Invoice Cost],
                    COALESCE(r.total_cost,0) AS [Actual Cost],
                    MAX(COALESCE(r.invoice_quantity,r.quantity_received,0)
                        -COALESCE(r.quantity_received,0),0) AS [Product Short L],
                    COALESCE(rs.reconciled_litres,0) AS [Reconciled Short L],
                    COALESCE(rs.station_borne_litres,0) AS [Station-Borne Short L],
                    MAX(COALESCE(r.invoice_quantity,r.quantity_received,0)
                        -COALESCE(r.quantity_received,0)
                        -COALESCE(rs.reconciled_litres,0)
                        -COALESCE(rs.station_borne_litres,0),0)
                        AS [Unreconciled Short L],
                    COALESCE(rs.reconciled_cost,0) AS [Reconciled Short Cost],
                    COALESCE(rs.station_borne_cost,0) AS [Station-Borne Cost],
                    COALESCE(r.total_cost,0)+COALESCE(rs.station_borne_cost,0)
                        AS [Adjusted Product Cost],
                    COALESCE(p.amount_sent,0) AS [Amount Sent],
                    MAX(COALESCE(r.total_cost,0)
                        +COALESCE(rs.station_borne_cost,0)
                        -COALESCE(p.amount_sent,0),0) AS [Balance],
                    r.vehicle_number AS Vehicle,
                    r.driver_name AS Driver, r.driver_phone AS [Driver Phone]
                    FROM fuel_receipts r LEFT JOIN tanks t ON t.id=r.tank_id
                    LEFT JOIN (
                        SELECT receipt_id,
                            SUM(reconciled_litres) AS reconciled_litres,
                            SUM(reconciled_cost) AS reconciled_cost,
                            SUM(station_borne_litres) AS station_borne_litres,
                            SUM(station_borne_cost) AS station_borne_cost
                        FROM receipt_short_reconciliations
                        GROUP BY receipt_id
                    ) rs ON rs.receipt_id=r.id
                    LEFT JOIN (
                        SELECT receipt_id,SUM(amount) AS amount_sent
                        FROM account_transactions
                        WHERE transaction_type='Product Payment'
                        GROUP BY receipt_id
                    ) p ON p.receipt_id=r.id
                    WHERE date(r.receipt_date) BETWEEN date(?) AND date(?)
                    ORDER BY date(r.receipt_date), r.id"""
            elif report == "Attendants":
                sql = """SELECT s.session_date AS Date, s.id AS Session,
                    a.name AS Attendant, s.litres_sold AS [Litres Sold],
                    s.short_over AS [Short/Over], s.sale_amount AS [Sales Value]
                    FROM pump_sessions s
                    LEFT JOIN attendants a ON a.id=s.attendant_id
                    WHERE date(s.session_date) BETWEEN date(?) AND date(?)
                    ORDER BY date(s.session_date), s.id"""
            elif report == "Expenses":
                columns = self._columns(conn, "expenses") if conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='expenses'"
                ).fetchone() else set()
                date_col = next(
                    (c for c in ("expense_date", "date", "created_at") if c in columns), None)
                amount_col = next(
                    (c for c in ("amount", "expense_amount", "cost") if c in columns), None)
                if not date_col or not amount_col:
                    return [], []
                label_col = next((c for c in (
                    "category", "description", "expense_type", "name") if c in columns), None)
                label_expr = label_col if label_col else "'Expense'"
                sql = f"SELECT {date_col} AS Date, {label_expr} AS Description, {amount_col} AS Amount FROM expenses WHERE date({date_col}) BETWEEN date(?) AND date(?) ORDER BY date({date_col})"
            elif report == "RTT":
                sql = """SELECT s.session_date AS Date, a.name AS Attendant,
                    p.pump_number AS Pump, t.tank_number AS Tank, s.product AS Product,
                    COALESCE(s.rtt_litres,0) AS "Returned Litres",
                    COALESCE(s.average_cost_per_litre,0) AS "FIFO Cost per Litre",
                    COALESCE(s.rtt_cost, COALESCE(s.rtt_litres,0) *
                    COALESCE(s.average_cost_per_litre,0)) AS "Return Value"
                    FROM pump_sessions s LEFT JOIN attendants a ON a.id=s.attendant_id
                    LEFT JOIN pumps p ON p.id=s.pump_id LEFT JOIN tanks t ON t.id=p.tank_id
                    WHERE date(s.session_date) BETWEEN date(?) AND date(?)
                    AND COALESCE(s.rtt_litres,0)>0
                    ORDER BY date(s.session_date),s.id"""
            elif report == "Profit & Loss":
                totals = conn.execute("""
                    SELECT COALESCE(SUM(gross_profit),0), COALESCE(SUM(expenses),0),
                           COALESCE(SUM(sale_amount),0), COALESCE(SUM(cost_of_goods_sold),0)
                    FROM pump_sessions
                    WHERE date(session_date) BETWEEN date(?) AND date(?)
                """, (start, end)).fetchone()
                expense_rows = expense_report_rows(conn, start, end)
                expense_groups = {}
                for _day, source, _description, amount in expense_rows:
                    expense_groups[source] = expense_groups.get(
                        source, 0.0) + amount
                session_expenses = expense_groups.get("Pump session", 0.0)
                standalone = expense_groups.get("Expense session", 0.0)
                account_expenses = expense_groups.get(
                    "Accounts cash expense", 0.0)
                all_expenses = session_expenses + standalone + account_expenses
                short_loss, delivery_loss, tank_dip_adjustment = (
                    profit_adjustments(conn, start, end)
                )
                reconciled_dip_profit = reconciled_tank_dip_profit(
                    conn, start, end
                )
                net_profit = (
                    float(totals[0] or 0) - all_expenses - short_loss
                    - delivery_loss + reconciled_dip_profit
                )
                try:
                    tax_rate = float(self.tax_rate_entry.get().strip() or 0)
                except ValueError as exc:
                    raise ValueError(
                        "Enter a valid tax percentage from 0 to 100.") from exc
                if not 0 <= tax_rate <= 100:
                    raise ValueError(
                        "Tax percentage must be between 0 and 100.")
                tax_amount = max(net_profit, 0) * tax_rate / 100
                return (["Description", "Amount (NGN)"], [
                    ("Fuel Sales Revenue", totals[2]),
                    ("Less: Cost of Fuel Sold", -float(totals[3] or 0)),
                    ("Gross Profit", totals[0]),
                    ("Session Expenses", -session_expenses),
                    ("Expense Window", -float(standalone or 0)),
                    ("Accounts Cash Expenses", -float(account_expenses or 0)),
                    ("Total Expenses", -all_expenses),
                    ("Unrecovered Attendant Shorts", -short_loss),
                    ("Station-borne Delivery Shortage", -delivery_loss),
                    ("Tank Dip Variance Estimate (excluded from profit)",
                     tank_dip_adjustment),
                    ("Reconciled Tank Dip Gain/(Loss)", reconciled_dip_profit),
                    ("Net Profit", net_profit),
                    (f"Tax Expense ({tax_rate:g}%)", -tax_amount),
                    ("Profit After Tax", net_profit - tax_amount),
                ])
            else:
                return [], []
            params = (start, end) if "?" in sql else ()
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError as exc:
                raise ValueError(
                    f"Could not load {report} report: {exc}") from exc
            headers = list(rows[0].keys()) if rows else [
                part.strip().split(" AS ")[-1].strip("[]")
                for part in sql.split("SELECT", 1)[1].split("FROM", 1)[0].split(",")
            ]
            if report == "RTT":
                headers = ["Date", "Attendant", "Pump", "Tank", "Product",
                           "Returned Litres", "FIFO Cost per Litre", "Return Value"]
            if report == "Fuel Receipts":
                headers = [
                    "Date", "Tank", "Product Type", "Supplier", "Invoice Number",
                    "Invoice L", "Actual L", "Short/Over L", "Cost/L",
                    "Invoice Cost", "Actual Cost", "Product Short L",
                    "Reconciled Short L", "Station-Borne Short L",
                    "Unreconciled Short L", "Reconciled Short Cost",
                    "Station-Borne Cost", "Adjusted Product Cost", "Amount Sent",
                    "Balance", "Vehicle", "Driver", "Driver Phone",
                ]
            if report == "Sales":
                headers = [
                    "Date", "Attendant", "Pump", "Tank", "Product",
                    "Net Litres Sold", "Selling Price/L", "Cash Collected",
                    "POS Collected", "Sales Value", "Fuel Cost",
                    "Gross Profit", "Cash Short/Over",
                ]
                return headers, [
                    tuple(row[1:-1]) + (
                        adjusted_session_short_over(
                            conn, row[0], row[-1], end
                        ),
                    )
                    for row in rows
                ]
            if report == "Attendants":
                headers = [
                    "Date", "Session", "Attendant", "Litres Sold",
                    "Short/Over", "Sales Value",
                ]
                return headers, [
                    tuple(row[:4]) + (
                        adjusted_session_short_over(
                            conn, row[1], row[4], end
                        ),
                        row[5],
                    )
                    for row in rows
                ]
            return headers, [tuple(row) for row in rows]

    def _tab_changed(self, *_):
        selected = self.tabs.get()
        if selected == "Documents":
            self.refresh_documents()
        elif selected != "Summary":
            self.load_report(selected)

    def refresh_reports(self):
        try:
            start, end = self._dates()
            self._refresh_summary()
            selected = self.tabs.get()
            if selected not in ("Summary", "Documents"):
                self.load_report(selected)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Report Error", str(error), parent=self)
            return
        self._publish_website_reports(start, end)

    def _publish_website_reports(self, start, end):
        error = configuration_error()
        if error:
            self.website_sync_status.configure(
                text=error, text_color=Theme.DANGER
            )
            return
        try:
            reports = {}
            for name in self.REPORTS:
                if name == "Summary":
                    continue
                headers, rows = self._query(name)
                reports[name] = {
                    "headers": headers,
                    "rows": [list(row) for row in rows],
                }
            summary = {
                "cards": {
                    title: label.cget("text")
                    for title, label in self.summary_cards.items()
                },
                "chart": list(self._chart_values),
            }
        except (ValueError, sqlite3.Error) as error:
            self.website_sync_status.configure(
                text=f"Could not prepare website reports: {error}",
                text_color=Theme.DANGER,
            )
            return
        self.website_sync_status.configure(text="Publishing reports…")
        publish_snapshot(
            self, "reports",
            {
                "period": {"from": start, "to": end},
                "summary": summary,
                "reports": reports,
            },
            self._website_sync_result,
        )

    def _website_sync_result(self, message, success):
        self.website_sync_status.configure(
            text=message,
            text_color=Theme.SUCCESS if success else Theme.DANGER,
        )

    def _refresh_summary(self):
        start, end = self._dates()
        with sqlite3.connect(DATABASE, timeout=10) as conn:
            ensure_fifo_schema(conn)
            row = conn.execute("""SELECT COALESCE(SUM(litres_sold),0),
                COALESCE(SUM(sale_amount),0), COALESCE(SUM(rtt_litres),0),
                COALESCE(SUM(rtt_cost),0) FROM pump_sessions
                WHERE date(session_date) BETWEEN date(?) AND date(?)""",
                               (start, end)).fetchone()
            stock = conn.execute(
                "SELECT COALESCE(SUM(current_stock),0) FROM tanks").fetchone()[0]
            tank_baselines = tank_desktop_baselines(conn)
            baseline_litres = sum(item["litres"] for item in tank_baselines.values())
            stock_is_desktop_baseline = (
                abs(float(stock or 0) - float(baseline_litres or 0)) < 0.01
            )
            saleable_stock = 0.0 if stock_is_desktop_baseline else float(stock or 0)
            baseline_cost = sum(item["cost"] for item in tank_baselines.values())
            baseline_detail = conn.execute(
                "SELECT id,COALESCE(tank_number,''),COALESCE(product,'') "
                "FROM tanks ORDER BY tank_number,id"
            ).fetchall()
            baseline_lines = "\n".join(
                f"Tank {number or tank_id} {product}: "
                f"{tank_baselines.get(tank_id, {}).get('litres', 0):,.2f} L / "
                f"₦{tank_baselines.get(tank_id, {}).get('cost', 0):,.2f}"
                for tank_id, number, product in baseline_detail
            )
            received = conn.execute("""SELECT COALESCE(SUM(quantity_received),0)
                FROM fuel_receipts WHERE date(receipt_date) BETWEEN date(?) AND date(?)""",
                                    (start, end)).fetchone()[0]
            first_dip_date = conn.execute("""
                SELECT MIN(date(dip_date)) FROM tank_dips
                WHERE date(dip_date)<=date(?)
            """, (end,)).fetchone()[0]
            cumulative_dip_adjustments = tank_dip_variance_adjustments(
                conn, first_dip_date or start, end
            )
            tank_variance_rows = conn.execute(
                "SELECT id,COALESCE(tank_number,'') FROM tanks ORDER BY tank_number,id"
            ).fetchall()
            stock_variance = sum(
                float(cumulative_dip_adjustments.get(tank_id, {}).get("litres", 0) or 0)
                for tank_id, _tank_number in tank_variance_rows
            )
            true_variance = sum(
                float(cumulative_dip_adjustments.get(tank_id, {}).get("litres", 0) or 0)
                - float(tank_baselines.get(tank_id, {}).get("litres", 0) or 0)
                for tank_id, _tank_number in tank_variance_rows
            )

            gross_profit = conn.execute("""SELECT COALESCE(SUM(gross_profit),0)
                FROM pump_sessions WHERE date(session_date) BETWEEN date(?) AND date(?)""",
                                        (start, end)).fetchone()[0]
            session_expenses = conn.execute("""SELECT COALESCE(SUM(expenses),0)
                FROM pump_sessions WHERE date(session_date) BETWEEN date(?) AND date(?)""",
                                            (start, end)).fetchone()[0]
            expenses = expense_totals(conn, start, end)
            short_loss, delivery_loss, tank_dip_adjustment = (
                profit_adjustments(conn, start, end)
            )
            reconciled_dip_profit = reconciled_tank_dip_profit(
                conn, start, end
            )
        net_profit = (
            float(gross_profit or 0) - float(expenses or 0) - short_loss
            - delivery_loss + reconciled_dip_profit
        )
        values = (f"{row[0]:,.2f} L",
                  f"{received:,.2f} L",
                  f"{float(stock_variance or 0):+,.2f} L",
                  f"₦{tank_dip_adjustment:+,.2f}",
                  f"₦{row[1]:,.2f}",
                  f"₦{gross_profit:,.2f}",
                  f"₦{float(expenses or 0):,.2f}",
                  f"₦{net_profit:,.2f}",
                  f"{saleable_stock:,.2f} L",
                  f"{row[2]:,.2f} L",
                  f"₦{row[3]:,.2f}",
                  f"₦{baseline_cost:,.2f}",
                  f"{true_variance:+,.2f} L"
                  )
        for key, value in zip(self.summary_cards, values):
            color = (
                "#FACC15" if key == "Tank baseline cost (not profit)" else

                Theme.WARNING if key in ("Recorded expenses", "RTT cost") else

                Theme.INFO if key in ("Net litres sold", "Sales value") else

                Theme.DANGER if key == "Current stock" and saleable_stock <= 0 else

                Theme.INFO if key == "Current stock" else

                "#DC2626" if key == "True tank variance"
                and true_variance < 0 else

                "#15803D" if key == "True tank variance"
                and true_variance > 0 else

                "#EF4444" if key == "Cumulative tank dip variance"
                and stock_variance < 0 else

                Theme.SUCCESS if key == "Cumulative tank dip variance"
                and stock_variance > 0 else

                "#F87171" if key == "Dip variance estimate (not profit)"
                and tank_dip_adjustment < 0 else

                "#16A34A" if key == "Dip variance estimate (not profit)"
                and tank_dip_adjustment > 0 else

                "#16A34A" if key == "Net profit" and net_profit > 0 else

                "#DC2626" if key == "Net profit" and net_profit < 0 else

                Theme.SUCCESS if key == "Gross profit" and gross_profit > 0 else

                "#F87171" if key == "Gross profit" and gross_profit < 0 else

                Theme.TEXT
            )
            self.summary_cards[key].configure(text=value, text_color=color)
            self.summary_title_labels[key].configure(
                text_color=(
                    "#FACC15"
                    if key == "Tank baseline cost (not profit)"
                    else Theme.TEXT
                )
            )
        self._chart_values = (
            float(gross_profit or 0),
            -float(expenses or 0),
            -float(short_loss or 0),
            -float(delivery_loss or 0),
            float(net_profit),
            float(tank_dip_adjustment or 0) - float(baseline_cost or 0),
        )
        self._draw_profit_chart()
        stock_note = (
            f"Desktop baseline matches recorded tank stock; "
            f"current stock available for sales: {saleable_stock:,.2f} L\n\n"
            if stock_is_desktop_baseline else
            f"Current stock: {saleable_stock:,.2f} L\n\n"
        )
        baseline_info_text = (
            f"Cumulative Variance: {stock_variance:+,.2f} L\n"
            f"Desktop baseline: {baseline_litres:,.2f} L\n"
            f"True Variance: {true_variance:+,.2f} L\n"
            f"Reconciled Dip Gain/(Loss): ₦{reconciled_dip_profit:+,.2f}\n"
            f"Baseline Cost: ₦{baseline_cost:,.2f}\n"
            f"Tank baselines:\n{baseline_lines or 'No tank baselines recorded.'}\n"
            f"Tank true variances:\n" + "\n".join(
                f"Tank {tank_number or tank_id}: "
                f"{float(cumulative_dip_adjustments.get(tank_id, {}).get('litres', 0) or 0) - float(tank_baselines.get(tank_id, {}).get('litres', 0) or 0):+,.2f} L"
                for tank_id, tank_number in tank_variance_rows
            ) + "\n"
            + stock_note
            + "Baseline inventory is excluded from "
            "profit and loss calculations."
        )
        self.baseline_info.configure(text=baseline_info_text)

        self.load_email_settings()

    def load_email_settings(self):
        sender, recipient, enabled, _status = product_finished_email_settings(
            DATABASE)
        self.finished_sender.delete(0, "end")
        self.finished_sender.insert(0, sender)
        self.finished_recipient.delete(0, "end")
        self.finished_recipient.insert(0, recipient)
        self.finished_enabled.set(enabled)
        self.email_status.configure(
            text=("Product-finished email is enabled." if enabled
                  else "Product-finished email is disabled.")
        )

    def save_email_settings(self):
        try:
            status = save_product_finished_email_settings(
                DATABASE, self.finished_sender.get(),
                self.finished_recipient.get(), self.finished_enabled.get()
            )
            self.email_status.configure(text=status)
            messagebox.showinfo(
                "Product-Finished Report Email",
                "Email settings saved. Reports send when Product Finished is selected. No test email was sent.",
                parent=self
            )
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Email Settings", str(error), parent=self)

    def _draw_profit_chart(self):
        if not hasattr(self, "profit_chart"):
            return
        canvas = self.profit_chart
        canvas.delete("all")
        width = max(canvas.winfo_width(), 300)
        height = max(canvas.winfo_height(), 1)
        values = getattr(self, "_chart_values", (0, 0, 0))
        maximum = max([abs(value) for value in values] + [1])
        baseline = height / 2 + 8
        max_bar_height = max(min((height - 56) / 2, 72), 0)
        canvas.create_line(
            20, baseline, width - 16, baseline,
            fill=Theme.BORDER, width=1,
        )
        labels = (
            "Gross\nprofit", "Expenses", "Attendant\nshorts",
            "Delivery\nshortage", "Net\nprofit",
            "Dip variance less\nbaseline cost",
        )
        colors = (
            Theme.SUCCESS, Theme.WARNING, "#F87171", "#DC2626",
            "#15803D", "#FACC15",
        )
        slot = (width - 40) / len(values)
        for index, (label, value, color) in enumerate(zip(labels, values, colors)):
            bar_height = (abs(value) / maximum) * max_bar_height
            x0 = 20 + index * slot + slot * 0.2
            x1 = 20 + (index + 1) * slot - slot * 0.2
            label_y = 14
            if value >= 0:
                y0, y1 = baseline - bar_height, baseline
            else:
                y0, y1 = baseline, baseline + bar_height
            canvas.create_rectangle(
                x0, y0, x1, y1, fill=color, outline="",
                width=0,
            )
            canvas.create_text((x0 + x1) / 2, label_y,
                               text=f"NGN {value:+,.0f}", fill=color,
                               font=("Segoe UI", 8, "bold"))
            canvas.create_text((x0 + x1) / 2, height - 18,
                               text=label, fill=Theme.TEXT_LIGHT,
                               font=("Segoe UI", 8, "bold"), justify="center")

    def load_report(self, name):
        headers, rows = self._query(name)
        tree = self.tables[name]
        tree.delete(*tree.get_children())
        tree.configure(columns=headers)
        for header in headers:
            if name == "Profit & Loss" and header.casefold() == "description":
                alignment = "w"
            elif name == "Profit & Loss" and "amount" in header.casefold():
                alignment = "e"
            else:
                alignment = "center"
            tree.heading(header, text=header, anchor=alignment)
            width = (
                480 if header.casefold() == "description"
                else max(110, min(190, len(header) * 10))
            )
            tree.column(header, width=width,
                        minwidth=85, anchor=alignment, stretch=True)
        for row in rows:
            tree.insert(
                "", "end",
                values=tuple(
                    self._format_report_value(header, value)
                    for header, value in zip(headers, row)
                )
            )
        self.current_report = name
        self.report_headers = headers
        self.report_rows = rows

    @staticmethod
    def _format_report_value(header, value):
        if value is None:
            return ""
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            normalized = header.casefold()
            is_litres = "litre" in normalized or normalized.endswith(
                (" l", " (l)", " [l]")
            )
            if not is_litres and any(token in normalized for token in (
                "price", "cost", "sales", "profit", "amount", "balance",
                "short/over", "expense", "revenue", "payment",
            )):
                return f"₦{value:,.2f}"
            return f"{value:,.2f}"
        if isinstance(value, str) and "NGN " in value:
            return value.replace("NGN ", "₦")
        return format_display_date(value)

    def _formatted_export_rows(self):
        return self._format_export_rows(self.report_headers, self.report_rows)

    def _format_export_rows(self, headers, rows):
        return [
            tuple(
                self._format_report_value(header, value)
                for header, value in zip(headers, row)
            )
            for row in rows
        ]

    @staticmethod
    def _export_stem(report_name):
        return report_name.casefold().replace(" / ", "_").replace("/", "_").replace(" ", "_")

    def open_product_detail(self, _event=None):
        selected = self.tables["Product / Delivery"].selection()
        if not selected:
            return
        values = self.tables["Product / Delivery"].item(
            selected[0], "values"
        )
        label = str(values[1])
        tank_id = None
        if " / " in label and ": " in label:
            product, remainder = label.split(" / ", 1)
            tank = remainder.split(": ", 1)[0]
            try:
                with sqlite3.connect(DATABASE, timeout=10) as conn:
                    row = conn.execute("""
                        SELECT id FROM tanks
                        WHERE product=? AND tank_number=? LIMIT 1
                    """, (product, tank)).fetchone()
                tank_id = row[0] if row else None
            except sqlite3.Error as error:
                messagebox.showerror("Product Detail", str(error), parent=self)
                return
        try:
            start, end = self._dates()
            headers, rows = product_delivery_detail(
                DATABASE, start, end, tank_id)
        except (ValueError, sqlite3.Error) as error:
            messagebox.showerror("Product Detail", str(error), parent=self)
            return
        window = ctk.CTkToplevel(self)
        window.title(f"Product / Delivery Detail — {label}")
        window.geometry("1300x650")
        window.transient(self.winfo_toplevel())
        ctk.CTkLabel(
            window, text=label, font=("Segoe UI", 16, "bold")
        ).pack(anchor="w", padx=14, pady=(12, 5))
        tree = ttk.Treeview(
            window, columns=headers, show="headings",
            style="CLEONReport.Treeview",
        )
        for header in headers:
            tree.heading(header, text=header)
            tree.column(header, width=155, minwidth=100, anchor="center")
        ybar = ttk.Scrollbar(window, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(window, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=8)
        ybar.grid(row=1, column=1, sticky="ns", pady=8)
        xbar.grid(row=2, column=0, sticky="ew", padx=(10, 0), pady=(0, 10))
        window.grid_rowconfigure(1, weight=1)
        window.grid_columnconfigure(0, weight=1)
        for row in rows:
            tree.insert(
                "", "end",
                values=tuple(format_display_date(value) for value in row)
            )

    @staticmethod
    def _format(value):
        if isinstance(value, float):
            return f"{value:,.2f}"
        return "" if value is None else format_display_date(value)

    def export_csv(self):
        name = self.tabs.get()
        if name == "Summary":
            messagebox.showinfo(
                "Choose a Report", "Select a detailed report tab before exporting.", parent=self)
            return
        try:
            self.load_report(name)
            path = filedialog.asksaveasfilename(
                parent=self, title="Export report as CSV",
                defaultextension=".csv",
                initialfile=f"{self._export_stem(name)}_report.csv",
                filetypes=[("CSV files", "*.csv")])
            if not path:
                return
            from export_utils import add_total_column
            export_headers, export_rows = add_total_column(
                name, self.report_headers, self.report_rows
            )
            with open(path, "w", newline="", encoding="utf-8-sig") as output:
                writer = csv.writer(output)
                writer.writerow(export_headers)
                writer.writerows(self._format_export_rows(
                    export_headers, export_rows
                ))
                if name == "Product / Delivery":
                    start, end = self._dates()
                    detail_headers, detail_rows = product_delivery_detail(
                        DATABASE, start, end
                    )
                    detail_headers, detail_rows = add_total_column(
                        "Delivery Detail", detail_headers, detail_rows
                    )
                    writer.writerow([])
                    writer.writerow(["Delivery Detail"])
                    writer.writerow(detail_headers)
                    writer.writerows(self._format_export_rows(
                        detail_headers, detail_rows
                    ))
            messagebox.showinfo(
                "Export Complete", "CSV report saved. Open it in Excel to print or save as PDF.", parent=self)
        except (ValueError, sqlite3.Error, OSError) as error:
            messagebox.showerror("Export Error", str(error), parent=self)

    def export_pdf(self):
        name = self.tabs.get()
        if name == "Summary":
            messagebox.showinfo(
                "Choose a Report", "Select a detailed report tab before exporting.", parent=self)
            return
        try:
            self.load_report(name)
            start, end = self._dates()
            path = filedialog.asksaveasfilename(
                parent=self, title="Export report as CLEON PDF",
                defaultextension=".pdf",
                initialfile=f"{self._export_stem(name)}_report.pdf",
                filetypes=[("PDF files", "*.pdf")])
            if not path:
                return
            if name == "Product / Delivery":
                from export_utils import export_product_delivery_pdf
                detail_headers, detail_rows = product_delivery_detail(
                    DATABASE, start, end
                )
                export_product_delivery_pdf(
                    path, self.report_headers, self.report_rows,
                    detail_headers, detail_rows, (start, end)
                )
            elif name == "Fuel Receipts":
                from export_utils import export_fuel_receipts_pdf
                export_fuel_receipts_pdf(
                    path, self.report_headers, self.report_rows, (start, end)
                )
            else:
                from export_utils import export_pdf as write_cleon_pdf
                write_cleon_pdf(path, name, self.report_headers, self.report_rows,
                                (start, end))
            messagebox.showinfo(
                "Export Complete", "CLEON letterhead PDF report saved.", parent=self)
        except (ValueError, sqlite3.Error, OSError, ImportError) as error:
            messagebox.showerror("Export Error", str(error), parent=self)

    def export_excel(self):
        name = self.tabs.get()
        if name == "Summary":
            messagebox.showinfo(
                "Choose a Report", "Select a detailed report tab before exporting.", parent=self)
            return
        try:
            self.load_report(name)
            start, end = self._dates()
            path = filedialog.asksaveasfilename(
                parent=self, title="Export report as CLEON Excel workbook",
                defaultextension=".xlsx",
                initialfile=f"{self._export_stem(name)}_report.xlsx",
                filetypes=[("Excel workbooks", "*.xlsx")])
            if not path:
                return
            from export_utils import export_excel as write_cleon_excel
            if name == "Product / Delivery":
                detail_headers, detail_rows = product_delivery_detail(
                    DATABASE, start, end
                )
                write_cleon_excel(
                    path, name, self.report_headers, self.report_rows,
                    (start, end), detail_headers, detail_rows,
                )
            else:
                write_cleon_excel(
                    path, name, self.report_headers, self.report_rows,
                    (start, end),
                )
            messagebox.showinfo(
                "Export Complete", "CLEON formatted Excel report saved.", parent=self)
        except (ValueError, sqlite3.Error, OSError, ImportError) as error:
            messagebox.showerror("Export Error", str(error), parent=self)
