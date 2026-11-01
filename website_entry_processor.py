"""Validate and import assigned website entries into the station SQLite ledger."""

import math
import sqlite3
from datetime import date

from account import ensure_account_schema, record_transfer
from app_settings import get_active_database
from fifo_inventory import (
    ensure_fifo_schema, product_for_pump, rebuild_fifo_product,
)
from price_management import current_price
from pump_runs import (
    ensure_pump_run_schema, link_receipt_to_product_runs,
    opening_meter_for_run, record_run_session,
)
from supplier_records import ensure_supplier_schema, get_or_create_supplier_id


DATABASE = get_active_database()


def _ensure_import_log(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS website_entry_imports (
            entry_id TEXT PRIMARY KEY,
            imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _number(payload, name, default=None):
    value = payload.get(name, default)
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Enter a valid {name.replace('_', ' ')}.") from error
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name.replace('_', ' ').title()} must be a finite non-negative number.")
    return number


def _date(payload, name):
    value = str(payload.get(name, "")).strip()
    try:
        date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"Enter a valid {name.replace('_', ' ')}.") from error
    return value


def _tank(conn, label):
    row = conn.execute("""
        SELECT id,tank_number,product,COALESCE(capacity,0),COALESCE(current_stock,0),
               COALESCE(is_active,1)
        FROM tanks WHERE lower(trim(tank_number))=lower(trim(?)) LIMIT 1
    """, (str(label),)).fetchone()
    if not row:
        raise ValueError(f"Tank '{label}' does not exist in the station app.")
    if not row[5]:
        raise ValueError(f"Tank '{row[1]}' is archived and cannot receive entries.")
    return row


