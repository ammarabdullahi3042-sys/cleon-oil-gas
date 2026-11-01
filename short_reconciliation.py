"""Auditable attendant short recovery and delivery-short settlement ledgers."""

import math
import sqlite3
from datetime import date

from account import ensure_account_schema
from date_utils import parse_flexible_date
from fifo_inventory import ensure_fifo_schema, rebuild_fifo_product


def ensure_reconciliation_schema(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendant_short_reconciliations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendant_id INTEGER NOT NULL,
            reduced_amount REAL NOT NULL,
            recovered_amount REAL NOT NULL DEFAULT 0,
            recovery_date TEXT NOT NULL,
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendant_short_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reconciliation_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            UNIQUE(reconciliation_id,session_id)
        )
    """)
    conn.execute("""
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    transaction_columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(account_transactions)"
    )} if conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='account_transactions'
    """).fetchone() else set()
    if transaction_columns and "short_reconciliation_id" not in transaction_columns:
        conn.execute(
            "ALTER TABLE account_transactions ADD COLUMN short_reconciliation_id INTEGER"
        )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_schema_migrations (
            migration_key TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    migrated = conn.execute("""
        SELECT 1 FROM app_schema_migrations
        WHERE migration_key='station_borne_receipt_fifo_cost_v3'
    """).fetchone()
    if not migrated:
        ensure_fifo_schema(conn)
        affected_products = set()
        receipts = conn.execute("""
            SELECT r.id,r.product,COALESCE(r.total_cost,0),
                   COALESCE(r.quantity_received,0),
                   COALESCE(SUM(s.station_borne_cost),0)
            FROM fuel_receipts r
            JOIN receipt_short_reconciliations s ON s.receipt_id=r.id
            GROUP BY r.id,r.product,r.total_cost,r.quantity_received
        """).fetchall()
        for receipt_id, product, total_cost, quantity, station_cost in receipts:
            if float(quantity or 0) <= 0:
                continue
            effective = max(
                float(total_cost or 0) + float(station_cost or 0), 0
            ) / float(quantity)
            conn.execute(
                "UPDATE fuel_receipts SET effective_cost_price=? WHERE id=?",
                (effective, receipt_id),
            )
            if product:
                affected_products.add(product)
        has_sessions = conn.execute("""
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='pump_sessions'
        """).fetchone()
        if has_sessions:
            for product in affected_products:
                rebuild_fifo_product(conn.cursor(), product)
        conn.execute("""
            INSERT INTO app_schema_migrations(migration_key)
            VALUES ('station_borne_receipt_fifo_cost_v3')
        """)
    sign_migration = conn.execute("""
        SELECT 1 FROM app_schema_migrations
        WHERE migration_key='session_short_negative_over_positive_v1'
    """).fetchone()
    if not sign_migration:
        has_sessions = conn.execute("""
            SELECT 1 FROM sqlite_master
            WHERE type='table' AND name='pump_sessions'
        """).fetchone()
        if has_sessions:
            conn.execute("""
                UPDATE pump_sessions
                SET short_over=-COALESCE(short_over,0)
            """)
        conn.execute("""
            INSERT INTO app_schema_migrations(migration_key)
            VALUES ('session_short_negative_over_positive_v1')
        """)


def attendant_short_balances(conn, attendant_id):
    ensure_reconciliation_schema(conn)
    sessions = conn.execute("""
        SELECT ps.id,ps.session_date,MAX(-COALESCE(ps.short_over,0),0),
               COALESCE(SUM(CASE
                   WHEN date(r.recovery_date)<=date('now') THEN sa.amount
                   ELSE 0
               END),0)
        FROM pump_sessions ps
        LEFT JOIN attendant_short_allocations sa ON sa.session_id=ps.id
        LEFT JOIN attendant_short_reconciliations r
          ON r.id=sa.reconciliation_id
        WHERE ps.attendant_id=?
        GROUP BY ps.id,ps.session_date,ps.short_over
        ORDER BY date(ps.session_date),ps.id
    """, (attendant_id,)).fetchall()
    return [(row[0], row[1], float(row[2] or 0),
             max(float(row[2] or 0) - float(row[3] or 0), 0))
            for row in sessions]


def attendant_short_outstanding(conn, attendant_id):
    return sum(row[3] for row in attendant_short_balances(conn, attendant_id))


def adjusted_session_short_over(conn, session_id, short_over, as_of_date=None):
    """Return the session short/over after applicable short reconciliations."""
    ensure_reconciliation_schema(conn)
    short_over = float(short_over or 0)
    if short_over >= 0:
        return short_over
    if as_of_date is None:
        allocation = conn.execute("""
            SELECT COALESCE(SUM(sa.amount),0)
            FROM attendant_short_allocations sa
            JOIN attendant_short_reconciliations r
              ON r.id=sa.reconciliation_id
            WHERE sa.session_id=? AND date(r.recovery_date)<=date('now')
        """, (session_id,)).fetchone()[0]
    else:
        allocation = conn.execute("""
            SELECT COALESCE(SUM(sa.amount),0)
            FROM attendant_short_allocations sa
            JOIN attendant_short_reconciliations r
              ON r.id=sa.reconciliation_id
            WHERE sa.session_id=? AND date(r.recovery_date)<=date(?)
        """, (session_id, as_of_date)).fetchone()[0]
    return min(short_over + float(allocation or 0), 0.0)


def adjusted_short_over_total(conn, start, end, as_of_date=None):
    """Sum session short/over values after allocated reconciliations."""
    rows = conn.execute("""
        SELECT id,COALESCE(short_over,0)
        FROM pump_sessions
        WHERE date(session_date) BETWEEN date(?) AND date(?)
    """, (start, end)).fetchall()
    return sum(
        adjusted_session_short_over(conn, row[0], row[1], as_of_date)
        for row in rows
    )


def reconcile_attendant_short(database, attendant_id, reduced_amount,
                              recovered_amount, recovery_date, notes=""):
    try:
        reduced_amount = float(reduced_amount)
        recovered_amount = float(recovered_amount)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter valid amounts for the short reduction and recovery.") from error
    if (not math.isfinite(reduced_amount) or not math.isfinite(recovered_amount)
            or reduced_amount <= 0 or recovered_amount < 0):
        raise ValueError("Short reduction must be positive and recovery cannot be negative.")
    if recovered_amount > reduced_amount:
        raise ValueError("Recovered sales money cannot exceed the amount being reconciled.")
    try:
        recovery_date = parse_flexible_date(recovery_date).isoformat()
    except ValueError as error:
        raise ValueError("Enter a valid recovery date.") from error

    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_reconciliation_schema(conn)
        allocations = attendant_short_balances(conn, attendant_id)
        outstanding = sum(row[3] for row in allocations)
        if reduced_amount > outstanding + 0.005:
            raise ValueError(
                f"Reduction exceeds the outstanding short of ₦{outstanding:,.2f}."
            )
        cursor = conn.execute("""
            INSERT INTO attendant_short_reconciliations(
                attendant_id,reduced_amount,recovered_amount,recovery_date,notes
            ) VALUES (?,?,?,?,?)
        """, (attendant_id, reduced_amount, recovered_amount, recovery_date,
              str(notes or "").strip()))
        reconciliation_id = cursor.lastrowid

        remaining = reduced_amount
        for session_id, _day, _recorded, session_outstanding in allocations:
            if remaining <= 0.005:
                break
            amount = min(remaining, session_outstanding)
            if amount > 0:
                conn.execute("""
                    INSERT INTO attendant_short_allocations(
                        reconciliation_id,session_id,amount
                    ) VALUES (?,?,?)
                """, (reconciliation_id, session_id, amount))
                remaining -= amount

        if recovered_amount > 0:
            ensure_account_schema(conn)
            cash_id = conn.execute("""
                SELECT id FROM accounts WHERE account_type='CASH'
                ORDER BY id LIMIT 1
            """).fetchone()[0]
            conn.execute("""
                INSERT INTO account_transactions(
                    transaction_date,transaction_type,amount,bank_name,
                    reference,description,account_id,short_reconciliation_id
                ) VALUES (?,'Account Receipt',?,?,?,?,?,?)
            """, (
                recovery_date, recovered_amount, "Station Cash",
                f"Short recovery #{reconciliation_id}",
                "Recovered from attendant; excluded from pump-session sales totals.",
                cash_id, reconciliation_id
            ))
        return reconciliation_id


def receipt_short_amounts(conn, receipt_id):
    ensure_reconciliation_schema(conn)
    row = conn.execute("""
        SELECT MAX(COALESCE(invoice_quantity,quantity_received)
                   -COALESCE(quantity_received,0),0),
               MAX(COALESCE(invoice_quantity,quantity_received)
                   -COALESCE(quantity_received,0),0)*COALESCE(cost_price,0)
        FROM fuel_receipts WHERE id=?
    """, (receipt_id,)).fetchone()
    initial_litres, initial_cost = (float(row[0] or 0), float(row[1] or 0)) if row else (0, 0)
    reconciled = conn.execute("""
        SELECT COALESCE(SUM(reconciled_litres),0),
               COALESCE(SUM(reconciled_cost),0),
               COALESCE(SUM(station_borne_litres),0),
               COALESCE(SUM(station_borne_cost),0)
        FROM receipt_short_reconciliations WHERE receipt_id=?
    """, (receipt_id,)).fetchone()
    return (
        initial_litres, initial_cost,
        max(initial_litres - float(reconciled[0]) - float(reconciled[2]), 0),
        max(initial_cost - float(reconciled[1]) - float(reconciled[3]), 0),
    )


def update_receipt_effective_cost(conn, receipt_id):
    """Add station-borne shortage cost to the receipt's FIFO unit cost."""
    receipt = conn.execute("""
        SELECT product,COALESCE(total_cost,0),COALESCE(quantity_received,0)
        FROM fuel_receipts WHERE id=?
    """, (receipt_id,)).fetchone()
    if not receipt:
        raise ValueError("The selected fuel receipt was not found.")
    product, receipt_cost, quantity_received = receipt
    station_cost = conn.execute("""
        SELECT COALESCE(SUM(station_borne_cost),0)
        FROM receipt_short_reconciliations WHERE receipt_id=?
    """, (receipt_id,)).fetchone()[0]
    if float(quantity_received or 0) <= 0:
        raise ValueError("A receipt must have positive received quantity.")
    adjusted_cost = max(float(receipt_cost or 0) + float(station_cost or 0), 0)
    conn.execute(
        "UPDATE fuel_receipts SET effective_cost_price=? WHERE id=?",
        (adjusted_cost / float(quantity_received), receipt_id),
    )
    has_sessions = conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='pump_sessions'
    """).fetchone()
    if product and has_sessions:
        rebuild_fifo_product(conn.cursor(), product)


def reconcile_receipt_short(database, receipt_id, party_type, party_name,
                            reconciled_litres, reconciled_cost,
                            station_borne_litres, station_borne_cost,
                            disputed, settlement_date, notes=""):
    party_type = str(party_type or "").strip()
    party_name = str(party_name or "").strip()
    if party_type not in ("Supplier", "Driver"):
        raise ValueError("Choose Supplier or Driver as the responsible party.")
    if not party_name:
        raise ValueError("Enter the responsible supplier or driver.")
    try:
        values = tuple(float(value or 0) for value in (
            reconciled_litres, reconciled_cost,
            station_borne_litres, station_borne_cost
        ))
    except (TypeError, ValueError) as error:
        raise ValueError("Enter valid litre and cost amounts.") from error
    if not all(math.isfinite(value) and value >= 0 for value in values):
        raise ValueError("Reconciliation amounts must be finite and non-negative.")
    rl, rc, sl, sc = values
    if rl == rc == sl == sc == 0:
        raise ValueError("Enter at least one settled or station-borne amount.")
    try:
        settlement_date = parse_flexible_date(settlement_date or date.today().isoformat()).isoformat()
    except ValueError as error:
        raise ValueError("Enter a valid settlement date.") from error

    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_fifo_schema(conn)
        ensure_reconciliation_schema(conn)
        _initial_l, _initial_c, remaining_l, remaining_c = receipt_short_amounts(
            conn, receipt_id
        )
        if rl + sl > remaining_l + 0.005:
            raise ValueError(
                f"Settled and station-borne litres exceed the outstanding "
                f"shortage of {remaining_l:,.2f} L."
            )
        if rc + sc > remaining_c + 0.005:
            raise ValueError(
                f"Settled and station-borne cost exceed the outstanding "
                f"shortage cost of ₦{remaining_c:,.2f}."
            )
        exists = conn.execute(
            "SELECT 1 FROM fuel_receipts WHERE id=?", (receipt_id,)
        ).fetchone()
        if not exists:
            raise ValueError("The selected fuel receipt was not found.")
        conn.execute("""
            INSERT INTO receipt_short_reconciliations(
                receipt_id,party_type,party_name,reconciled_litres,
                reconciled_cost,station_borne_litres,station_borne_cost,
                disputed,settlement_date,notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """, (receipt_id, party_type, party_name, rl, rc, sl, sc,
              1 if disputed else 0, settlement_date, str(notes or "").strip()))
        update_receipt_effective_cost(conn, receipt_id)
