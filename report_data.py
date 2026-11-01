"""Shared report datasets for the Report Center and weekly email."""

import sqlite3

from account import ensure_account_schema
from date_utils import format_display_date
from pump_runs import ensure_pump_run_schema
from short_reconciliation import (
    adjusted_session_short_over, ensure_reconciliation_schema,
)


PRODUCT_REPORT_HEADERS = (
    "Date/period", "Receipt", "Gross meter", "RTT", "Gain/loss (litres)",
    "Dip variance estimate (not profit) (NGN)", "Cost", "Sales", "Expenses",
    "Short/over", "Profit/(loss)",
)


def expense_report_rows(conn, start, end):
    """Return categorized expenses and suppress exact Expense/Accounts duplicates."""
    rows = []
    if conn.execute("""
        SELECT 1 FROM sqlite_master WHERE type='table' AND name='expenses'
    """).fetchone():
        for day, description, amount in conn.execute("""
            SELECT expense_date,COALESCE(description,'Expense'),COALESCE(amount,0)
            FROM expenses
            WHERE date(expense_date) BETWEEN date(?) AND date(?)
            ORDER BY date(expense_date),id
        """, (start, end)):
            rows.append((day, "Expense session", description, float(amount or 0)))

    if conn.execute("""
        SELECT 1 FROM sqlite_master WHERE type='table' AND name='pump_sessions'
    """).fetchone():
        for day, pump, attendant, amount in conn.execute("""
            SELECT ps.session_date,COALESCE(p.pump_number,''),
                   COALESCE(a.name,''),COALESCE(ps.expenses,0)
            FROM pump_sessions ps
            LEFT JOIN pumps p ON p.id=ps.pump_id
            LEFT JOIN attendants a ON a.id=ps.attendant_id
            WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
              AND COALESCE(ps.expenses,0)<>0
            ORDER BY date(ps.session_date),ps.id
        """, (start, end)):
            rows.append((day, "Pump session", f"Pump {pump} / {attendant}",
                         float(amount or 0)))

    account_table = conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='account_transactions'
    """).fetchone()
    if account_table:
        account_table_exists = conn.execute("""
            SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'
        """).fetchone()
        account_join = ("LEFT JOIN accounts a ON a.id=t.account_id"
                        if account_table_exists else "")
        account_filter = (
            "(t.transaction_type='Account Expense' OR "
            "(a.account_type='CASH' OR t.account_id IS NULL))"
            if account_table_exists else "1=1"
        )
        expense_exists = conn.execute("""
            SELECT 1 FROM sqlite_master WHERE type='table' AND name='expenses'
        """).fetchone()
        duplicate_clause = """
              AND NOT EXISTS (
                SELECT 1 FROM expenses e
                WHERE date(e.expense_date)=date(t.transaction_date)
                  AND ROUND(COALESCE(e.amount,0),2)=ROUND(t.amount,2)
                  AND lower(trim(COALESCE(e.description,'')))=
                      lower(trim(COALESCE(NULLIF(t.reference,''),t.description,'')))
                  AND trim(COALESCE(e.description,''))<>''
              )
        """ if expense_exists else ""
        for day, description, amount, transaction_type in conn.execute(f"""
            SELECT t.transaction_date,
                   COALESCE(NULLIF(t.reference,''),NULLIF(t.description,''),
                            'Cash expense'),
                   COALESCE(t.amount,0),t.transaction_type
            FROM account_transactions t
            {account_join}
            WHERE t.transaction_type IN ('Cash Expense','Account Expense')
              AND {account_filter}
              AND date(t.transaction_date) BETWEEN date(?) AND date(?)
              {duplicate_clause}
            ORDER BY date(t.transaction_date),t.id
        """, (start, end)):
            source = ("Cash Vault expense" if transaction_type == "Cash Expense"
                      else "Account expense")
            rows.append((day, source, description,
                         float(amount or 0)))
    return sorted(rows, key=lambda row: (str(row[0] or ""), row[1], row[2]))


def expense_totals(conn, start, end):
    return sum(row[3] for row in expense_report_rows(conn, start, end))


def tank_dip_variance_events(conn, tank_id, end):
    """Return dip-period values using finished-product desktop baselines."""
    tank_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(tanks)")
    }
    desktop_columns = [
        column for column in ("desktop_dip_id", "desktop_date", "desktop_stock")
        if column in tank_columns
    ]
    desktop_row = None
    if desktop_columns:
        desktop_row = conn.execute(
            f"SELECT {','.join(desktop_columns)} FROM tanks WHERE id=?",
            (tank_id,),
        ).fetchone()
    desktop_values = dict(zip(desktop_columns, desktop_row or ()))
    desktop_dip_id = desktop_values.get("desktop_dip_id")
    desktop_date = desktop_values.get("desktop_date")
    desktop_stock = desktop_values.get("desktop_stock")
    dips = conn.execute("""
        SELECT id,dip_date,COALESCE(opening_dip,0),COALESCE(closing_dip,0)
        FROM tank_dips
        WHERE tank_id=? AND date(dip_date)<=date(?)
        ORDER BY date(dip_date),id
    """, (tank_id, end)).fetchall()
    events = []
    baseline_date = None
    baseline_litres = 0.0
    include_baseline_date = False
    has_baseline = False

    for dip_id, dip_date, opening, closing in dips:
        is_desktop = dip_id == desktop_dip_id
        if (
            not is_desktop and desktop_dip_id is None and desktop_date
            and dip_date == desktop_date and desktop_stock is not None
            and abs(float(closing or 0) - float(desktop_stock or 0)) <= 0.01
        ):
            is_desktop = True
        if is_desktop:
            events.append({
                "id": dip_id, "date": dip_date, "opening": opening,
                "closing": closing, "received": 0.0, "sold": 0.0,
                "baseline_litres": float(closing or 0),
                "variance": None, "baseline": True, "desktop": True,
            })
            baseline_date = dip_date
            baseline_litres = float(closing or 0)
            include_baseline_date = False
            has_baseline = True
            continue

        if not has_baseline:
            baseline_date = dip_date
            baseline_litres = float(opening or 0)
            include_baseline_date = True
            has_baseline = True

        date_operator = ">=" if include_baseline_date else ">"
        sold, received = conn.execute(f"""
            SELECT
                COALESCE((SELECT SUM(ps.litres_sold)
                          FROM pumps p
                          JOIN pump_sessions ps ON ps.pump_id=p.id
                          WHERE p.tank_id=?
                            AND date(ps.session_date){date_operator}date(?)
                            AND date(ps.session_date)<=date(?)),0),
                COALESCE((SELECT SUM(fr.quantity_received)
                          FROM fuel_receipts fr
                          WHERE fr.tank_id=?
                            AND date(fr.receipt_date){date_operator}date(?)
                            AND date(fr.receipt_date)<=date(?)),0)
        """, (
            tank_id, baseline_date, dip_date,
            tank_id, baseline_date, dip_date,
        )).fetchone()
        sold = float(sold or 0)
        received = float(received or 0)
        has_activity = abs(sold) > 0.000001 or abs(received) > 0.000001
        events.append({
            "id": dip_id, "date": dip_date, "opening": opening,
            "closing": closing, "received": received, "sold": sold,
            "baseline_litres": baseline_litres,
            "variance": (
                sold - (float(opening or 0) + received - float(closing or 0))
                if has_activity else None
            ),
            "baseline": not has_activity, "desktop": False,
        })
        baseline_date = dip_date
        baseline_litres = float(closing or 0)
        include_baseline_date = False
    return events


def tank_dip_variance_adjustments(conn, start, end, tank_id=None):
    """Return signed dip variance litres and value for each tank in the period."""
    if not conn.execute("""
        SELECT 1 FROM sqlite_master WHERE type='table' AND name='tank_dips'
    """).fetchone():
        return {}

    from price_management import ensure_price_schema

    ensure_price_schema(conn)
    adjustments = {}
    has_product_runs = bool(conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='pump_product_runs'
    """).fetchone())
    tank_filter = "WHERE id=?" if tank_id is not None else ""
    tanks = conn.execute(f"""
        SELECT id,COALESCE(product,'') FROM tanks
        {tank_filter} ORDER BY id
    """, (tank_id,) if tank_id is not None else ()).fetchall()
    for tank_id, product in tanks:
        for event in tank_dip_variance_events(conn, tank_id, end):
            if event["variance"] is None:
                continue
            in_period = conn.execute(
                "SELECT date(?) BETWEEN date(?) AND date(?)",
                (event["date"], start, end),
            ).fetchone()[0]
            if not in_period:
                continue
            variance_litres = float(event["variance"])
            dip_product = conn.execute("""
                SELECT product FROM pump_product_runs
                WHERE tank_id=? AND date(started_at)<=date(?)
                ORDER BY date(started_at) DESC,id DESC LIMIT 1
            """, (tank_id, event["date"])).fetchone() if has_product_runs else None
            product_at_dip = dip_product[0] if dip_product else product
            price = conn.execute("""
                SELECT price_per_litre FROM product_prices
                WHERE UPPER(TRIM(product))=UPPER(TRIM(?))
                  AND date(effective_date)<=date(?)
                ORDER BY date(effective_date) DESC,id DESC LIMIT 1
            """, (product_at_dip, event["date"])).fetchone()
            if abs(variance_litres) > 0.000001 and not price:
                raise ValueError(
                    f"No selling price is recorded for {product_at_dip or 'this product'} "
                    f"on {event['date']}, so tank dip overage/shortage cannot be valued."
                )
            adjustment = adjustments.setdefault(
                tank_id, {"litres": 0.0, "amount": 0.0}
            )
            adjustment["litres"] += variance_litres
            adjustment["amount"] += (
                variance_litres * float(price[0]) if price else 0.0
            )
    return adjustments


