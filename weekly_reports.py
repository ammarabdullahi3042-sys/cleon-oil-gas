"""Product-finished report email using externally configured SMTP."""

import os
import re
import smtplib
import sqlite3
import tempfile
import threading
import ssl
from datetime import date
from email.message import EmailMessage
from pathlib import Path

from app_settings import ensure_app_settings
from report_data import product_delivery_detail, product_delivery_report


MAIL_ENVIRONMENT_KEYS = ("CLEON_SMTP_HOST", "CLEON_SMTP_PORT")


def _valid_recipient(recipient):
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", str(recipient or "").strip()))


def _smtp_configuration(sender=None):
    required = {
        key: os.environ.get(key, "").strip()
        for key in MAIL_ENVIRONMENT_KEYS
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Mail delivery is not configured. Set " + ", ".join(missing) +
            " in the application environment."
        )
    try:
        port = int(os.environ["CLEON_SMTP_PORT"])
    except ValueError as error:
        raise ValueError("CLEON_SMTP_PORT must be a valid port number.") from error
    if not 1 <= port <= 65535:
        raise ValueError("CLEON_SMTP_PORT must be between 1 and 65535.")
    username = os.environ.get("CLEON_SMTP_USERNAME", "").strip()
    password = os.environ.get("CLEON_SMTP_PASSWORD", "")
    configured_sender = str(
        sender or os.environ.get("CLEON_SMTP_SENDER", "")
    ).strip()
    if not _valid_recipient(configured_sender):
        raise ValueError(
            "Set a valid product-finished report sender address in Report Center settings."
        )
    if bool(username) != bool(password):
        raise ValueError(
            "Set both CLEON_SMTP_USERNAME and CLEON_SMTP_PASSWORD, or neither."
        )
    return {
        "host": required["CLEON_SMTP_HOST"],
        "port": port,
        "sender": configured_sender,
        "username": username,
        "password": password,
        "ssl": os.environ.get("CLEON_SMTP_USE_SSL", "").strip().lower()
                in ("1", "true", "yes"),
    }


def product_finished_email_settings(database):
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        values = dict(conn.execute("""
            SELECT preference_key,preference_value
            FROM app_preferences
            WHERE preference_key IN (
                'product_finished_email_sender',
                'product_finished_email_recipient',
                'product_finished_email_enabled',
                'product_finished_email_status'
            )
        """).fetchall())
    return (
        values.get("product_finished_email_sender", "ammarabdullahi3042@gmail.com"),
        values.get("product_finished_email_recipient", "cleonoilandgas@gmail.com"),
        values.get("product_finished_email_enabled", "1") == "1",
        values.get("product_finished_email_status", "Product-finished email is enabled."),
    )


def save_product_finished_email_settings(database, sender, recipient, enabled):
    sender = str(sender or "").strip()
    recipient = str(recipient or "").strip()
    if not _valid_recipient(sender):
        raise ValueError("Enter a valid sender email address.")
    if not _valid_recipient(recipient):
        raise ValueError("Enter a valid recipient email address.")
    status = ("Enabled; report will send when Product Finished is selected."
              if enabled else "Product-finished email is disabled.")
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        conn.executemany("""
            INSERT INTO app_preferences(preference_key,preference_value)
            VALUES (?,?)
            ON CONFLICT(preference_key) DO UPDATE
            SET preference_value=excluded.preference_value
        """, (
            ("product_finished_email_sender", sender),
            ("product_finished_email_recipient", recipient),
            ("product_finished_email_enabled", "1" if enabled else "0"),
            ("product_finished_email_status", status),
        ))
    return status


def _set_product_finished_status(database, status):
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        conn.execute("""
            INSERT INTO app_preferences(preference_key,preference_value)
            VALUES ('product_finished_email_status',?)
            ON CONFLICT(preference_key) DO UPDATE
            SET preference_value=excluded.preference_value
        """, (status,))


def _send_finished_run_report(database, run_id, sender, recipient):
    with sqlite3.connect(database, timeout=15) as conn:
        run = conn.execute("""
            SELECT r.product,p.pump_number,t.tank_number,
                   MIN(date(ps.session_date)),MAX(date(ps.session_date))
            FROM pump_product_runs r
            JOIN pumps p ON p.id=r.pump_id
            LEFT JOIN tanks t ON t.id=r.tank_id
            JOIN pump_sessions ps ON ps.run_id=r.id
            WHERE r.id=? AND r.status='CLOSED'
            GROUP BY r.id,r.product,p.pump_number,t.tank_number
        """, (run_id,)).fetchone()
    if not run or not run[3] or not run[4]:
        raise ValueError("No saved session dates were found for the finished product run.")
    start, end = date.fromisoformat(run[3]), date.fromisoformat(run[4])
    config = _smtp_configuration(sender)
    headers, rows = product_delivery_report(
        database, start.isoformat(), end.isoformat()
    )
    detail_headers, detail_rows = product_delivery_detail(
        database, start.isoformat(), end.isoformat()
    )
    from export_utils import export_product_delivery_pdf

    with tempfile.TemporaryDirectory(prefix="cleon_finished_report_") as directory:
        attachment = Path(directory) / f"product_finished_run_{run_id}.pdf"
        export_product_delivery_pdf(
            attachment, headers, rows, detail_headers, detail_rows,
            (start.isoformat(), end.isoformat())
        )
        message = EmailMessage()
        message["Subject"] = (
            f"CLEON product finished: {run[0]} / Pump {run[1]} "
            f"(Run {run_id})"
        )
        message["From"] = sender
        message["To"] = recipient
        message.set_content(
            f"Product run {run_id} for {run[0]} on Pump {run[1]} "
            f"(Tank {run[2] or 'not assigned'}) was finished.\n"
            f"Attached is the product/delivery report for "
            f"{start.isoformat()} through {end.isoformat()}."
        )
        message.add_attachment(
            attachment.read_bytes(), maintype="application", subtype="pdf",
            filename=attachment.name
        )
        if config["ssl"]:
            with smtplib.SMTP_SSL(
                config["host"], config["port"], timeout=30,
                context=ssl.create_default_context()
            ) as server:
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=30) as server:
                server.ehlo()
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
                if config["username"]:
                    server.login(config["username"], config["password"])
                server.send_message(message)


def send_product_finished_email(root, database, run_id):
    """Start one report email after a product run is explicitly finished."""
    sender, recipient, enabled, _status = product_finished_email_settings(database)
    if not enabled:
        return False, "Product-finished email is disabled in Report Center settings."
    if not _valid_recipient(sender) or not _valid_recipient(recipient):
        error = "A valid sender and recipient are required for product-finished email."
        _set_product_finished_status(database, error)
        return False, error
    try:
        _smtp_configuration(sender)
    except ValueError as error:
        _set_product_finished_status(database, str(error))
        return False, str(error)
    _set_product_finished_status(
        database, f"Sending finished-run report #{run_id} to {recipient}..."
    )

    def send():
        try:
            _send_finished_run_report(database, run_id, sender, recipient)
        except (ValueError, sqlite3.Error, OSError, smtplib.SMTPException,
                ImportError, RuntimeError) as error:
            _set_product_finished_status(
                database, f"Product-finished email failed: {error}"
            )
        else:
            _set_product_finished_status(
                database,
                f"Sent product-finished report #{run_id} from {sender} "
                f"to {recipient} successfully."
            )

    threading.Thread(target=send, daemon=True).start()
    return True, f"Run closed. Product report is being emailed to {recipient}."
