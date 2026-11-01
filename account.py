"""Bookkeeping helpers for independent cash, POS-terminal and bank ledgers."""

import sqlite3
from datetime import date, datetime


from app_settings import get_active_database

DATABASE = get_active_database()
TRANSACTION_TYPES = (
    "Bank Deposit", "POS Settlement", "Bank Payment / Withdrawal",
    "Opening Cash Balance", "Opening POS Balance", "Opening Bank Balance",
)
LEDGER_TYPES = (
    "Account Receipt", "Cash Count", "Cash Expense", "POS Transaction",
    "Account Expense", "Product Payment",
    "Bank Deposit", "Account Payment / Amount Sent", "Account Transfer",
    "Opening Balance",
)


def ensure_account_schema(conn):
    """Create the account transfer register if it does not exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT NOT NULL,
            account_type TEXT NOT NULL CHECK(account_type IN ('CASH','BANK','POS')),
            account_number TEXT,
            provider TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(account_type, account_name)
        )
    """)
    conn.execute("""
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
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_account_transactions_date_type
        ON account_transactions(transaction_date, transaction_type)
    """)
    transaction_columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(account_transactions)"
    )}
    for column in ("account_id", "target_account_id"):
        if column not in transaction_columns:
            conn.execute(f"ALTER TABLE account_transactions ADD COLUMN {column} INTEGER")
    if "receipt_id" not in transaction_columns:
        conn.execute("ALTER TABLE account_transactions ADD COLUMN receipt_id INTEGER")
    conn.execute("""
        INSERT OR IGNORE INTO accounts(account_name,account_type,provider)
        VALUES ('Station Cash','CASH','Cash')
    """)
    cash_id = conn.execute(
        "SELECT id FROM accounts WHERE account_type='CASH' ORDER BY id LIMIT 1"
    ).fetchone()[0]

    # Convert existing free-text bank/provider labels into named account records.
    legacy_rows = conn.execute("""
        SELECT id, transaction_type, COALESCE(bank_name,'')
        FROM account_transactions WHERE account_id IS NULL
    """).fetchall()
    for transaction_id, transaction_type, label in legacy_rows:
        label = str(label or '').strip()
        if not label:
            continue
        if transaction_type == 'POS Settlement' or transaction_type == 'Opening POS Balance':
            account_type = 'POS'
        elif transaction_type == 'Opening Cash Balance':
            account_type = 'CASH'
        else:
            account_type = 'BANK'
        conn.execute("""
            INSERT OR IGNORE INTO accounts(account_name,account_type,provider)
            VALUES (?,?,?)
        """, (label, account_type, label))
        account_id = conn.execute(
            "SELECT id FROM accounts WHERE account_type=? AND account_name=?",
            (account_type, label),
        ).fetchone()[0]
        if transaction_type == 'Bank Deposit':
            conn.execute("""UPDATE account_transactions
                SET account_id=?,target_account_id=? WHERE id=?""",
                (cash_id, account_id, transaction_id))
        elif transaction_type == 'POS Settlement':
            conn.execute("""UPDATE account_transactions
                SET account_id=? WHERE id=?""", (account_id, transaction_id))
        else:
            conn.execute("""UPDATE account_transactions
                SET account_id=? WHERE id=?""", (account_id, transaction_id))
    conn.execute("""
        UPDATE account_transactions SET account_id=?
        WHERE transaction_type='Opening Cash Balance' AND account_id IS NULL
    """, (cash_id,))
    conn.execute("""
        UPDATE account_transactions SET account_id=?
        WHERE transaction_type='Bank Deposit' AND account_id IS NULL
    """, (cash_id,))


def list_accounts(account_type=None, active_only=False, database=DATABASE):
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        sql = "SELECT id, account_name, account_type, COALESCE(account_number,''), COALESCE(provider,''), is_active FROM accounts"
        conditions = []
        params = []
        if account_type:
            conditions.append("account_type=?")
            params.append(str(account_type).upper())
        if active_only:
            conditions.append("is_active=1")
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY account_type,account_name COLLATE NOCASE"
        return conn.execute(sql, params).fetchall()


