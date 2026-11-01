"""Monthly attendant salary calculations and auditable payout history."""

import calendar
import math
import sqlite3
from datetime import date, timedelta

from short_reconciliation import (
    attendant_short_balances, ensure_reconciliation_schema,
)


def ensure_payroll_schema(conn):
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(attendants)")
    }
    if "monthly_salary" not in columns:
        conn.execute(
            "ALTER TABLE attendants ADD COLUMN monthly_salary REAL NOT NULL DEFAULT 0"
        )
    if "salary_payday_day" not in columns:
        conn.execute(
            "ALTER TABLE attendants ADD COLUMN salary_payday_day INTEGER"
        )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendant_salary_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attendant_id INTEGER NOT NULL,
            payday TEXT NOT NULL,
            paid_date TEXT NOT NULL,
            base_salary REAL NOT NULL,
            short_deduction REAL NOT NULL DEFAULT 0,
            overage_offset REAL NOT NULL DEFAULT 0,
            overage_credit REAL NOT NULL DEFAULT 0,
            net_salary REAL NOT NULL,
            notes TEXT,
            UNIQUE(attendant_id,payday)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attendant_salary_overage_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payment_id INTEGER NOT NULL,
            session_id INTEGER NOT NULL,
            allocation_type TEXT NOT NULL
                CHECK(allocation_type IN ('SHORT_OFFSET','SALARY_CREDIT')),
            amount REAL NOT NULL
        )
    """)


def _scheduled_day(year, month, payday_day):
    final_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(payday_day, final_day))


def _next_month(year, month):
    return (year + 1, 1) if month == 12 else (year, month + 1)


def salary_preview(conn, attendant_id, as_of=None):
    ensure_payroll_schema(conn)
    ensure_reconciliation_schema(conn)
    as_of = as_of or date.today()
    attendant = conn.execute("""
        SELECT name,COALESCE(date_joined,''),COALESCE(monthly_salary,0),
               salary_payday_day
        FROM attendants WHERE id=?
    """, (attendant_id,)).fetchone()
    if not attendant:
        raise ValueError("The selected attendant could not be found.")
    name, date_joined, base_salary, payday_day = attendant
    if payday_day is None or not 1 <= int(payday_day) <= 31:
        raise ValueError("Set a valid monthly salary payday (1-31) first.")
    base_salary = float(base_salary or 0)
    if not math.isfinite(base_salary) or base_salary < 0:
        raise ValueError("Monthly salary must be a valid non-negative amount.")

    last_payment = conn.execute("""
        SELECT payday FROM attendant_salary_payments
        WHERE attendant_id=? ORDER BY date(payday) DESC,id DESC LIMIT 1
    """, (attendant_id,)).fetchone()
    if last_payment:
        last_payday = date.fromisoformat(last_payment[0])
        year, month = _next_month(last_payday.year, last_payday.month)
        payday = _scheduled_day(year, month, int(payday_day))
        period_start = last_payday + timedelta(days=1)
    else:
        payday = _scheduled_day(as_of.year, as_of.month, int(payday_day))
        period_start = (
            date.fromisoformat(date_joined[:10])
            if date_joined else date.min
        )
        last_payday = None

    sessions = conn.execute("""
        SELECT id,session_date,COALESCE(short_over,0)
        FROM pump_sessions
        WHERE attendant_id=? AND date(session_date)<=date(?)
        ORDER BY date(session_date),id
    """, (attendant_id, as_of.isoformat())).fetchall()
    balances = {
        row[0]: row[3] for row in attendant_short_balances(conn, attendant_id)
    }
    outstanding_short = sum(
        balances.get(session_id, 0.0)
        for session_id, session_date, _amount in sessions
        if session_date and date.fromisoformat(session_date[:10]) <= as_of
    )

    overage_sessions = conn.execute("""
        SELECT ps.id,ps.session_date,
               MAX(COALESCE(ps.short_over,0),0) -
               COALESCE((
                   SELECT SUM(a.amount)
                   FROM attendant_salary_overage_allocations a
                   JOIN attendant_salary_payments p ON p.id=a.payment_id
                   WHERE a.session_id=ps.id AND date(p.paid_date)<=date(?)
               ),0) AS available
        FROM pump_sessions ps
        WHERE ps.attendant_id=? AND COALESCE(ps.short_over,0)>0
          AND date(ps.session_date)<=date(?)
        ORDER BY date(ps.session_date),ps.id
    """, (as_of.isoformat(), attendant_id, as_of.isoformat())).fetchall()
    available_overages = [
        (session_id, max(float(amount or 0), 0))
        for session_id, session_date, amount in overage_sessions
        if session_date and
        date.fromisoformat(session_date[:10]) >= period_start and amount
    ]
    overage_total = sum(amount for _session_id, amount in available_overages)
    offset = min(outstanding_short, overage_total)
    short_after_offset = outstanding_short - offset
    salary_deduction = min(base_salary, short_after_offset)
    overage_credit = overage_total - offset
    net_salary = max(base_salary - salary_deduction + overage_credit, 0)
    return {
        "name": name,
        "base_salary": base_salary,
        "payday": payday,
        "period_start": period_start,
        "period_end": payday,
        "is_due": payday <= as_of,
        "outstanding_short": outstanding_short,
        "overage_total": overage_total,
        "overage_offset": offset,
        "short_deduction": salary_deduction,
        "overage_credit": overage_credit,
        "net_salary": net_salary,
        "overage_sessions": available_overages,
    }


def _record_short_reduction(conn, attendant_id, amount, payday, notes):
    if amount <= 0.005:
        return
    balances = attendant_short_balances(conn, attendant_id)
    outstanding = sum(row[3] for row in balances)
    if amount > outstanding + 0.005:
        raise ValueError("Outstanding shorts changed while processing salary.")
    cursor = conn.execute("""
        INSERT INTO attendant_short_reconciliations(
            attendant_id,reduced_amount,recovered_amount,recovery_date,notes
        ) VALUES (?,?,0,?,?)
    """, (attendant_id, amount, payday.isoformat(), notes))
    reconciliation_id = cursor.lastrowid
    remaining = amount
    for session_id, _day, _recorded, session_outstanding in balances:
        if remaining <= 0.005:
            break
        allocated = min(remaining, session_outstanding)
        if allocated > 0:
            conn.execute("""
                INSERT INTO attendant_short_allocations(
                    reconciliation_id,session_id,amount
                ) VALUES (?,?,?)
            """, (reconciliation_id, session_id, allocated))
            remaining -= allocated


def process_salary_payment(database, attendant_id, notes=""):
    today = date.today()
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        preview = salary_preview(conn, attendant_id, today)
        if not preview["is_due"]:
            raise ValueError(
                f"Salary is not due until {preview['payday'].strftime('%d-%m-%Y')}."
            )
        payment_id = conn.execute("""
            INSERT INTO attendant_salary_payments(
                attendant_id,payday,paid_date,base_salary,short_deduction,
                overage_offset,overage_credit,net_salary,notes
            ) VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            attendant_id, preview["payday"].isoformat(), today.isoformat(),
            preview["base_salary"], preview["short_deduction"],
            preview["overage_offset"], preview["overage_credit"],
            preview["net_salary"], str(notes or "").strip(),
        )).lastrowid

        _record_short_reduction(
            conn, attendant_id, preview["overage_offset"],
            preview["payday"], "Offset by session overage at salary payout."
        )
        _record_short_reduction(
            conn, attendant_id, preview["short_deduction"],
            preview["payday"], "Deducted from salary at monthly payout."
        )

        offset_remaining = preview["overage_offset"]
        offset_allocations = {}
        for session_id, available in preview["overage_sessions"]:
            if offset_remaining <= 0.005:
                break
            offset = min(offset_remaining, available)
            if offset:
                conn.execute("""
                    INSERT INTO attendant_salary_overage_allocations(
                        payment_id,session_id,allocation_type,amount
                    ) VALUES (?,?,'SHORT_OFFSET',?)
                """, (payment_id, session_id, offset))
                offset_allocations[session_id] = offset
                offset_remaining -= offset
        credit_remaining = preview["overage_credit"]
        for session_id, available in preview["overage_sessions"]:
            if credit_remaining <= 0.005:
                break
            remaining_from_session = (
                available - offset_allocations.get(session_id, 0.0)
            )
            credit = min(credit_remaining, remaining_from_session)
            if credit:
                conn.execute("""
                    INSERT INTO attendant_salary_overage_allocations(
                        payment_id,session_id,allocation_type,amount
                    ) VALUES (?,?,'SALARY_CREDIT',?)
                """, (payment_id, session_id, credit))
                credit_remaining -= credit
        if offset_remaining > 0.005 or credit_remaining > 0.005:
            raise ValueError(
                "Session overage balances changed while processing salary."
            )
        return preview
