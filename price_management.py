"""Simple effective-dated selling price book for fuel products."""

import sqlite3
from datetime import date, datetime
from tkinter import messagebox, ttk

import customtkinter as ctk

from theme import Theme
from date_utils import attach_date_picker, format_display_date, parse_flexible_date
from number_entry import FormattedNumberEntry


from app_settings import get_active_database

DATABASE = get_active_database()


def ensure_price_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS product_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product TEXT NOT NULL,
            price_per_litre REAL NOT NULL CHECK(price_per_litre > 0),
            effective_date TEXT NOT NULL,
            UNIQUE(product, effective_date)
        )
    """)


def current_price(product, effective_date, database=DATABASE):
    if not product:
        return None
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_price_schema(conn)
        row = conn.execute("""
            SELECT price_per_litre FROM product_prices
            WHERE UPPER(TRIM(product))=UPPER(TRIM(?))
              AND date(effective_date)<=date(?)
            ORDER BY date(effective_date) DESC, id DESC LIMIT 1
        """, (product, effective_date)).fetchone()
    return float(row[0]) if row else None


class PriceManagementWindow(ctk.CTkToplevel):
    def __init__(self, master=None):
        super().__init__(master)
        self.title("CLEON Fuel Selling Prices")
        self.geometry("760x520")
        self.configure(fg_color=Theme.BG)
        Theme.setup()
        self.build_ui()
        self.load_products()
        self.refresh_history()
        self.transient(master)
        self.grab_set()

    def build_ui(self):
        ctk.CTkLabel(
            self, text="Fuel Selling Price Management", font=Theme.TITLE_FONT,
            text_color=Theme.TEXT
        ).pack(anchor="w", padx=20, pady=(18, 5))
        ctk.CTkLabel(
            self,
            text="New sessions use the price effective on the pump product and session date.",
            font=Theme.BODY_FONT, text_color=Theme.TEXT_LIGHT
        ).pack(anchor="w", padx=22, pady=(0, 10))

        form = Theme.card(self)
        form.pack(fill="x", padx=18, pady=8)
        self.product_menu = ctk.CTkOptionMenu(form, values=["PMS", "AGO"])
        self.product_menu.grid(row=0, column=0, padx=8, pady=12, sticky="ew")
        self.price_entry = FormattedNumberEntry(
            form, placeholder_text="Selling price per litre (NGN)"
        )
        self.price_entry.grid(row=0, column=1, padx=8, pady=12, sticky="ew")
        self.date_entry = ctk.CTkEntry(
            form, placeholder_text="Effective date (DD-MM-YY)"
        )
        self.date_entry.grid(row=0, column=2, padx=8, pady=12, sticky="ew")
        self.date_entry.insert(0, format_display_date(date.today().isoformat()))
        attach_date_picker(self.date_entry)
        Theme.primary_button(form, "Save Price", self.save_price, width=140).grid(
            row=1, column=0, columnspan=3, pady=(0, 12)
        )
        for column in range(3):
            form.grid_columnconfigure(column, weight=1)

        table = ctk.CTkFrame(self, fg_color=Theme.SURFACE)
        table.pack(fill="both", expand=True, padx=18, pady=(5, 18))
        columns = ("Product", "Price / Litre", "Effective Date")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        for name, width in zip(columns, (180, 220, 180)):
            self.tree.heading(name, text=name)
            self.tree.column(name, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

    def load_products(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                products = [row[0] for row in conn.execute("""
                    SELECT DISTINCT UPPER(TRIM(product)) FROM tanks
                    WHERE product IS NOT NULL AND TRIM(product)<>''
                    ORDER BY UPPER(TRIM(product))
                """).fetchall()]
            products = products or ["PMS", "AGO"]
            self.product_menu.configure(values=products)
            self.product_menu.set(products[0])
        except sqlite3.Error as error:
            messagebox.showerror("Price Management", str(error), parent=self)

    def refresh_history(self):
        try:
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_price_schema(conn)
                rows = conn.execute("""
                    SELECT product, price_per_litre, effective_date
                    FROM product_prices
                    ORDER BY date(effective_date), product
                """).fetchall()
            self.tree.delete(*self.tree.get_children())
            for product, price, effective_date in rows:
                self.tree.insert("", "end", values=(
                    product, f"NGN {float(price):,.2f}", format_display_date(effective_date)
                ))
        except sqlite3.Error as error:
            messagebox.showerror("Price History", str(error), parent=self)

    def save_price(self):
        try:
            product = self.product_menu.get().strip().upper()
            price = float(self.price_entry.get().replace(",", "").strip())
            effective_date = parse_flexible_date(self.date_entry.get()).isoformat()
            if price <= 0:
                raise ValueError("Selling price must be greater than zero.")
            with sqlite3.connect(DATABASE, timeout=10) as conn:
                ensure_price_schema(conn)
                conn.execute("""
                    INSERT INTO product_prices(product, price_per_litre, effective_date)
                    VALUES (?, ?, ?)
                    ON CONFLICT(product, effective_date)
                    DO UPDATE SET price_per_litre=excluded.price_per_litre
                """, (product, price, effective_date))
            self.price_entry.delete(0, "end")
            self.refresh_history()
            messagebox.showinfo(
                "Price Saved",
                f"{product} price saved from {effective_date}.", parent=self
            )
        except ValueError as error:
            messagebox.showwarning(
                "Check Price", str(error) or "Enter a valid price and date.", parent=self
            )
        except sqlite3.Error as error:
            messagebox.showerror("Database Error", str(error), parent=self)