def save_account(name, account_type, account_number="", provider="", account_id=None,
                 database=DATABASE):
    name = str(name or "").strip()
    account_type = str(account_type or "").strip().upper()
    if len(name) < 2:
        raise ValueError("Enter an account name with at least 2 characters.")
    if account_type not in ("BANK", "POS"):
        raise ValueError("Choose Bank or POS as the account type.")
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        try:
            if account_id is None:
                conn.execute("""INSERT INTO accounts
                    (account_name,account_type,account_number,provider)
                    VALUES (?,?,?,?)""",
                    (name, account_type, str(account_number).strip(), str(provider).strip()))
            else:
                cursor = conn.execute("""UPDATE accounts SET account_name=?,account_type=?,
                    account_number=?,provider=? WHERE id=? AND account_type<>'CASH'""",
                    (name, account_type, str(account_number).strip(),
                     str(provider).strip(), account_id))
                if cursor.rowcount == 0:
                    raise ValueError("The selected account was not found or cannot be edited.")
        except sqlite3.IntegrityError as error:
            raise ValueError("That account name already exists for this type.") from error


def set_account_active(account_id, active, database=DATABASE):
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        cursor = conn.execute("""UPDATE accounts SET is_active=?
            WHERE id=? AND account_type<>'CASH'""", (1 if active else 0, account_id))
        if cursor.rowcount != 1:
            raise ValueError("The selected account could not be updated.")


def _account_balance(conn, account_id, cutoff):
    account = conn.execute(
        "SELECT account_type FROM accounts WHERE id=?", (account_id,)
    ).fetchone()
    if not account:
        return 0.0
    account_type = account[0]
    count_anchor = None
    if account_type == "CASH":
        count_anchor = conn.execute("""
            SELECT transaction_date,id,amount
            FROM account_transactions
            WHERE account_id=? AND transaction_type='Cash Count'
              AND date(transaction_date)<=date(?)
            ORDER BY date(transaction_date) DESC,id DESC LIMIT 1
        """, (account_id, cutoff)).fetchone()
    if count_anchor:
        balance = float(count_anchor[2] or 0)
        txs = conn.execute("""
            SELECT transaction_type,amount,account_id,target_account_id
            FROM account_transactions
            WHERE date(transaction_date)<=date(?)
              AND (account_id=? OR target_account_id=?)
              AND transaction_type<>'Cash Count'
              AND (date(transaction_date)>date(?)
                   OR (date(transaction_date)=date(?) AND id>?))
        """, (cutoff, account_id, account_id, count_anchor[0],
              count_anchor[0], count_anchor[1])).fetchall()
    else:
        balance = 0.0
        txs = conn.execute("""
            SELECT transaction_type,amount,account_id,target_account_id
            FROM account_transactions
            WHERE date(transaction_date)<=date(?)
              AND (account_id=? OR target_account_id=?)
              AND transaction_type<>'Cash Count'
        """, (cutoff, account_id, account_id)).fetchall()
    for tx_type, amount, source_id, target_id in txs:
        amount = float(amount or 0)
        if tx_type in (
            "Opening Balance", "Opening Cash Balance", "Opening POS Balance",
            "Opening Bank Balance", "Account Receipt", "POS Transaction",
        ):
            balance += amount
        elif tx_type in (
            "Account Payment / Amount Sent", "Bank Payment / Withdrawal",
            "Cash Expense", "Account Expense", "Product Payment",
        ):
            balance -= amount
        elif tx_type in ("Account Transfer", "Bank Deposit", "POS Settlement"):
            if tx_type == "Bank Deposit" and target_id is None:
                balance += amount
            elif target_id == account_id:
                balance += amount
            elif source_id == account_id:
                balance -= amount
    if account_type == "CASH":
        sql = """SELECT COALESCE(SUM(COALESCE(cash_collected,0)),0)
                 FROM pump_sessions WHERE date(session_date)<=date(?)"""
        params = [cutoff]
        if count_anchor:
            sql += " AND date(session_date)>date(?)"
            params.append(count_anchor[0])
        balance += float(conn.execute(sql, params).fetchone()[0] or 0)
    return float(balance)