def profit_adjustments(conn, start, end):
    """Return attendant shorts, delivery losses and signed tank dip adjustments."""
    ensure_reconciliation_schema(conn)
    short_amount = conn.execute("""
        SELECT COALESCE(SUM(MAX(-COALESCE(short_over,0),0)),0)
        FROM pump_sessions ps
        WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
    """, (start, end)).fetchone()[0]
    reconciled = conn.execute("""
        SELECT COALESCE(SUM(sa.amount),0)
        FROM pump_sessions ps
        JOIN attendant_short_allocations sa ON sa.session_id=ps.id
        JOIN attendant_short_reconciliations r ON r.id=sa.reconciliation_id
        WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
          AND date(r.recovery_date)<=date(?)
    """, (start, end, end)).fetchone()[0]
    delivery_loss = conn.execute("""
        SELECT COALESCE(SUM(station_borne_cost),0)
        FROM receipt_short_reconciliations
        WHERE date(settlement_date) BETWEEN date(?) AND date(?)
    """, (start, end)).fetchone()[0]
    tank_adjustment = sum(
        item["amount"]
        for item in tank_dip_variance_adjustments(conn, start, end).values()
    )
    return (
        max(float(short_amount or 0) - float(reconciled or 0), 0),
        float(delivery_loss or 0),
        tank_adjustment,
    )


