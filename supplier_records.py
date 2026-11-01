"""Supplier contacts and bank details used by fuel receipt payments."""

import sqlite3


def ensure_supplier_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            contact_phone TEXT NOT NULL DEFAULT '',
            bank_name TEXT NOT NULL DEFAULT '',
            bank_account_name TEXT NOT NULL DEFAULT '',
            bank_account_number TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    receipt_table = conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='fuel_receipts'
    """).fetchone()
    if not receipt_table:
        return

    receipt_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(fuel_receipts)")
    }
    if "supplier_id" not in receipt_columns:
        conn.execute("ALTER TABLE fuel_receipts ADD COLUMN supplier_id INTEGER")

    conn.execute("""
        INSERT OR IGNORE INTO suppliers(name)
        SELECT DISTINCT TRIM(supplier_name) FROM fuel_receipts
        WHERE supplier_name IS NOT NULL AND TRIM(supplier_name)<>''
    """)
    conn.execute("""
        UPDATE fuel_receipts
        SET supplier_id=(
            SELECT id FROM suppliers
            WHERE suppliers.name=fuel_receipts.supplier_name COLLATE NOCASE
        )
        WHERE supplier_id IS NULL
          AND supplier_name IS NOT NULL AND TRIM(supplier_name)<>''
    """)


def supplier_names(conn):
    ensure_supplier_schema(conn)
    rows = conn.execute("""
        SELECT name FROM suppliers
        WHERE TRIM(name)<>''
        ORDER BY name COLLATE NOCASE
    """).fetchall()
    return [row[0] for row in rows]


def get_or_create_supplier_id(conn, name):
    name = str(name or "").strip()
    if not name:
        return None
    ensure_supplier_schema(conn)
    conn.execute("INSERT OR IGNORE INTO suppliers(name) VALUES (?)", (name,))
    row = conn.execute(
        "SELECT id FROM suppliers WHERE name=? COLLATE NOCASE", (name,)
    ).fetchone()
    if not row:
        raise sqlite3.Error("Could not associate the fuel receipt with its supplier.")
    return row[0]
