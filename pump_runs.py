"""Explicit pump/product runs that link deliveries without guessing sales batches."""

import sqlite3
import math
from datetime import datetime

from fifo_inventory import baseline_cost_for_stock, ensure_fifo_schema


def ensure_pump_run_schema(conn):
    session_columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(pump_sessions)"
    )}
    if session_columns and "run_id" not in session_columns:
        conn.execute("ALTER TABLE pump_sessions ADD COLUMN run_id INTEGER")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS pump_product_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pump_id INTEGER NOT NULL,
            tank_id INTEGER,
            product TEXT NOT NULL,
            opening_meter REAL,
            closing_meter REAL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pump_run_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            receipt_id INTEGER NOT NULL,
            quantity_received REAL NOT NULL DEFAULT 0,
            total_cost REAL NOT NULL DEFAULT 0,
            opening_meter REAL,
            UNIQUE(run_id, receipt_id)
        )
    """)
    run_receipt_columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(pump_run_receipts)"
    )}
    if "opening_meter" not in run_receipt_columns:
        conn.execute(
            "ALTER TABLE pump_run_receipts ADD COLUMN opening_meter REAL"
        )


def link_receipt_to_product_runs(cursor, receipt_id, tank_id, product,
                                 quantity_received, total_cost,
                                 opening_readings):
    """Join overlapping deliveries to open runs; leave new runs to attendants."""
    pumps = cursor.execute(
        "SELECT id FROM pumps WHERE tank_id=? ORDER BY id", (tank_id,)
    ).fetchall()
    for (pump_id,) in pumps:
        active = cursor.execute("""
            SELECT id, tank_id, product FROM pump_product_runs
            WHERE pump_id=? AND status='OPEN'
            ORDER BY id DESC LIMIT 1
        """, (pump_id,)).fetchone()
        if active and (active[1] != tank_id or active[2].casefold() != product.casefold()):
            raise ValueError(
                f"Pump {pump_id} still has an open {active[2]} product run. "
                "Finish that run before linking a different product delivery."
            )
        if active:
            cursor.execute("""
                INSERT INTO pump_run_receipts(
                    run_id,receipt_id,quantity_received,total_cost,opening_meter
                ) VALUES (?,?,?,?,NULL)
            """, (active[0], receipt_id, quantity_received, total_cost))
        else:
            reading = opening_readings.get(pump_id)
            try:
                reading = float(reading)
            except (TypeError, ValueError) as error:
                raise ValueError(
                    f"Enter the opening meter for pump {pump_id} on the Fuel Receipt."
                ) from error
            if not math.isfinite(reading) or reading < 0:
                raise ValueError(
                    f"Pump {pump_id} opening meter must be a finite, non-negative value."
                )
            previous = cursor.execute("""
                SELECT closing_meter FROM pump_product_runs
                WHERE pump_id=? AND status='CLOSED' AND closing_meter IS NOT NULL
                ORDER BY finished_at DESC,id DESC LIMIT 1
            """, (pump_id,)).fetchone()
            if previous and abs(float(previous[0]) - reading) > 0.005:
                raise ValueError(
                    f"Pump {pump_id} opening meter must carry forward from its "
                    f"previous run ({float(previous[0]):,.2f})."
                )
            run_id = cursor.execute("""
                INSERT INTO pump_product_runs(
                    pump_id,tank_id,product,opening_meter
                ) VALUES (?,?,?,?)
            """, (pump_id, tank_id, product, reading)).lastrowid
            cursor.execute("""
                INSERT INTO pump_run_receipts(
                    run_id,receipt_id,quantity_received,total_cost,opening_meter
                ) VALUES (?,?,?,?,?)
            """, (run_id, receipt_id, quantity_received, total_cost, reading))


def opening_meter_for_new_run(conn, pump_id):
    row = conn.execute("""
        SELECT closing_meter FROM pump_product_runs
        WHERE pump_id=? AND status='CLOSED' AND closing_meter IS NOT NULL
        ORDER BY finished_at DESC,id DESC LIMIT 1
    """, (pump_id,)).fetchone()
    return float(row[0]) if row else None


def run_choices(conn, pump_id):
    rows = conn.execute("""
        SELECT r.id, r.product,
               GROUP_CONCAT(fr.invoice_number, ', ')
        FROM pump_product_runs r
        LEFT JOIN pump_run_receipts rr ON rr.run_id=r.id
        LEFT JOIN fuel_receipts fr ON fr.id=rr.receipt_id
        WHERE r.pump_id=? AND r.status='OPEN'
        GROUP BY r.id,r.product
        ORDER BY r.id DESC
    """, (pump_id,)).fetchall()
    options = {}
    for run_id, product, invoices in rows:
        label = f"Run {run_id} | {product} | Receipts: {invoices or 'none'}"
        options[label] = run_id
    return options


def opening_meter_for_run(conn, pump_id, run_id, session_id=None):
    if session_id is not None:
        row = conn.execute("""
            SELECT opening_meter FROM pump_sessions WHERE id=? AND pump_id=?
        """, (session_id, pump_id)).fetchone()
        if row:
            return float(row[0] or 0)

    prior_session = conn.execute("""
        SELECT closing_meter
        FROM pump_sessions
        WHERE run_id=? AND (? IS NULL OR id<>?)
        ORDER BY date(session_date) DESC, session_date DESC, id DESC
        LIMIT 1
    """, (run_id, session_id, session_id)).fetchone()
    if prior_session:
        return float(prior_session[0] or 0)

    run = conn.execute("""
        SELECT opening_meter FROM pump_product_runs WHERE id=? AND pump_id=?
    """, (run_id, pump_id)).fetchone()
    if run and run[0] is not None:
        return float(run[0])

    previous_run = conn.execute("""
        SELECT closing_meter FROM pump_product_runs
        WHERE pump_id=? AND status='CLOSED' AND closing_meter IS NOT NULL
        ORDER BY finished_at DESC,id DESC LIMIT 1
    """, (pump_id,)).fetchone()
    return float(previous_run[0]) if previous_run else None


def record_run_session(cursor, pump_id, run_id, session_id, opening, closing,
                       allow_closed=False, allow_opening_correction=False):
    run = cursor.execute("""
        SELECT status,opening_meter FROM pump_product_runs
        WHERE id=? AND pump_id=?
    """, (run_id, pump_id)).fetchone()
    if not run:
        raise ValueError("Select a stock receipt/product run for this pump.")
    if run[0] != "OPEN" and not allow_closed:
        raise ValueError("This product run is finished; select an open run.")

    current = cursor.execute("""
        SELECT session_date FROM pump_sessions WHERE id=? AND run_id=?
    """, (session_id, run_id)).fetchone()
    if not current:
        raise ValueError("The saved session could not be linked to its product run.")
    current_date = current[0]
    previous = cursor.execute("""
        SELECT closing_meter FROM pump_sessions
        WHERE run_id=? AND id<>?
          AND (date(session_date)<date(?) OR
               (date(session_date)=date(?) AND id<?))
        ORDER BY date(session_date) DESC,session_date DESC,id DESC
        LIMIT 1
    """, (run_id, session_id, current_date, current_date, session_id)).fetchone()
    expected_opening = previous[0] if previous else None
    if expected_opening is None:
        latest_closed = cursor.execute("""
            SELECT closing_meter FROM pump_product_runs
            WHERE pump_id=? AND status='CLOSED' AND closing_meter IS NOT NULL
            ORDER BY finished_at DESC,id DESC LIMIT 1
        """, (pump_id,)).fetchone()
        expected_opening = (
            latest_closed[0] if latest_closed
            else (None if allow_opening_correction else run[1])
        )
    if expected_opening is not None and abs(float(opening) - float(expected_opening)) > 0.005:
        raise ValueError(
            f"Opening meter must continue from the previous run/session reading "
            f"({float(expected_opening):,.2f})."
        )
    following = cursor.execute("""
        SELECT opening_meter FROM pump_sessions
        WHERE run_id=? AND id<>?
          AND (date(session_date)>date(?) OR
               (date(session_date)=date(?) AND id>?))
        ORDER BY date(session_date),session_date,id LIMIT 1
    """, (run_id, session_id, current_date, current_date, session_id)).fetchone()
    if following and abs(float(following[0]) - float(closing)) > 0.005:
        raise ValueError(
            f"Closing meter must continue into the next session "
            f"({float(following[0]):,.2f})."
        )

    cursor.execute("""
        UPDATE pump_product_runs
        SET opening_meter=COALESCE(opening_meter,?),
            closing_meter=?
        WHERE id=?
    """, (opening, closing, run_id))


def close_tank_product(database, tank_id):
    """Finish every open pump run assigned to a tank."""
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_pump_run_schema(conn)
        conn.execute("BEGIN IMMEDIATE")
        ensure_fifo_schema(conn)
        tank = conn.execute(
            "SELECT product FROM tanks WHERE id=?", (tank_id,)
        ).fetchone()
        if not tank:
            raise ValueError("The selected tank was not found.")
        open_runs = conn.execute("""
            SELECT r.id,r.pump_id,r.product,p.pump_number,r.opening_meter
            FROM pump_product_runs r
            JOIN pumps p ON p.id=r.pump_id
            WHERE (p.tank_id=? OR r.tank_id=?) AND r.status='OPEN'
            ORDER BY p.pump_number,r.id
        """, (tank_id, tank_id)).fetchall()
        if not open_runs:
            raise ValueError("The selected tank has no open pump runs to finish.")
        if any(item[2].casefold() != tank[0].casefold() for item in open_runs):
            raise ValueError(
                "The tank has open pump runs assigned to a different product. "
                "Resolve the product assignments before finishing the tank."
            )

        run_sessions = []
        latest_session_date = None
        for open_run_id, pump_id, _product, pump_number, opening_meter in open_runs:
            last_session = conn.execute("""
                SELECT closing_meter,session_date FROM pump_sessions
                WHERE run_id=?
                ORDER BY date(session_date) DESC,session_date DESC,id DESC
                LIMIT 1
            """, (open_run_id,)).fetchone()
            if last_session:
                closing_meter, session_date = last_session
                if latest_session_date is None or str(session_date) > latest_session_date:
                    latest_session_date = str(session_date)
            else:
                prior_run = conn.execute("""
                    SELECT closing_meter FROM pump_product_runs
                    WHERE pump_id=? AND status='CLOSED' AND closing_meter IS NOT NULL
                    ORDER BY finished_at DESC,id DESC LIMIT 1
                """, (pump_id,)).fetchone()
                closing_meter = (
                    opening_meter if opening_meter is not None
                    else prior_run[0] if prior_run else None
                )
                session_date = None
            if closing_meter is None:
                raise ValueError(
                    f"Pump {pump_number} has no saved meter reading to carry "
                    "forward. Record its opening meter before finishing the tank."
                )
            run_sessions.append((open_run_id, closing_meter))

        dip_query = """
            SELECT id,dip_date,closing_dip FROM tank_dips
            WHERE tank_id=?
        """
        dip_params = [tank_id]
        if latest_session_date is not None:
            dip_query += " AND date(dip_date)>=date(?)"
            dip_params.append(latest_session_date)
        dip_query += " ORDER BY date(dip_date) DESC,id DESC LIMIT 1"
        tank_dip = conn.execute(dip_query, dip_params).fetchone()
        if not tank_dip or float(tank_dip[2] or 0) <= 0:
            raise ValueError(
                "Record a non-zero physical closing dip for this tank"
                + (
                    " on or after the latest pump session."
                    if latest_session_date is not None else "."
                )
                + " The remaining fuel becomes the tank desktop."
            )

        desktop_cost = baseline_cost_for_stock(
            conn.cursor(), tank[0], float(tank_dip[2]), tank_dip[1]
        )
        finished_at = datetime.now().isoformat(timespec="seconds")
        for open_run_id, closing_meter in run_sessions:
            conn.execute("""
                UPDATE pump_product_runs
                SET closing_meter=?,status='CLOSED',finished_at=?
                WHERE id=?
            """, (closing_meter, finished_at, open_run_id))
        remaining_runs = conn.execute("""
            SELECT 1
            FROM pump_product_runs r
            JOIN pumps p ON p.id=r.pump_id
            WHERE (p.tank_id=? OR r.tank_id=?) AND r.status='OPEN'
            LIMIT 1
        """, (tank_id, tank_id)).fetchone()
        if remaining_runs:
            raise ValueError(
                "Not all open product runs connected to this tank were closed."
            )
        conn.execute("""
            UPDATE tanks
            SET desktop_stock=?,desktop_cost=?,desktop_date=?,desktop_dip_id=?
            WHERE id=?
        """, (
            float(tank_dip[2]), desktop_cost, tank_dip[1], tank_dip[0], tank_id
        ))
        return [item[0] for item in open_runs]