def product_delivery_report(database, start, end):
    """Return eleven columns, one row per product/tank and period."""
    with sqlite3.connect(database, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        ensure_pump_run_schema(conn)
        ensure_reconciliation_schema(conn)
        ensure_account_schema(conn)
        dip_adjustments = tank_dip_variance_adjustments(conn, start, end)
        product_tanks = conn.execute("""
            SELECT id,COALESCE(tank_number,''),COALESCE(product,''),
                   COALESCE(current_stock,0)
            FROM tanks ORDER BY product,tank_number,id
        """).fetchall()
        rows = []
        product_rows = []
        for tank_id, tank_number, product, current_stock in product_tanks:
            receipts = conn.execute("""
                SELECT id,receipt_date,invoice_number,delivery_note,
                       COALESCE(invoice_quantity,quantity_received) invoice_l,
                       COALESCE(quantity_received,0) received_l,
                       COALESCE(total_cost,0) total_cost,
                       COALESCE(cost_price,0) cost_price,
                       COALESCE(short_over_litres,0) variance_l
                FROM fuel_receipts
                WHERE tank_id=? AND date(receipt_date) BETWEEN date(?) AND date(?)
                ORDER BY date(receipt_date),id
            """, (tank_id, start, end)).fetchall()
            sessions = conn.execute("""
                SELECT ps.id,ps.run_id,ps.opening_meter,ps.closing_meter,
                       COALESCE(ps.litres_sold,0) sold,
                       COALESCE(ps.rtt_litres,0) rtt,
                       COALESCE(ps.rtt_cost,
                           COALESCE(ps.rtt_litres,0)*
                           COALESCE(ps.average_cost_per_litre,0)) rtt_cost,
                       COALESCE(ps.sale_amount,0) sales,
                       COALESCE(ps.cost_of_goods_sold,0) cogs,
                       COALESCE(ps.gross_profit,0) gross_profit,
                       COALESCE(ps.expenses,0) expenses,
                       COALESCE(ps.short_over,0) short_over,
                       COALESCE(p.pump_number,'') pump
                FROM pump_sessions ps
                JOIN pumps p ON p.id=ps.pump_id
                WHERE p.tank_id=? AND date(ps.session_date)
                      BETWEEN date(?) AND date(?)
                  AND ps.run_id IN (
                    SELECT DISTINCT rr.run_id FROM pump_run_receipts rr
                    JOIN fuel_receipts fr ON fr.id=rr.receipt_id
                    WHERE fr.tank_id=?
                  )
                ORDER BY date(ps.session_date),ps.id
            """, (tank_id, start, end, tank_id)).fetchall()
            if not receipts and not sessions and tank_id not in dip_adjustments:
                continue

            receipt_ids = [row["id"] for row in receipts]
            receipt_label = ", ".join(
                f"#{row['id']} {row['invoice_number'] or row['delivery_note'] or ''}".strip()
                for row in receipts
            ) or "No linked receipt in period"
            received = sum(float(row["received_l"] or 0) for row in receipts)
            net_sold = sum(float(row["sold"] or 0) for row in sessions)
            gross_meter = sum(
                float(row["closing_meter"] or 0) -
                float(row["opening_meter"] or 0)
                for row in sessions
            )
            rtt_litres = sum(float(row["rtt"] or 0) for row in sessions)
            rtt_cost = sum(float(row["rtt_cost"] or 0) for row in sessions)
            sales = sum(float(row["sales"] or 0) for row in sessions)
            cogs = sum(float(row["cogs"] or 0) for row in sessions)
            gross_profit = sum(float(row["gross_profit"] or 0) for row in sessions)
            session_expenses = sum(float(row["expenses"] or 0) for row in sessions)
            session_short = sum(
                max(-float(row["short_over"] or 0), 0) for row in sessions
            )
            session_ids = [row["id"] for row in sessions]
            signed_short_over = sum(
                adjusted_session_short_over(
                    conn, row["id"], row["short_over"], end
                )
                for row in sessions
            )

            if receipt_ids:
                marks = ",".join("?" for _ in receipt_ids)
                settlement = conn.execute(f"""
                    SELECT COALESCE(SUM(station_borne_cost),0)
                    FROM receipt_short_reconciliations
                    WHERE receipt_id IN ({marks})
                      AND date(settlement_date)<=date(?)
                """, (*receipt_ids, end)).fetchone()
                station_loss = float(settlement[0] or 0)
            else:
                station_loss = 0.0
            reconciled_session_short = 0.0
            if session_ids:
                marks = ",".join("?" for _ in session_ids)
                reconciled_session_short = float(conn.execute(f"""
                    SELECT COALESCE(SUM(sa.amount),0)
                    FROM attendant_short_allocations sa
                    JOIN attendant_short_reconciliations r
                      ON r.id=sa.reconciliation_id
                    WHERE sa.session_id IN ({marks})
                      AND date(r.recovery_date)<=date(?)
                """, (*session_ids, end)).fetchone()[0] or 0)
            session_short_loss = max(session_short - reconciled_session_short, 0)
            dip_adjustment = dip_adjustments.get(tank_id)
            gain_loss = dip_adjustment["litres"] if dip_adjustment else None
            dip_profit_loss = dip_adjustment["amount"] if dip_adjustment else 0.0

            # Session net litres already subtract RTT from meter movement.
            # RTT remains a separate litre metric and is not subtracted again
            # from monetary profit. Reconciled attendant shorts reduce the
            # outstanding short; station-borne delivery cost remains a loss.
            product_expenses = session_expenses
            product_profit = (
                sales - cogs - session_short_loss - station_loss
                - product_expenses
            )
            reported_expenses = product_expenses + station_loss
            short_label = f"NGN {signed_short_over:+,.2f}"
            product_rows.append({
                "tank_id": tank_id, "tank": tank_number, "product": product,
                "receipt_ids": receipt_ids, "receipt_label": receipt_label,
                "gross": gross_meter, "rtt_litres": rtt_litres,
                "gain_loss": gain_loss, "dip_profit_loss": dip_profit_loss,
                "cost": cogs, "receipt_cost": max(
                    sum(float(row["total_cost"] or 0) for row in receipts)
                    + station_loss, 0
                ), "sales": sales,
                "expenses": reported_expenses, "short_label": short_label,
                "signed_short_over": signed_short_over,
                "profit": product_profit, "received": received,
                "sold": net_sold, "stock": float(current_stock or 0),
                "rtt_cost": rtt_cost, "cogs": cogs,
                "gross_profit": gross_profit, "station_loss": station_loss,
                "session_short": session_short,
                "recovered_short": reconciled_session_short,
                "reconciled_short": reconciled_session_short,
                "session_short_loss": session_short_loss,
                "session_ids": [r["id"] for r in sessions],
            })
            rows.append((
                f"{format_display_date(start)} to {format_display_date(end)}",
                f"{product} / {tank_number}: {receipt_label}",
                f"{gross_meter:,.2f} L", f"{rtt_litres:,.2f} L",
                ("Baseline only" if gain_loss is None
                 else f"{gain_loss:+,.2f} L"),
                f"NGN {dip_profit_loss:+,.2f}",
                f"NGN {cogs:,.2f}",
                f"NGN {sales:,.2f}", f"NGN {reported_expenses:,.2f}",
                short_label, f"NGN {product_profit:,.2f}",
            ))

        # General expenses without a reliable tank/product relationship remain
        # visible as a distinct period row instead of being copied to each product.
        expense_rows = expense_report_rows(conn, start, end)
        unallocated_expenses = sum(
            value for _day, source, _description, value in expense_rows
            if source != "Pump session"
        )
        if unallocated_expenses:
            rows.append((
                f"{start} to {end}",                 "UNALLOCATED PERIOD EXPENSES", "", "", "", "", "", "",
                f"NGN {unallocated_expenses:,.2f}", "", "",
            ))
        if product_rows:
            total_gross = sum(row["gross"] for row in product_rows)
            total_rtt = sum(row["rtt_litres"] for row in product_rows)
            total_gain = sum(
                row["gain_loss"] or 0 for row in product_rows
            )
            total_dip_profit_loss = sum(
                row["dip_profit_loss"] for row in product_rows
            )
            total_cogs = sum(row["cogs"] for row in product_rows)
            total_sales = sum(row["sales"] for row in product_rows)
            total_short = sum(
                row["signed_short_over"]
                for row in product_rows
            )
            total_profit = sum(row["profit"] for row in product_rows) - unallocated_expenses
            total_operating_expenses = sum(
                row["expenses"] for row in product_rows
            ) + unallocated_expenses
            rows.append((
                f"{format_display_date(start)} to {format_display_date(end)}",
                "PERIOD TOTAL (see product rows)",
                f"{total_gross:,.2f} L", f"{total_rtt:,.2f} L",
                f"{total_gain:+,.2f} L",
                f"NGN {total_dip_profit_loss:+,.2f}",
                f"NGN {total_cogs:,.2f}",
                f"NGN {total_sales:,.2f}",
                f"NGN {total_operating_expenses:,.2f}",
                f"NGN {total_short:+,.2f}",
                f"NGN {total_profit:,.2f}",
            ))
        return list(PRODUCT_REPORT_HEADERS), rows


def product_delivery_detail(database, start, end, tank_id=None):
    """Detailed linked rows for drilldown and the printable/email appendix."""
    with sqlite3.connect(database, timeout=15) as conn:
        conn.row_factory = sqlite3.Row
        ensure_pump_run_schema(conn)
        ensure_reconciliation_schema(conn)
        ensure_account_schema(conn)
        details = []
        tank_filter = "AND t.id=?" if tank_id is not None else ""
        params = [start, end]
        if tank_id is not None:
            params.append(tank_id)
        receipts = conn.execute(f"""
            SELECT fr.id,fr.receipt_date,fr.invoice_number,fr.delivery_note,
                   fr.product,t.tank_number,fr.supplier_name,fr.driver_name,
                   fr.vehicle_number,fr.invoice_quantity,fr.quantity_received,
                   fr.cost_price,fr.total_cost,fr.variance_value,
                   COALESCE((SELECT SUM(at.amount)
                             FROM account_transactions at
                             WHERE at.receipt_id=fr.id
                               AND at.transaction_type='Product Payment'),0)
                       AS product_paid
            FROM fuel_receipts fr JOIN tanks t ON t.id=fr.tank_id
            WHERE date(fr.receipt_date) BETWEEN date(?) AND date(?) {tank_filter}
            ORDER BY date(fr.receipt_date),fr.id
        """, params).fetchall()
        for receipt in receipts:
            recs = conn.execute("""
                SELECT party_type,party_name,reconciled_litres,reconciled_cost,
                       station_borne_litres,station_borne_cost,disputed,
                       settlement_date,COALESCE(notes,'') AS notes
                FROM receipt_short_reconciliations
                WHERE receipt_id=? AND date(settlement_date)<=date(?)
                ORDER BY date(settlement_date),id
            """, (receipt["id"], end)).fetchall()
            initial_l = max(float(receipt["invoice_quantity"] or 0)
                            - float(receipt["quantity_received"] or 0), 0)
            station_borne_cost = sum(
                float(item["station_borne_cost"] or 0) for item in recs
            )
            adjusted_receipt_cost = (
                float(receipt["total_cost"] or 0) + station_borne_cost
            )
            details.append((
                "Delivery receipt", receipt["receipt_date"], receipt["product"],
                receipt["tank_number"], f"#{receipt['id']} {receipt['invoice_number'] or ''}",
                receipt["supplier_name"] or "", receipt["driver_name"] or "",
                receipt["vehicle_number"] or "",
                f"Invoice {float(receipt['invoice_quantity'] or 0):,.2f} L; "
                f"received {float(receipt['quantity_received'] or 0):,.2f} L; "
                f"variance {float(receipt['variance_value'] or 0):+,.2f} NGN; "
                f"product paid NGN {float(receipt['product_paid'] or 0):,.2f}; "
                f"balance due NGN {max(adjusted_receipt_cost-float(receipt['product_paid'] or 0),0):,.2f}",
                f"Initial shortage {initial_l:,.2f} L / "
                f"NGN {initial_l*float(receipt['cost_price'] or 0):,.2f}; "
                f"receipt cost NGN {float(receipt['total_cost'] or 0):,.2f}; "
                f"station borne NGN {station_borne_cost:,.2f}; "
                f"adjusted product cost NGN {adjusted_receipt_cost:,.2f}",
            ))
            for item in recs:
                details.append((
                    "Receipt settlement", item["settlement_date"],
                    receipt["product"], receipt["tank_number"],
                    f"#{receipt['id']}", item["party_type"], item["party_name"],
                    receipt["vehicle_number"] or "",
                    f"settled {float(item['reconciled_litres'] or 0):,.2f} L / "
                    f"NGN {float(item['reconciled_cost'] or 0):,.2f}; "
                    f"station borne {float(item['station_borne_litres'] or 0):,.2f} L / "
                    f"NGN {float(item['station_borne_cost'] or 0):,.2f}",
                    f"{'DISPUTED; ' if item['disputed'] else ''}{item['notes']}",
                ))

        run_query = """
            SELECT r.id,r.product,t.tank_number,p.pump_number,r.opening_meter,
                   r.closing_meter,r.status,ps.id AS session_id,
                   ps.session_date,ps.opening_meter AS shift_open,
                   ps.closing_meter AS shift_close,ps.rtt_litres,ps.litres_sold,
                   ps.sale_amount,ps.cost_of_goods_sold,ps.gross_profit,ps.expenses,
                   ps.short_over,a.name AS attendant,
                   GROUP_CONCAT(DISTINCT fr.id || ':' || COALESCE(fr.invoice_number,'')) receipts
            FROM pump_product_runs r JOIN pumps p ON p.id=r.pump_id
            JOIN tanks t ON t.id=r.tank_id
            JOIN pump_sessions ps ON ps.run_id=r.id
            LEFT JOIN attendants a ON a.id=ps.attendant_id
            LEFT JOIN pump_run_receipts rr ON rr.run_id=r.id
            LEFT JOIN fuel_receipts fr ON fr.id=rr.receipt_id
            WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
        """
        run_params = [start, end]
        if tank_id is not None:
            run_query += " AND t.id=?"
            run_params.append(tank_id)
        run_query += " GROUP BY ps.id ORDER BY date(ps.session_date),ps.id"
        for item in conn.execute(run_query, run_params):
            details.append((
                "Pump session", item["session_date"], item["product"],
                item["tank_number"], item["receipts"] or "",
                item["pump_number"], item["attendant"] or "",
                f"Run #{item['id']} {item['status']}",
                f"shift {float(item['shift_open'] or 0):,.2f} -> "
                f"{float(item['shift_close'] or 0):,.2f}; run "
                f"{'' if item['opening_meter'] is None else format(float(item['opening_meter']), ',.2f')} -> "
                f"{'' if item['closing_meter'] is None else format(float(item['closing_meter']), ',.2f')}",
                f"RTT {float(item['rtt_litres'] or 0):,.2f} L; "
                f"net sold {float(item['litres_sold'] or 0):,.2f} L; "
                f"sales NGN {float(item['sale_amount'] or 0):,.2f}; "
                f"COGS NGN {float(item['cost_of_goods_sold'] or 0):,.2f}; "
                f"gross profit NGN {float(item['gross_profit'] or 0):,.2f}; "
                f"expenses NGN {float(item['expenses'] or 0):,.2f}; "
                f"short/over NGN "
                f"{adjusted_session_short_over(conn, item['session_id'], item['short_over'], end):+,.2f}",
            ))

        session_filter = "AND t.id=?" if tank_id is not None else ""
        session_params = [end, start, end]
        if tank_id is not None:
            session_params.append(tank_id)
        for item in conn.execute(f"""
            SELECT ps.id,ps.session_date,ps.product,t.tank_number,p.pump_number,
                   a.name AS attendant,MAX(-COALESCE(ps.short_over,0),0) short_amount,
                   COALESCE(SUM(sa.amount),0) reconciled
            FROM pump_sessions ps
            LEFT JOIN pumps p ON p.id=ps.pump_id
            LEFT JOIN tanks t ON t.id=p.tank_id
            LEFT JOIN attendants a ON a.id=ps.attendant_id
            LEFT JOIN attendant_short_allocations sa ON sa.session_id=ps.id
            LEFT JOIN attendant_short_reconciliations sr
              ON sr.id=sa.reconciliation_id
             AND date(sr.recovery_date)<=date(?)
            WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
              {session_filter}
            GROUP BY ps.id
            HAVING MAX(-COALESCE(ps.short_over,0),0)>0
            ORDER BY date(ps.session_date),ps.id
        """, session_params):
            details.append((
                "Attendant short", item["session_date"], item["product"] or "",
                item["tank_number"] or "", f"Session #{item['id']}",
                item["pump_number"] or "", item["attendant"] or "", "",
                f"Short NGN {float(item['short_amount'] or 0):,.2f}; "
                f"deducted NGN {float(item['reconciled'] or 0):,.2f}",
                f"Outstanding NGN {max(float(item['short_amount'] or 0)-float(item['reconciled'] or 0),0):,.2f}",
            ))

        # Preserve cumulative party balances in the appendix as well as receipt
        # settlement entries, so the reporting period does not hide older debt.
        for party_column, party_label in (
            ("supplier_name", "Supplier"),
            ("driver_name", "Driver"),
            ("vehicle_number", "Truck"),
        ):
            party_where = "AND t.id=?" if tank_id is not None else ""
            party_params = [end, end]
            if tank_id is not None:
                party_params.append(tank_id)
            for item in conn.execute(f"""
                WITH per_receipt AS (
                    SELECT fr.id,COALESCE(fr.{party_column},'') party,
                           fr.product,fr.tank_id,fr.receipt_date,
                           MAX(COALESCE(fr.invoice_quantity,0)-
                               COALESCE(fr.quantity_received,0),0) initial_l,
                           MAX(COALESCE(fr.invoice_quantity,0)-
                               COALESCE(fr.quantity_received,0),0)*
                               COALESCE(fr.cost_price,0) initial_cost,
                           COALESCE(SUM(rs.reconciled_litres),0) settled_l,
                           COALESCE(SUM(rs.station_borne_litres),0) station_l,
                           COALESCE(SUM(rs.reconciled_cost),0) settled_cost,
                           COALESCE(SUM(rs.station_borne_cost),0) station_cost,
                           COALESCE(SUM(CASE WHEN rs.disputed=1 THEN 1 ELSE 0 END),0) disputes
                    FROM fuel_receipts fr
                    LEFT JOIN receipt_short_reconciliations rs
                      ON rs.receipt_id=fr.id
                     AND date(rs.settlement_date)<=date(?)
                    WHERE date(fr.receipt_date)<=date(?)
                    GROUP BY fr.id
                )
                SELECT pr.party,pr.product,t.tank_number,
                       COALESCE(SUM(pr.initial_l),0) initial_l,
                       COALESCE(SUM(pr.initial_cost),0) initial_cost,
                       COALESCE(SUM(pr.settled_l),0) settled_l,
                       COALESCE(SUM(pr.station_l),0) station_l,
                       COALESCE(SUM(pr.settled_cost),0) settled_cost,
                       COALESCE(SUM(pr.station_cost),0) station_cost,
                       COALESCE(SUM(pr.disputes),0) disputes
                FROM per_receipt pr JOIN tanks t ON t.id=pr.tank_id
                WHERE 1=1 {party_where}
                  AND trim(pr.party)<>''
                GROUP BY lower(trim(pr.party)),pr.product,t.tank_number
                ORDER BY pr.party,pr.product,t.tank_number
            """, party_params):
                outstanding_l = max(
                    float(item["initial_l"] or 0) -
                    float(item["settled_l"] or 0) -
                    float(item["station_l"] or 0), 0
                )
                outstanding_cost = max(
                    float(item["initial_cost"] or 0) -
                    float(item["settled_cost"] or 0) -
                    float(item["station_cost"] or 0), 0
                )
                if not any((
                    outstanding_l, item["settled_l"], item["station_l"],
                    item["settled_cost"], item["station_cost"], item["disputes"],
                )):
                    continue
                details.append((
                    f"Cumulative {party_label} balance", end,
                    item["product"] or "", item["tank_number"] or "",
                    f"{party_label}: {item['party']}", "", "", "",
                    f"Initial shortage {float(item['initial_l'] or 0):,.2f} L; "
                    f"settled {float(item['settled_l'] or 0):,.2f} L; "
                    f"station-borne {float(item['station_l'] or 0):,.2f} L; "
                    f"outstanding {outstanding_l:,.2f} L; disputes {item['disputes']}",
                    f"Recovered NGN {float(item['settled_cost'] or 0):,.2f}; "
                    f"station loss NGN {float(item['station_cost'] or 0):,.2f}; "
                    f"outstanding NGN {outstanding_cost:,.2f}",
                ))

        expenses = expense_report_rows(conn, start, end)
        for day, source, description, amount in expenses:
            details.append((
                "Expense", day, "", "", source, "", "", "",
                description, f"NGN {amount:,.2f}",
            ))

        return (
            ["Record", "Date", "Product", "Tank", "Receipt / source",
             "Supplier / pump", "Driver / attendant", "Truck / run",
             "Meter / quantities", "Settlement / financial detail"],
            details,
        )
