"""Selectable session history panel for editing pump sessions."""

import sqlite3
from tkinter import messagebox, ttk

import customtkinter as ctk

from theme import Theme
from date_utils import format_display_date
from short_reconciliation import adjusted_session_short_over
from short_reconciliation import ensure_reconciliation_schema


from app_settings import get_active_database

DATABASE = get_active_database()


class SessionHistoryWindow(ctk.CTkFrame):
    def __init__(self, master, session_window=None):
        super().__init__(master, fg_color=Theme.BG)
        self.session_window = session_window
        heading = ctk.CTkFrame(self, fg_color="transparent")
        heading.pack(fill="x", padx=8, pady=(6, 4))
        ctk.CTkLabel(
            heading, text="Pump Session History", font=Theme.SUBHEADING_FONT,
            text_color=Theme.TEXT
        ).pack(side="left")
        Theme.secondary_button(
            heading, "Refresh", self.load_sessions, width=82, height=30
        ).pack(side="right", padx=(4, 0))
        Theme.primary_button(
            heading, "Load Selected Session", self.load_selected,
            width=155, height=30
        ).pack(side="right", padx=4)
        table = ctk.CTkFrame(self, fg_color=Theme.SURFACE,
                             corner_radius=Theme.CARD_RADIUS)
        table.pack(fill="both", expand=True, padx=4, pady=4)
        columns = ("Date", "Pump", "Attendant", "Product", "Net Litres",
                   "RTT Litres", "Sales", "Outstanding Short / Over")
        self.tree = ttk.Treeview(
            table, columns=columns, show="headings", height=18
        )
        widths = (76, 48, 92, 58, 72, 58, 88, 104)
        for column, width in zip(columns, widths):
            self.tree.heading(column, text=column)
            self.tree.column(column, width=width, minwidth=48, anchor="center")
        ybar = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        xbar = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=(8, 0))
        ybar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=(8, 0))
        xbar.grid(row=1, column=0, sticky="ew", padx=(8, 0), pady=(0, 8))
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda _event: self.load_selected())
        self.load_sessions()

    def load_sessions(self):
        self.tree.delete(*self.tree.get_children())
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_reconciliation_schema(conn)
                rows = conn.execute("""
                    SELECT ps.id, ps.session_date, COALESCE(p.pump_number,''),
                           COALESCE(a.name,''), COALESCE(ps.product,''),
                           COALESCE(ps.litres_sold,0), COALESCE(ps.rtt_litres,0),
                           COALESCE(ps.sale_amount,0), COALESCE(ps.short_over,0)
                    FROM pump_sessions ps
                    LEFT JOIN pumps p ON p.id=ps.pump_id
                    LEFT JOIN attendants a ON a.id=ps.attendant_id
                    ORDER BY date(ps.session_date), ps.id
                """).fetchall()
                for row in rows:
                    (session_id, session_date, pump, attendant, product,
                     net_l, rtt_l, sales, variance) = row
                    outstanding = adjusted_session_short_over(
                        conn, session_id, variance
                    )
                    self.tree.insert("", "end", iid=str(session_id), values=(
                        format_display_date(session_date), pump, attendant, product,
                        f"{float(net_l or 0):,.2f}",
                        f"{float(rtt_l or 0):,.2f}",
                        f"₦{float(sales or 0):,.2f}",
                        f"₦{outstanding:+,.2f}"
                    ))
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", f"Could not load sessions:\n{error}", parent=self)

    def load_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Select Session", "Select a session record first.", parent=self)
            return
        if self.session_window is None:
            messagebox.showerror("Session Form Missing", "The pump session page is not available.", parent=self)
            return
        self.session_window.load_session_record(int(selected[0]))