def named_account_balances(as_of_date=None, database=DATABASE):
    """Return balances from each account's own ledger transactions only."""
    cutoff = _iso_date(as_of_date or date.today().isoformat())
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        accounts = conn.execute("""
            SELECT id,account_name,account_type,COALESCE(account_number,''),
                   COALESCE(provider,''),is_active
            FROM accounts ORDER BY account_type,account_name COLLATE NOCASE
        """).fetchall()
        rows = []
        for account_id, name, account_type, number, provider, active in accounts:
            count_anchor = None
            if account_type == "CASH":
                count_anchor = conn.execute("""SELECT transaction_date,id,amount
                    FROM account_transactions WHERE account_id=?
                    AND transaction_type='Cash Count'
                    AND date(transaction_date)<=date(?)
                    ORDER BY date(transaction_date) DESC,id DESC LIMIT 1""",
                    (account_id, cutoff)).fetchone()
            if count_anchor:
                balance = float(count_anchor[2] or 0)
                txs = conn.execute("""SELECT transaction_type,amount,account_id,
                        target_account_id,id,transaction_date
                    FROM account_transactions WHERE date(transaction_date)<=date(?)
                      AND (account_id=? OR target_account_id=?)
                      AND transaction_type<>'Cash Count'
                      AND (date(transaction_date)>date(?)
                           OR (date(transaction_date)=date(?) AND id>?))""",
                    (cutoff, account_id, account_id, count_anchor[0],
                     count_anchor[0], count_anchor[1])).fetchall()
            else:
                balance = 0.0
                txs = conn.execute("""SELECT transaction_type,amount,account_id,
                        target_account_id,id,transaction_date
                    FROM account_transactions WHERE date(transaction_date)<=date(?)
                      AND (account_id=? OR target_account_id=?)
                      AND transaction_type<>'Cash Count'""",
                    (cutoff, account_id, account_id)).fetchall()
            for tx_type, amount, source_id, target_id, _tx_id, _tx_date in txs:
                amount = float(amount or 0)
                if tx_type in ("Opening Balance", "Opening Cash Balance",
                               "Opening POS Balance", "Opening Bank Balance",
                               "Account Receipt", "POS Transaction"):
                    balance += amount
                elif tx_type in ("Account Payment / Amount Sent",
                                 "Bank Payment / Withdrawal", "Cash Expense",
                                 "Account Expense",
                                 "Product Payment"):
                    balance -= amount
                elif tx_type in ("Account Transfer", "Bank Deposit", "POS Settlement"):
                    if tx_type == "Bank Deposit" and target_id is None:
                        balance += amount
                    elif target_id == account_id:
                        balance += amount
                    elif source_id == account_id:
                        balance -= amount
            # Pump-session cash is a real inflow to the station vault. A cash
            # count is an end-of-day snapshot, so sessions on/before its date
            # are already represented by that snapshot and must not be added
            # again. POS session amounts remain reconciled through POS entries.
            if account_type == "CASH":
                session_sql = """SELECT COALESCE(SUM(COALESCE(cash_collected,0)),0)
                    FROM pump_sessions WHERE date(session_date)<=date(?)"""
                session_params = [cutoff]
                if count_anchor:
                    session_sql += " AND date(session_date)>date(?)"
                    session_params.append(count_anchor[0])
                balance += float(conn.execute(session_sql, session_params).fetchone()[0] or 0)
            rows.append((account_id, name, account_type, number, provider,
                         float(balance or 0), bool(active)))
    return rows


def _iso_date(value):
    try:
        return datetime.strptime(str(value).strip(), "%Y-%m-%d").date().isoformat()
    except ValueError as error:
        raise ValueError("Date must be YYYY-MM-DD.") from error


def _receipt_product_payable(conn, receipt_id):
    receipt = conn.execute(
        "SELECT COALESCE(total_cost,0) FROM fuel_receipts WHERE id=?",
        (receipt_id,),
    ).fetchone()
    if not receipt:
        raise ValueError("The selected fuel receipt was not found.")
    has_reconciliation = conn.execute("""
        SELECT 1 FROM sqlite_master
        WHERE type='table' AND name='receipt_short_reconciliations'
    """).fetchone()
    station_cost = 0.0
    if has_reconciliation:
        station_cost = conn.execute("""
            SELECT COALESCE(SUM(station_borne_cost),0)
            FROM receipt_short_reconciliations WHERE receipt_id=?
        """, (receipt_id,)).fetchone()[0]
    return float(receipt[0] or 0) + float(station_cost or 0)


