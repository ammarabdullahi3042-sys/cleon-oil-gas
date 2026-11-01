"""Small SQLite helpers for product-level FIFO costing.

Receipt batches are depleted oldest-first. Keep receipts and sessions in the
same database and call these helpers inside the caller's SQLite transaction.
"""

import sqlite3


def ensure_fifo_schema(conn):
    """Create FIFO support tables and migrate the current app's tables."""
    cursor = conn.cursor()

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
            receipt_date TEXT
        )
    """)

    receipt_columns = {
        row[1] for row in cursor.execute(
            "PRAGMA table_info(fuel_receipts)"
        ).fetchall()
    }
    additions = {
        "invoice_quantity": "REAL",
        "product": "TEXT",
        "short_over_litres": "REAL NOT NULL DEFAULT 0",
        "variance_value": "REAL NOT NULL DEFAULT 0",
        "vehicle_number": "TEXT",
        "driver_name": "TEXT",
        "driver_phone": "TEXT",
        "receipt_type": "TEXT NOT NULL DEFAULT 'Delivery'",
        "effective_cost_price": "REAL",
    }
    for column, declaration in additions.items():
        if column not in receipt_columns:
            cursor.execute(
                f"ALTER TABLE fuel_receipts ADD COLUMN {column} {declaration}"
            )

    cursor.execute("""
        UPDATE fuel_receipts
        SET invoice_quantity = quantity_received
        WHERE invoice_quantity IS NULL
    """)
    cursor.execute("""
        UPDATE fuel_receipts
        SET remaining_quantity = quantity_received
        WHERE remaining_quantity IS NULL
    """)
    cursor.execute("""
        UPDATE fuel_receipts
        SET product = (
            SELECT t.product FROM tanks t
            WHERE t.id = fuel_receipts.tank_id
        )
        WHERE product IS NULL OR product = ''
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

    session_exists = cursor.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='pump_sessions'
    """).fetchone()

    if session_exists:
        session_columns = {
            row[1] for row in cursor.execute(
                "PRAGMA table_info(pump_sessions)"
            ).fetchall()
        }
        for column in ("cost_of_goods_sold", "gross_profit",
                       "average_cost_per_litre", "product",
                       "rtt_litres", "rtt_cost"):
            if column not in session_columns:
                declaration = "TEXT" if column == "product" else "REAL NOT NULL DEFAULT 0"
                cursor.execute(
                    f"ALTER TABLE pump_sessions ADD COLUMN "
                    f"{column} {declaration}"
                )

        cursor.execute("""
            UPDATE pump_sessions
            SET product = (
                SELECT t.product
                FROM pumps p
                JOIN tanks t ON t.id = p.tank_id
                WHERE p.id = pump_sessions.pump_id
            )
            WHERE product IS NULL OR product=''
        """)


def baseline_cost_for_stock(cursor, product, litres, baseline_date):
    """Value baseline litres at the product's weighted receipt cost."""
    litres = float(litres or 0)
    if litres <= 0:
        return 0.0
    cursor.execute("""
        SELECT COALESCE(SUM(
                   COALESCE(quantity_received,0) *
                   COALESCE(effective_cost_price,cost_price,0)
               ),0),
               COALESCE(SUM(quantity_received),0)
        FROM fuel_receipts
        WHERE product=? AND date(receipt_date)<=date(?)
    """, (product, baseline_date))
    stock_value, stock_litres = cursor.fetchone()
    if not stock_litres:
        raise ValueError(
            f"No costed {product} stock is available to value the "
            "remaining tank baseline. Record the opening fuel as a dated "
            "receipt with its cost before finishing the tank."
        )
    return litres * float(stock_value or 0) / float(stock_litres)


def product_for_pump(cursor, pump_id):
    cursor.execute("""
        SELECT t.product
        FROM pumps p
        JOIN tanks t ON t.id = p.tank_id
        WHERE p.id = ?
    """, (pump_id,))
    row = cursor.fetchone()
    if not row or not row[0]:
        raise ValueError("The selected pump is not assigned to a product tank.")
    return row[0]


def restore_session_allocations(cursor, session_id):
    """Return a session's consumed litres to their receipt batches."""
    cursor.execute("""
        SELECT receipt_id, litres
        FROM fifo_session_allocations
        WHERE session_id = ?
    """, (session_id,))
    allocations = cursor.fetchall()

    for receipt_id, litres in allocations:
        cursor.execute("""
            UPDATE fuel_receipts
            SET remaining_quantity = remaining_quantity + ?
            WHERE id = ?
        """, (litres, receipt_id))

    cursor.execute(
        "DELETE FROM fifo_session_allocations WHERE session_id=?",
        (session_id,)
    )