def _import_pump_session(conn, payload):
    ensure_fifo_schema(conn)
    ensure_pump_run_schema(conn)
    pump = conn.execute("SELECT id FROM pumps WHERE lower(trim(pump_number))=lower(trim(?))", (payload.get("pump_number", ""),)).fetchone()
    if not pump:
        raise ValueError("The selected pump was not found in the station app.")
    pump_id = pump[0]
    attendant = conn.execute("SELECT id FROM attendants WHERE lower(trim(name))=lower(trim(?))", (payload.get("attendant_name", ""),)).fetchone()
    if not attendant:
        raise ValueError("The selected attendant was not found in the station app.")
    run = conn.execute("""
        SELECT id,product FROM pump_product_runs
        WHERE pump_id=? AND status='OPEN' ORDER BY id DESC LIMIT 1
    """, (pump_id,)).fetchone()
    if not run:
        raise ValueError("This pump has no open product run linked to a fuel receipt.")
    run_id, product = run
    assigned_product = product_for_pump(conn.cursor(), pump_id)
    if not assigned_product or assigned_product.casefold() != str(product).casefold():
        raise ValueError("The pump's open product run does not match its assigned tank.")
    session_date = _date(payload, "session_date")
    opening = _number(payload, "opening_meter")
    closing = _number(payload, "closing_meter")
    rtt = _number(payload, "rtt_litres", 0)
    cash = _number(payload, "cash_collected", 0)
    pos = _number(payload, "pos_amount", 0)
    expenses = _number(payload, "expenses", 0)
    if closing < opening:
        raise ValueError("Closing meter cannot be below opening meter.")
    movement = closing - opening
    if rtt > movement:
        raise ValueError("RTT litres cannot exceed pump meter movement.")
    expected_opening = opening_meter_for_run(conn, pump_id, run_id)
    if expected_opening is not None and abs(opening - expected_opening) > .005:
        raise ValueError(f"Opening meter must continue from {expected_opening:,.2f} L.")
    price = current_price(product, session_date, DATABASE)
    if price is None:
        raise ValueError(f"No {product} selling price is set for {session_date}.")
    sold = movement - rtt
    sale = sold * price
    short_over = cash + pos - (sale - expenses)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pump_sessions (
            pump_id,attendant_id,opening_meter,closing_meter,litres_sold,
            price_per_litre,sale_amount,cash_collected,pos_amount,expenses,rtt,
            short_over,session_date,product,cost_of_goods_sold,gross_profit,
            average_cost_per_litre,rtt_litres,run_id
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,0,0,?,?)
    """, (pump_id, attendant[0], opening, closing, sold, price, sale, cash,
          pos, expenses, rtt, short_over, session_date, product, rtt, run_id))
    session_id = cur.lastrowid
    record_run_session(cur, pump_id, run_id, session_id, opening, closing)
    rebuild_fifo_product(cur, product)


def _pump_openings(payload, conn, tank_id):
    raw = str(payload.get("pump_openings", "") or "")
    readings = {}
    for item in raw.split(","):
        if not item.strip():
            continue
        pump_name, separator, value = item.partition("=")
        if not separator:
            raise ValueError("Enter pump opening meters as Pump number=reading, separated by commas.")
        pump = conn.execute("SELECT id FROM pumps WHERE tank_id=? AND lower(trim(pump_number))=lower(trim(?))", (tank_id, pump_name.strip())).fetchone()
        if not pump:
            raise ValueError(f"Pump '{pump_name.strip()}' is not connected to this tank.")
        try:
            reading = float(value.strip())
        except ValueError as error:
            raise ValueError(f"Enter a valid opening meter for {pump_name.strip()}.") from error
        if not math.isfinite(reading) or reading < 0:
            raise ValueError(f"Opening meter for {pump_name.strip()} must be a finite non-negative number.")
        readings[pump[0]] = reading
    return readings


def _import_fuel_receipt(conn, payload):
    ensure_fifo_schema(conn)
    ensure_pump_run_schema(conn)
    ensure_supplier_schema(conn)
    tank = _tank(conn, payload.get("tank", ""))
    tank_id, _name, product, capacity, stock, _active = tank
    selected_product = str(payload.get("product", "")).strip().upper()
    if selected_product != str(product).strip().upper():
        raise ValueError(f"Tank {tank[1]} is assigned to {product}; receipt product must match.")
    invoice_qty = _number(payload, "invoice_quantity")
    actual_qty = _number(payload, "actual_quantity")
    unit_cost = _number(payload, "cost_per_litre")
    if min(invoice_qty, actual_qty, unit_cost) <= 0:
        raise ValueError("Receipt quantities and cost must be greater than zero.")
    if stock + actual_qty > capacity + .005:
        raise ValueError(f"This receipt would exceed tank capacity ({capacity:,.2f} L).")
    supplier = str(payload.get("supplier", "")).strip()
    supplier_id = get_or_create_supplier_id(conn, supplier)
    variance = actual_qty - invoice_qty
    receipt_cost = actual_qty * unit_cost
    receipt_date = _date(payload, "receipt_date")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO fuel_receipts (
            supplier_name,supplier_id,tank_id,invoice_number,delivery_note,
            quantity_received,remaining_quantity,cost_price,total_cost,
            receipt_date,invoice_quantity,product,short_over_litres,
            variance_value,vehicle_number,driver_name,driver_phone,receipt_type
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (supplier, supplier_id, tank_id, str(payload.get("invoice_number", "")).strip(),
          str(payload.get("delivery_note", "")).strip(), actual_qty, actual_qty,
          unit_cost, receipt_cost, receipt_date, invoice_qty,
          product, variance, variance * unit_cost,
          str(payload.get("vehicle_number", "")).strip(),
          str(payload.get("driver_name", "")).strip(),
          str(payload.get("driver_phone", "")).strip(), "Delivery"))
    receipt_id = cursor.lastrowid
    cursor.execute("UPDATE tanks SET current_stock=COALESCE(current_stock,0)+? WHERE id=?", (actual_qty, tank_id))
    link_receipt_to_product_runs(cursor, receipt_id, tank_id, product, actual_qty,
                                 receipt_cost, _pump_openings(payload, conn, tank_id))
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pump_sessions'").fetchone():
        rebuild_fifo_product(cursor, product)


def _import_tank_dip(conn, payload):
    tank = _tank(conn, payload.get("tank", ""))
    tank_id, _name, _product, capacity, _stock, _active = tank
    opening = _number(payload, "opening_dip")
    closing = _number(payload, "closing_dip")
    if max(opening, closing) > capacity:
        raise ValueError(f"Dip cannot exceed tank capacity ({capacity:,.2f} L).")
    dip_date = _date(payload, "dip_date")
    cur = conn.execute("INSERT INTO tank_dips(tank_id,opening_dip,closing_dip,dip_date) VALUES (?,?,?,?)",
                       (tank_id, opening, closing, dip_date))
    dip_id = cur.lastrowid
    latest = conn.execute("""
        SELECT closing_dip,dip_date FROM tank_dips WHERE tank_id=?
        ORDER BY date(dip_date) DESC,id DESC LIMIT 1
    """, (tank_id,)).fetchone()
    conn.execute("""UPDATE tanks SET current_stock=?,current_stock_date=? WHERE id=?""",
                 (latest[0], latest[1], tank_id))


def _import_account_activity(payload, database):
    ensure = str(payload.get("transaction_type", ""))
    transaction_date = _date(payload, "transaction_date")
    try:
        amount = _number(payload, "amount")
    except ValueError:
        raise
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        account = conn.execute("""SELECT id FROM accounts WHERE is_active=1 AND lower(trim(account_name))=lower(trim(?))""", (payload.get("account", ""),)).fetchone()
        if not account:
            raise ValueError("The named source account is not active in the station app.")
        target = None
        target_name = str(payload.get("target_account", "")).strip()
        if target_name:
            row = conn.execute("""SELECT id FROM accounts WHERE is_active=1 AND lower(trim(account_name))=lower(trim(?))""", (target_name,)).fetchone()
            if not row:
                raise ValueError("The named destination account is not active in the station app.")
            target = row[0]
    receipt_id = int(payload.get("receipt_id") or 0) or None
    record_transfer(ensure, amount, transaction_date, reference=str(payload.get("reference", "")),
                    database=database, account_id=account[0], target_account_id=target,
                    receipt_id=receipt_id)


def import_station_entry(entry, database=DATABASE):
    """Import one queued item; local ID logging makes retries idempotent."""
    entry_id = str(entry.get("entry_id", ""))
    payload = entry.get("payload")
    if not entry_id or not isinstance(payload, dict):
        raise ValueError("The website entry is incomplete.")
    entry_type = entry.get("entry_type")
    if entry_type == "account_activity":
        with sqlite3.connect(database, timeout=15) as conn:
            _ensure_import_log(conn)
            if conn.execute("SELECT 1 FROM website_entry_imports WHERE entry_id=?", (entry_id,)).fetchone():
                return "Already imported."
        _import_account_activity(payload, database)
        with sqlite3.connect(database, timeout=15) as conn:
            _ensure_import_log(conn)
            conn.execute("INSERT OR IGNORE INTO website_entry_imports(entry_id) VALUES (?)", (entry_id,))
        return "Imported account activity."
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        _ensure_import_log(conn)
        if conn.execute("SELECT 1 FROM website_entry_imports WHERE entry_id=?", (entry_id,)).fetchone():
            return "Already imported."
        if entry_type == "pump_session":
            _import_pump_session(conn, payload)
            note = "Imported pump session."
        elif entry_type == "fuel_receipt":
            _import_fuel_receipt(conn, payload)
            note = "Imported fuel receipt."
        elif entry_type == "tank_dip":
            _import_tank_dip(conn, payload)
            note = "Imported tank dip."
        else:
            raise ValueError("This website entry type is not supported by the station app.")
        conn.execute("INSERT INTO website_entry_imports(entry_id) VALUES (?)", (entry_id,))
        return note