def record_transfer(transaction_type, amount, transaction_date=None,
                    bank_name="", reference="", description="",
                    database=DATABASE, account_id=None, target_account_id=None,
                    receipt_id=None):
    """Record an independent account transaction or a transfer between ledgers."""
    if transaction_type not in LEDGER_TYPES:
        raise ValueError("Choose a valid account transaction type.")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid amount.") from error
    if amount < 0 or (amount == 0 and transaction_type != "Cash Count"):
        raise ValueError("Amount must be greater than zero.")
    transaction_date = _iso_date(transaction_date or date.today().isoformat())
    narration = str(reference or description or "").strip()
    if transaction_type in (
        "Account Transfer", "Account Payment / Amount Sent", "Product Payment",
        "Account Expense",
    ) and not narration:
        raise ValueError("Enter the beneficiary and narration for this outflow.")
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        accounts = {r[0]: r for r in conn.execute(
            "SELECT id,account_name,account_type,is_active FROM accounts").fetchall()}
        if transaction_type in ("Account Transfer", "Bank Deposit"):
            source = accounts.get(int(account_id or 0))
            target = accounts.get(int(target_account_id or 0))
            if not source or not target or source[0] == target[0]:
                raise ValueError("Choose two different accounts for the transfer.")
            if not source[3] or not target[3]:
                raise ValueError("Both selected accounts must be active.")
            if (transaction_type == "Bank Deposit"
                    and (source[2] != "CASH" or target[2] != "BANK")):
                raise ValueError("A bank deposit must move money from Station Cash to a bank account.")
            source_id, target_id = source[0], target[0]
            label = f"{source[1]} -> {target[1]}"
            current = _account_balance(conn, source_id, transaction_date)
            if amount > current + 0.00001:
                raise ValueError(f"Amount exceeds the source account balance of {current:,.2f}.")
        else:
            account = accounts.get(int(account_id or 0))
            if not account or not account[3]:
                raise ValueError("Select an active account.")
            source_id, target_id = account[0], None
            label = account[1]
            if transaction_type == "POS Transaction" and account[2] != "POS":
                raise ValueError("Select a POS account for a POS Transaction.")
            if transaction_type == "Product Payment":
                if receipt_id is None:
                    raise ValueError("Select the fuel receipt this product payment covers.")
                product_payable = _receipt_product_payable(conn, receipt_id)
                already_paid = conn.execute("""
                    SELECT COALESCE(SUM(amount),0)
                    FROM account_transactions
                    WHERE transaction_type='Product Payment' AND receipt_id=?
                """, (receipt_id,)).fetchone()[0]
                balance_due = max(product_payable - float(already_paid or 0), 0)
                if amount > balance_due + 0.005:
                    raise ValueError(
                        f"Payment exceeds the receipt balance due of ₦{balance_due:,.2f}."
                    )
            if transaction_type == "Cash Count" and account[2] != "CASH":
                raise ValueError("Select Station Cash for a cash count or cash expense.")
            if transaction_type == "Cash Expense" and account[2] != "CASH":
                raise ValueError("Cash Expense must be posted to the Cash Vault.")
            if transaction_type == "Account Expense" and account[2] == "CASH":
                raise ValueError("Choose Cash Expense for expenses paid from the Cash Vault.")
            if transaction_type == "Account Receipt" and account[2] != "CASH":
                raise ValueError("Select Station Cash for an actual vault cash receipt.")
            if transaction_type == "Account Payment / Amount Sent" and account[2] not in ("BANK", "POS", "CASH"):
                raise ValueError("Select a Cash Vault, POS, or bank account for the payment.")
            if transaction_type == "Opening Balance":
                prior = conn.execute("""SELECT COUNT(*) FROM account_transactions
                    WHERE account_id=? AND transaction_type='Opening Balance'""",
                    (source_id,)).fetchone()[0]
                if prior:
                    raise ValueError("This account already has an opening balance recorded.")
            if transaction_type in (
                "Account Payment / Amount Sent", "Product Payment", "Account Expense"
            ):
                current = _account_balance(conn, source_id, transaction_date)
                if amount > current + 0.00001:
                    raise ValueError(f"Amount exceeds the selected source account balance of {current:,.2f}.")
        conn.execute("""INSERT INTO account_transactions
            (transaction_date,transaction_type,amount,bank_name,reference,
             description,account_id,target_account_id,receipt_id)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (transaction_date, transaction_type, amount, label,
             narration, str(description).strip(), source_id, target_id,
             receipt_id if transaction_type == "Product Payment" else None))


def update_account_transaction(transaction_id, transaction_date, amount,
                               reference="", database=DATABASE):
    """Update the date, amount and reference of an existing ledger transaction."""
    transaction_date = _iso_date(transaction_date)
    try:
        amount = float(amount)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid amount.") from error
    if amount < 0:
        raise ValueError("Amount cannot be negative.")

    reference = str(reference or "").strip()
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_account_schema(conn)
        row = conn.execute("""
            SELECT transaction_date,transaction_type,amount,account_id,
                   target_account_id,receipt_id
            FROM account_transactions WHERE id=?
        """, (transaction_id,)).fetchone()
        if not row:
            raise ValueError("The selected transaction no longer exists.")
        old_date, transaction_type, old_amount, account_id, target_id, receipt_id = row
        if amount == 0 and transaction_type != "Cash Count":
            raise ValueError("Amount must be greater than zero.")

        old_transaction_in_balance = (
            date.fromisoformat(str(old_date)[:10])
            <= date.fromisoformat(transaction_date)
        )
        account = conn.execute(
            "SELECT account_type FROM accounts WHERE id=?", (account_id,)
        ).fetchone()
        if old_transaction_in_balance and account and account[0] == "CASH":
            count_anchor = conn.execute("""
                SELECT transaction_date,id FROM account_transactions
                WHERE account_id=? AND transaction_type='Cash Count'
                  AND date(transaction_date)<=date(?)
                ORDER BY date(transaction_date) DESC,id DESC LIMIT 1
            """, (account_id, transaction_date)).fetchone()
            if count_anchor:
                old_transaction_in_balance = (
                    date.fromisoformat(str(old_date)[:10])
                    > date.fromisoformat(str(count_anchor[0])[:10])
                    or (
                        str(old_date)[:10] == str(count_anchor[0])[:10]
                        and transaction_id > count_anchor[1]
                    )
                )

        if transaction_type in (
            "Account Payment / Amount Sent", "Product Payment",
            "Account Expense", "Cash Expense", "Bank Payment / Withdrawal",
        ):
            balance = _account_balance(conn, account_id, transaction_date)
            if old_transaction_in_balance:
                balance += float(old_amount or 0)
            if amount > balance + 0.00001:
                raise ValueError(
                    f"Amount exceeds the selected account balance of ₦{balance:,.2f}."
                )
        elif transaction_type in ("Account Transfer", "Bank Deposit"):
            is_outflow = target_id is not None
            if is_outflow:
                balance = _account_balance(conn, account_id, transaction_date)
                if old_transaction_in_balance:
                    balance += float(old_amount or 0)
                if amount > balance + 0.00001:
                    raise ValueError(
                        f"Amount exceeds the source account balance of ₦{balance:,.2f}."
                    )

        if transaction_type == "Product Payment" and receipt_id is not None:
            product_payable = _receipt_product_payable(conn, receipt_id)
            already_paid = conn.execute("""
                SELECT COALESCE(SUM(amount),0) FROM account_transactions
                WHERE transaction_type='Product Payment' AND receipt_id=? AND id<>?
            """, (receipt_id, transaction_id)).fetchone()[0]
            due = max(product_payable - float(already_paid or 0), 0)
            if amount > due + 0.005:
                raise ValueError(
                    f"Payment exceeds the receipt balance due of ₦{due:,.2f}."
                )

        conn.execute("""
            UPDATE account_transactions
            SET transaction_date=?,amount=?,reference=?
            WHERE id=?
        """, (transaction_date, amount, reference, transaction_id))

        _ensure_expense_account_columns(conn)
        conn.execute("""
            UPDATE expenses
            SET expense_date=?,amount=?,description=?
            WHERE account_transaction_id=?
        """, (transaction_date, amount, reference, transaction_id))


def delete_account_transaction(transaction_id, database=DATABASE):
    """Delete an account transaction and any standalone expense linked to it."""
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_account_schema(conn)
        _ensure_expense_account_columns(conn)
        cursor = conn.execute(
            "DELETE FROM account_transactions WHERE id=?", (transaction_id,)
        )
        if cursor.rowcount != 1:
            raise ValueError("The selected transaction no longer exists.")
        conn.execute(
            "DELETE FROM expenses WHERE account_transaction_id=?",
            (transaction_id,),
        )


def _ensure_expense_account_columns(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            expense_date TEXT NOT NULL
        )
    """)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(expenses)")}
    if "source_account_id" not in columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN source_account_id INTEGER")
    if "account_transaction_id" not in columns:
        conn.execute("ALTER TABLE expenses ADD COLUMN account_transaction_id INTEGER")


