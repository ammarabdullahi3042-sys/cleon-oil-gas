"""SQLite schema creation and safe, additive migrations for the station app."""

import sqlite3

from app_settings import get_active_database

DATABASE = get_active_database()


def _columns(cursor, table):
    return {row[1] for row in cursor.execute(f"PRAGMA table_info({table})")}


def _add_missing_columns(cursor, table, definitions):
    existing = _columns(cursor, table)
    for name, declaration in definitions.items():
        if name not in existing:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN {name} {declaration}"
            )


def initialize_database(database=DATABASE):
    """Create missing tables and add newer columns without deleting data."""
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'STAFF'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tanks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                tank_number TEXT,
                product TEXT NOT NULL,
                capacity REAL NOT NULL DEFAULT 0,
                current_stock REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 1
            )
        """)
        _add_missing_columns(cursor, "tanks", {
            "name": "TEXT",
            "tank_number": "TEXT",
            "product": "TEXT",
            "capacity": "REAL NOT NULL DEFAULT 0",
            "current_stock": "REAL NOT NULL DEFAULT 0",
            "current_stock_date": "TEXT",
            "desktop_stock": "REAL NOT NULL DEFAULT 0",
            "desktop_cost": "REAL NOT NULL DEFAULT 0",
            "desktop_date": "TEXT",
            "desktop_dip_id": "INTEGER",
            "is_active": "INTEGER NOT NULL DEFAULT 1",
        })
        tank_cols = _columns(cursor, "tanks")
        if "name" in tank_cols:
            cursor.execute("""
                UPDATE tanks SET tank_number=name
                WHERE (tank_number IS NULL OR tank_number='')
                  AND name IS NOT NULL
            """)
        if "tank_number" in tank_cols:
            cursor.execute("""
                UPDATE tanks SET name=tank_number
                WHERE (name IS NULL OR name='') AND tank_number IS NOT NULL
            """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pumps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pump_number TEXT UNIQUE NOT NULL,
                tank_id INTEGER,
                FOREIGN KEY (tank_id) REFERENCES tanks(id)
            )
        """)
        _add_missing_columns(cursor, "pumps", {
            "pump_number": "TEXT",
            "tank_id": "INTEGER",
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                date_joined TEXT
            )
        """)
        _add_missing_columns(cursor, "attendants", {
            "name": "TEXT",
            "phone": "TEXT",
            "date_joined": "TEXT",
            "monthly_salary": "REAL NOT NULL DEFAULT 0",
            "salary_payday_day": "INTEGER",
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pump_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pump_id INTEGER,
                attendant_id INTEGER,
                opening_meter REAL NOT NULL DEFAULT 0,
                closing_meter REAL NOT NULL DEFAULT 0,
                litres_sold REAL NOT NULL DEFAULT 0,
                price_per_litre REAL NOT NULL DEFAULT 0,
                sale_amount REAL NOT NULL DEFAULT 0,
                cash_collected REAL NOT NULL DEFAULT 0,
                pos_amount REAL NOT NULL DEFAULT 0,
                expenses REAL NOT NULL DEFAULT 0,
                rtt REAL NOT NULL DEFAULT 0,
                rtt_litres REAL NOT NULL DEFAULT 0,
                rtt_cost REAL NOT NULL DEFAULT 0,
                short_over REAL NOT NULL DEFAULT 0,
                session_date TEXT,
                product TEXT,
                cost_of_goods_sold REAL NOT NULL DEFAULT 0,
                gross_profit REAL NOT NULL DEFAULT 0,
                average_cost_per_litre REAL NOT NULL DEFAULT 0,
                run_id INTEGER,
                FOREIGN KEY (pump_id) REFERENCES pumps(id),
                FOREIGN KEY (attendant_id) REFERENCES attendants(id)
            )
        """)
        _add_missing_columns(cursor, "pump_sessions", {
            "pump_id": "INTEGER",
            "attendant_id": "INTEGER",
            "opening_meter": "REAL NOT NULL DEFAULT 0",
            "closing_meter": "REAL NOT NULL DEFAULT 0",
            "litres_sold": "REAL NOT NULL DEFAULT 0",
            "price_per_litre": "REAL NOT NULL DEFAULT 0",
            "sale_amount": "REAL NOT NULL DEFAULT 0",
            "cash_collected": "REAL NOT NULL DEFAULT 0",
            "pos_amount": "REAL NOT NULL DEFAULT 0",
            "expenses": "REAL NOT NULL DEFAULT 0",
            "rtt": "REAL NOT NULL DEFAULT 0",
            "rtt_litres": "REAL NOT NULL DEFAULT 0",
            "rtt_cost": "REAL NOT NULL DEFAULT 0",
            "short_over": "REAL NOT NULL DEFAULT 0",
            "session_date": "TEXT",
            "product": "TEXT",
            "cost_of_goods_sold": "REAL NOT NULL DEFAULT 0",
            "gross_profit": "REAL NOT NULL DEFAULT 0",
            "average_cost_per_litre": "REAL NOT NULL DEFAULT 0",
            "run_id": "INTEGER",
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pump_product_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pump_id INTEGER NOT NULL,
                tank_id INTEGER,
                product TEXT NOT NULL,
                opening_meter REAL,
                closing_meter REAL,
                status TEXT NOT NULL DEFAULT 'OPEN',
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                FOREIGN KEY (pump_id) REFERENCES pumps(id),
                FOREIGN KEY (tank_id) REFERENCES tanks(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pump_run_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                receipt_id INTEGER NOT NULL,
                quantity_received REAL NOT NULL DEFAULT 0,
                total_cost REAL NOT NULL DEFAULT 0,
                opening_meter REAL,
                UNIQUE(run_id, receipt_id),
                FOREIGN KEY (run_id) REFERENCES pump_product_runs(id),
                FOREIGN KEY (receipt_id) REFERENCES fuel_receipts(id)
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_pump_run_receipts_receipt
            ON pump_run_receipts(receipt_id, run_id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fuel_receipts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_name TEXT,
                tank_id INTEGER,
                invoice_number TEXT,
                delivery_note TEXT,
                quantity_received REAL NOT NULL DEFAULT 0,
                remaining_quantity REAL NOT NULL DEFAULT 0,
                cost_price REAL NOT NULL DEFAULT 0,
                total_cost REAL NOT NULL DEFAULT 0,
                effective_cost_price REAL,
                receipt_date TEXT,
                invoice_quantity REAL,
                product TEXT,
                short_over_litres REAL NOT NULL DEFAULT 0,
                variance_value REAL NOT NULL DEFAULT 0,
                vehicle_number TEXT,
                driver_name TEXT,
                driver_phone TEXT,
                receipt_type TEXT NOT NULL DEFAULT 'Delivery',
                FOREIGN KEY (tank_id) REFERENCES tanks(id)
            )
        """)
        _add_missing_columns(cursor, "fuel_receipts", {
            "supplier_name": "TEXT",
            "tank_id": "INTEGER",
            "invoice_number": "TEXT",
            "delivery_note": "TEXT",
            "quantity_received": "REAL NOT NULL DEFAULT 0",
            "remaining_quantity": "REAL NOT NULL DEFAULT 0",
            "cost_price": "REAL NOT NULL DEFAULT 0",
            "total_cost": "REAL NOT NULL DEFAULT 0",
            "effective_cost_price": "REAL",
            "receipt_date": "TEXT",
            "invoice_quantity": "REAL",
            "product": "TEXT",
            "short_over_litres": "REAL NOT NULL DEFAULT 0",
            "variance_value": "REAL NOT NULL DEFAULT 0",
            "vehicle_number": "TEXT",
            "driver_name": "TEXT",
            "driver_phone": "TEXT",
            "receipt_type": "TEXT NOT NULL DEFAULT 'Delivery'",
        })
        cursor.execute("""
            UPDATE fuel_receipts SET invoice_quantity=quantity_received
            WHERE invoice_quantity IS NULL
        """)
        cursor.execute("""
            UPDATE fuel_receipts SET remaining_quantity=quantity_received
            WHERE remaining_quantity IS NULL
        """)
        cursor.execute("""
            UPDATE fuel_receipts SET product=(
                SELECT product FROM tanks WHERE tanks.id=fuel_receipts.tank_id
            ) WHERE product IS NULL OR product=''
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fifo_session_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                receipt_id INTEGER NOT NULL,
                litres REAL NOT NULL,
                unit_cost REAL NOT NULL
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_fifo_receipt_product_date
            ON fuel_receipts(product, receipt_date, id)
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tank_dips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tank_id INTEGER,
                opening_dip REAL NOT NULL DEFAULT 0,
                closing_dip REAL NOT NULL DEFAULT 0,
                dip_date TEXT,
                FOREIGN KEY (tank_id) REFERENCES tanks(id)
            )
        """)
        _add_missing_columns(cursor, "tank_dips", {
            "tank_id": "INTEGER",
            "opening_dip": "REAL NOT NULL DEFAULT 0",
            "closing_dip": "REAL NOT NULL DEFAULT 0",
            "dip_date": "TEXT",
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                amount REAL NOT NULL DEFAULT 0,
                expense_date TEXT
            )
        """)
        _add_missing_columns(cursor, "expenses", {
            "description": "TEXT",
            "amount": "REAL NOT NULL DEFAULT 0",
            "expense_date": "TEXT",
        })

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS account_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                transaction_date TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                bank_name TEXT,
                reference TEXT,
                description TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_account_transactions_date_type
            ON account_transactions(transaction_date, transaction_type)
        """)

        # Kept so older screens or data remain usable. New RTT records belong
        # to pump_sessions and are measured in litres, with FIFO cost.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rtt (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                description TEXT,
                amount REAL,
                rtt_date TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendant_short_reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                attendant_id INTEGER NOT NULL,
                reduced_amount REAL NOT NULL,
                recovered_amount REAL NOT NULL DEFAULT 0,
                recovery_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (attendant_id) REFERENCES attendants(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS attendant_short_allocations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reconciliation_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                UNIQUE(reconciliation_id, session_id),
                FOREIGN KEY (reconciliation_id)
                    REFERENCES attendant_short_reconciliations(id),
                FOREIGN KEY (session_id) REFERENCES pump_sessions(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS receipt_short_reconciliations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_id INTEGER NOT NULL,
                party_type TEXT NOT NULL,
                party_name TEXT NOT NULL,
                reconciled_litres REAL NOT NULL DEFAULT 0,
                reconciled_cost REAL NOT NULL DEFAULT 0,
                station_borne_litres REAL NOT NULL DEFAULT 0,
                station_borne_cost REAL NOT NULL DEFAULT 0,
                disputed INTEGER NOT NULL DEFAULT 0,
                settlement_date TEXT NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (receipt_id) REFERENCES fuel_receipts(id)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pump_session_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                changed_by TEXT,
                reason TEXT NOT NULL,
                old_opening_meter REAL,
                new_opening_meter REAL,
                old_closing_meter REAL,
                new_closing_meter REAL
            )
        """)

        # Create the starter owner only when absent. Change this password
        # immediately in the app; production apps should hash passwords.
        cursor.execute("""
            INSERT OR IGNORE INTO users (id, username, password, role)
            VALUES (1, 'owner', '1234', 'OWNER')
        """)

        conn.commit()


if __name__ == "__main__":
    initialize_database()
    print("Database initialized and upgraded successfully.")