def consume_fifo(cursor, session_id, product, litres, session_date):
    """Consume a session's sales from oldest eligible product batches."""
    litres = float(litres)
    if litres < 0:
        raise ValueError("Litres sold cannot be negative.")

    cursor.execute("""
        SELECT id, remaining_quantity,
               COALESCE(effective_cost_price,cost_price)
        FROM fuel_receipts
        WHERE product = ?
          AND COALESCE(remaining_quantity, 0) > 0
          AND date(receipt_date) <= date(?)
        ORDER BY date(receipt_date), id
    """, (product, session_date))
    batches = cursor.fetchall()

    available = sum(float(row[1] or 0) for row in batches)
    if available + 0.000001 < litres:
        raise ValueError(
            f"Insufficient recorded stock for {product}. "
            f"Available: {available:,.2f} L; required: {litres:,.2f} L. "
            "Record opening stock as a dated receipt batch with its cost first."
        )

    remaining_to_issue = litres
    cost_of_goods_sold = 0.0

    for receipt_id, batch_remaining, unit_cost in batches:
        if remaining_to_issue <= 0.000001:
            break

        batch_remaining = float(batch_remaining or 0)
        unit_cost = float(unit_cost or 0)
        issued = min(batch_remaining, remaining_to_issue)

        cursor.execute("""
            UPDATE fuel_receipts
            SET remaining_quantity = remaining_quantity - ?
            WHERE id = ?
        """, (issued, receipt_id))

        cursor.execute("""
            INSERT INTO fifo_session_allocations (
                session_id, receipt_id, litres, unit_cost
            )
            VALUES (?, ?, ?, ?)
        """, (session_id, receipt_id, issued, unit_cost))

        cost_of_goods_sold += issued * unit_cost
        remaining_to_issue -= issued

    return cost_of_goods_sold


def rebuild_fifo_product(cursor, product):
    """Recalculate batch balances and COGS for one product chronologically.

    This makes backdated receipts and edits consistent. If recorded sales
    exceed recorded receipt batches, the transaction fails and the operator
    must enter opening inventory with its cost before continuing.
    """
    cursor.execute("""
        SELECT id, quantity_received
        FROM fuel_receipts
        WHERE product=?
        ORDER BY date(receipt_date), id
    """, (product,))
    batches = cursor.fetchall()

    for receipt_id, quantity in batches:
        cursor.execute("""
            UPDATE fuel_receipts
            SET remaining_quantity=?
            WHERE id=?
        """, (float(quantity or 0), receipt_id))

    cursor.execute("""
        DELETE FROM fifo_session_allocations
        WHERE session_id IN (
            SELECT id FROM pump_sessions WHERE product=?
        )
    """, (product,))

    cursor.execute("""
        SELECT id, litres_sold, sale_amount, session_date, rtt_litres
        FROM pump_sessions
        WHERE product=?
        ORDER BY date(session_date), session_date, id
    """, (product,))
    sessions = cursor.fetchall()

    for session_id, litres_sold, sale_amount, session_date, rtt_litres in sessions:
        cogs = consume_fifo(
            cursor,
            session_id,
            product,
            float(litres_sold or 0),
            str(session_date)[:10]
        )
        litres = float(litres_sold or 0)
        average_cost = cogs / litres if litres else 0
        if not average_cost and float(rtt_litres or 0) > 0:
            cursor.execute("""
                SELECT COALESCE(SUM(remaining_quantity * cost_price), 0),
                       COALESCE(SUM(remaining_quantity), 0)
                FROM fuel_receipts
                WHERE product=? AND date(receipt_date)<=date(?)
            """, (product, str(session_date)[:10]))
            stock_value, stock_litres = cursor.fetchone()
            average_cost = (float(stock_value or 0) / float(stock_litres)
                            if stock_litres else 0)
        gross_profit = float(sale_amount or 0) - cogs
        # RTT is returned stock, so it is excluded from litres_sold and COGS.
        # Value it at this session's FIFO unit cost for a consistent report.
        rtt_cost = float(rtt_litres or 0) * average_cost

        cursor.execute("""
            UPDATE pump_sessions
            SET cost_of_goods_sold=?,
                gross_profit=?,
                average_cost_per_litre=?,
                rtt_cost=?
            WHERE id=?
        """, (cogs, gross_profit, average_cost, rtt_cost, session_id))


def latest_product_for_session(cursor, session_id):
    cursor.execute(
        "SELECT product FROM pump_sessions WHERE id=?",
        (session_id,)
    )
    row = cursor.fetchone()
    return row[0] if row else None