def save_standalone_account_expense(description, amount, expense_date,
                                    account_id, database=DATABASE,
                                    expense_id=None):
    """Save an expense and its account outflow together, without double-entry."""
    description = str(description or "").strip()
    if not description:
        raise ValueError("Enter an expense description.")
    try:
        amount = float(amount)
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid expense amount.") from error
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    expense_date = _iso_date(expense_date)

    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_account_schema(conn)
        _ensure_expense_account_columns(conn)
        account = conn.execute("""
            SELECT id,account_name,account_type,is_active
            FROM accounts WHERE id=?
        """, (account_id,)).fetchone()
        if not account or not account[3]:
            raise ValueError("Select an active cash vault, POS, or bank account.")
        transaction_type = "Cash Expense" if account[2] == "CASH" else "Account Expense"

        linked_transaction = None
        old_transaction = None
        if expense_id is not None:
            row = conn.execute("""
                SELECT account_transaction_id FROM expenses WHERE id=?
            """, (expense_id,)).fetchone()
            if not row:
                raise ValueError("The selected expense no longer exists.")
            linked_transaction = row[0]
            if linked_transaction is not None:
                old_transaction = conn.execute("""
                    SELECT amount,account_id,transaction_date
                    FROM account_transactions WHERE id=?
                """, (linked_transaction,)).fetchone()
        balance = _account_balance(conn, account[0], expense_date)
        if (old_transaction and old_transaction[1] == account[0]
                and date.fromisoformat(str(old_transaction[2])[:10])
                <= date.fromisoformat(expense_date)):
            balance += float(old_transaction[0] or 0)
        if amount > balance + 0.00001:
            raise ValueError(
                f"Amount exceeds the selected account balance of ₦{balance:,.2f}."
            )
        if linked_transaction is not None:
            conn.execute("""
                UPDATE account_transactions
                SET transaction_date=?,transaction_type=?,amount=?,bank_name=?,
                    reference=?,account_id=?,target_account_id=NULL,receipt_id=NULL
                WHERE id=?
            """, (expense_date, transaction_type, amount, account[1],
                  description, account[0], linked_transaction))
            conn.execute("""
                UPDATE expenses SET description=?,amount=?,expense_date=?,
                    source_account_id=?
                WHERE id=?
            """, (description, amount, expense_date, account[0], expense_id))
            return expense_id

        cursor = conn.execute("""
            INSERT INTO account_transactions(
                transaction_date,transaction_type,amount,bank_name,reference,
                description,account_id
            ) VALUES (?,?,?,?,?,?,?)
        """, (expense_date, transaction_type, amount, account[1],
              description, "Standalone expense", account[0]))
        transaction_id = cursor.lastrowid
        if expense_id is not None:
            conn.execute("""
                UPDATE expenses SET description=?,amount=?,expense_date=?,
                    source_account_id=?,account_transaction_id=?
                WHERE id=?
            """, (description, amount, expense_date, account[0], transaction_id,
                  expense_id))
            return expense_id
        cursor = conn.execute("""
            INSERT INTO expenses(
                description,amount,expense_date,source_account_id,
                account_transaction_id
            ) VALUES (?,?,?,?,?)
        """, (description, amount, expense_date, account[0], transaction_id))
        return cursor.lastrowid


def delete_standalone_account_expense(expense_id, database=DATABASE):
    with sqlite3.connect(database, timeout=15) as conn:
        conn.execute("BEGIN IMMEDIATE")
        ensure_account_schema(conn)
        _ensure_expense_account_columns(conn)
        row = conn.execute("""
            SELECT account_transaction_id FROM expenses WHERE id=?
        """, (expense_id,)).fetchone()
        if not row:
            raise ValueError("The selected expense no longer exists.")
        if row[0] is not None:
            conn.execute("DELETE FROM account_transactions WHERE id=?", (row[0],))
        conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,))


def daily_cash_pos_reconciliation(start_date, end_date, database=DATABASE):
    """Reconcile session expectations, vault counts, POS and bank movements.

    The latest Cash Count for a sales date is the physical amount counted in
    the vault. Cash Expense entries explain differences outside session
    expenses. Cash and POS remain pending until moved to a bank for that date.
    """
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    if start > end:
        raise ValueError("Start date must be on or before end date.")

    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        sessions = conn.execute("""
            SELECT date(session_date),
                   COALESCE(SUM(COALESCE(cash_collected,0)),0),
                   COALESCE(SUM(COALESCE(pos_amount,0)),0)
            FROM pump_sessions
            WHERE date(session_date) BETWEEN date(?) AND date(?)
            GROUP BY date(session_date)
        """, (start, end)).fetchall()
        has_attendant_allocations = conn.execute("""
            SELECT COUNT(*)=2 FROM sqlite_master
            WHERE type='table' AND name IN (
                'attendant_short_allocations',
                'attendant_short_reconciliations'
            )
        """).fetchone()[0]
        if has_attendant_allocations:
            attendant_short_rows = conn.execute("""
                SELECT date(ps.session_date),
                       CASE
                           WHEN COALESCE(ps.short_over,0)<0 THEN MIN(
                               COALESCE(ps.short_over,0)+COALESCE((
                                   SELECT SUM(sa.amount)
                                   FROM attendant_short_allocations AS sa
                                   JOIN attendant_short_reconciliations AS r
                                     ON r.id=sa.reconciliation_id
                                   WHERE sa.session_id=ps.id
                                     AND date(r.recovery_date)<=date(ps.session_date)
                               ),0),
                               0
                           )
                           ELSE COALESCE(ps.short_over,0)
                       END
                FROM pump_sessions AS ps
                WHERE date(ps.session_date) BETWEEN date(?) AND date(?)
            """, (start, end)).fetchall()
        else:
            attendant_short_rows = conn.execute("""
                SELECT date(session_date),COALESCE(short_over,0)
                FROM pump_sessions
                WHERE date(session_date) BETWEEN date(?) AND date(?)
            """, (start, end)).fetchall()
        account_activity = conn.execute("""
            SELECT date(t.transaction_date),
                   COALESCE(SUM(CASE WHEN t.transaction_type='Cash Expense'
                         AND source.account_type='CASH' THEN t.amount ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN t.transaction_type='POS Transaction'
                         AND source.account_type='POS' THEN t.amount ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN
                         (t.transaction_type IN (
                             'Bank Deposit','Account Transfer',
                             'Account Payment / Amount Sent','Product Payment'
                          )
                          AND source.account_type='CASH')
                         THEN t.amount ELSE 0 END),0),
                   COALESCE(SUM(CASE WHEN
                         (t.transaction_type IN (
                             'POS Settlement','Account Transfer',
                             'Account Payment / Amount Sent','Account Expense',
                             'Product Payment'
                          ) AND source.account_type='POS')
                         THEN t.amount ELSE 0 END),0)
            FROM account_transactions AS t
            LEFT JOIN accounts AS source ON source.id=t.account_id
            LEFT JOIN accounts AS target ON target.id=t.target_account_id
            WHERE date(t.transaction_date) BETWEEN date(?) AND date(?)
            GROUP BY date(t.transaction_date)
        """, (start, end)).fetchall()
        cash_counts = conn.execute("""
            SELECT date(t.transaction_date),t.amount
            FROM account_transactions AS t
            JOIN accounts AS a ON a.id=t.account_id
            WHERE t.transaction_type='Cash Count' AND a.account_type='CASH'
              AND date(t.transaction_date) BETWEEN date(?) AND date(?)
              AND t.id=(SELECT MAX(latest.id) FROM account_transactions AS latest
                        WHERE latest.account_id=t.account_id
                          AND latest.transaction_type='Cash Count'
                          AND date(latest.transaction_date)=date(t.transaction_date))
        """, (start, end)).fetchall()
        bank_destinations = conn.execute("""
            SELECT DISTINCT date(t.transaction_date),t.target_account_id
            FROM account_transactions AS t
            JOIN accounts AS source ON source.id=t.account_id
            JOIN accounts AS target ON target.id=t.target_account_id
            WHERE date(t.transaction_date) BETWEEN date(?) AND date(?)
              AND target.account_type='BANK'
              AND source.account_type IN ('CASH','POS')
              AND t.transaction_type IN (
                  'Bank Deposit','Account Transfer','POS Settlement'
              )
        """, (start, end)).fetchall()
        bank_balance_by_date = {}
        for day, bank_id in bank_destinations:
            bank_balance_by_date.setdefault(day, 0.0)
            bank_balance_by_date[day] += _account_balance(conn, bank_id, day)

    expected_by_date = {
        row[0]: (float(row[1] or 0), float(row[2] or 0))
        for row in sessions if row[0]
    }
    activity_by_date = {
        row[0]: (float(row[1] or 0), float(row[2] or 0),
                 float(row[3] or 0), float(row[4] or 0))
        for row in account_activity if row[0]
    }
    cash_count_by_date = {
        row[0]: float(row[1] or 0) for row in cash_counts if row[0]
    }
    attendant_remaining_by_date = {}
    for day, outstanding in attendant_short_rows:
        attendant_remaining_by_date[day] = (
            attendant_remaining_by_date.get(day, 0.0)
            + float(outstanding or 0)
        )
    results = []
    for day in sorted(set(expected_by_date) | set(activity_by_date)
                      | set(cash_count_by_date), reverse=True):
        session_cash, expected_pos = expected_by_date.get(
            day, (0.0, 0.0)
        )
        net_expected_cash = session_cash
        cash_expenses, pos_entered, cash_moved, pos_moved = activity_by_date.get(
            day, (0.0, 0.0, 0.0, 0.0)
        )
        cash_count = cash_count_by_date.get(day)
        net_cash_available = net_expected_cash - cash_expenses
        cash_available = (cash_count if cash_count is not None
                          else max(net_cash_available, 0.0))
        cash_pending = max(cash_available - cash_moved, 0.0)
        pos_pending = max(pos_entered - pos_moved, 0.0)
        overall_expected = net_cash_available + expected_pos
        moved_total = cash_moved + pos_moved
        bank_balance = bank_balance_by_date.get(day)
        actual_is_known = cash_count is not None or bank_balance is not None
        overall_actual = (
            cash_available + pos_entered - moved_total
            + (bank_balance or 0.0)
            if actual_is_known else None
        )
        count_difference = (
            overall_actual - overall_expected
            if overall_actual is not None else None
        )
        moved_difference = moved_total - overall_expected
        if (abs(moved_difference) <= 0.01
                or (count_difference is not None
                    and abs(count_difference) <= 0.01)):
            overall_difference = 0.0
            status = "BALANCED"
        else:
            overall_difference = (
                count_difference
                if count_difference is not None else moved_difference
            )
            if overall_difference < -0.01:
                status = "SHORT"
            elif overall_difference > 0.01:
                status = "OVER"
            else:
                status = "BALANCED"
        results.append((
            day, session_cash + expected_pos, cash_expenses,
            net_cash_available + expected_pos, cash_count, pos_entered,
            overall_actual, overall_difference, moved_total,
            attendant_remaining_by_date.get(day, 0.0), status
        ))
    return results

def get_balances(as_of_date=None, database=DATABASE):
    """Summarize the independent account books; pump sessions are not included."""
    cutoff = _iso_date(as_of_date or date.today().isoformat())
    accounts = named_account_balances(cutoff, database)
    grouped = {"CASH": 0.0, "POS": 0.0, "BANK": 0.0}
    for row in accounts:
        grouped[row[2]] = grouped.get(row[2], 0.0) + row[5]
    return {
        "as_of_date": cutoff,
        "cash_received": 0.0,
        "pos_received": 0.0,
        "cash_deposits": 0.0,
        "pos_settlements": 0.0,
        "cash_balance": grouped["CASH"],
        "pos_balance": grouped["POS"],
        "bank_balance": grouped["BANK"],
        "bank_balances": {r[1]: r[5] for r in accounts if r[2] == "BANK"},
        "bank_outflows": 0.0,
        "session_expenses": 0.0,
        "account_balances": accounts,
    }

def get_period_activity(start_date, end_date, database=DATABASE):
    """Return activity recorded directly in account ledgers for a date range."""
    start = _iso_date(start_date)
    end = _iso_date(end_date)
    if start > end:
        raise ValueError("Start date must be on or before end date.")
    with sqlite3.connect(database, timeout=15) as conn:
        ensure_account_schema(conn)
        rows = conn.execute("""SELECT transaction_type,COALESCE(SUM(amount),0)
            FROM account_transactions
            WHERE date(transaction_date) BETWEEN date(?) AND date(?)
            GROUP BY transaction_type""", (start, end)).fetchall()
    activity = {"cash_received": 0.0, "pos_received": 0.0,
                "cash_deposits": 0.0, "pos_settlements": 0.0}
    for typ, amount in rows:
        if typ in ("Account Receipt", "Opening Balance"):
            activity["cash_received"] += float(amount or 0)
        elif typ == "Cash Expense":
            activity.setdefault("cash_expenses", 0.0)
            activity["cash_expenses"] += float(amount or 0)
        elif typ == "POS Transaction":
            activity["pos_received"] += float(amount or 0)
        elif typ == "Bank Deposit":
            activity["cash_deposits"] += float(amount or 0)
        elif typ == "POS Settlement":
            activity["pos_settlements"] += float(amount or 0)
    return activity
