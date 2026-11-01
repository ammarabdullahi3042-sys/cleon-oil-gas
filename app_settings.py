"""App preferences, separate admin credentials, and SQLite backup/restore."""

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
STATION_CONFIG = APP_DIR / "cleon_stations.json"
DEFAULT_PASSWORDS = {
    "accounts": "Cleon$Acct-47Qm!2026",
    "settings": "Cl3on!Settings-92Rx",
}
BACKUP_NAME = "fuel_station_latest_backup.db"


def _station_registry():
    if not STATION_CONFIG.exists():
        return {
            "active": "main",
            "stations": [{"id": "main", "name": "Main Station",
                          "database": "fuel_station.db"}],
        }
    try:
        data = json.loads(STATION_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "active": "main",
            "stations": [{"id": "main", "name": "Main Station",
                          "database": "fuel_station.db"}],
        }
    if not isinstance(data, dict) or not isinstance(data.get("stations"), list):
        raise ValueError("The station list file is invalid. Restore cleon_stations.json or contact support.")
    return data


def get_active_database():
    registry = _station_registry()
    active = registry.get("active", "main")
    station = next((item for item in registry["stations"] if item.get("id") == active), None)
    relative_path = station.get("database") if station else "fuel_station.db"
    return str((APP_DIR / relative_path).resolve())


DATABASE = get_active_database()


def get_station_options():
    registry = _station_registry()
    return [(item["id"], item["name"], str((APP_DIR / item["database"]).resolve()))
            for item in registry["stations"]]


def get_active_station_id():
    return _station_registry().get("active", "main")


def get_active_station_name():
    active = get_active_station_id()
    for station_id, name, _path in get_station_options():
        if station_id == active:
            return name
    return "Main Station"


def _save_station_registry(registry):
    STATION_CONFIG.write_text(json.dumps(registry, indent=2), encoding="utf-8")


def switch_active_station(station_id):
    registry = _station_registry()
    if not any(item.get("id") == station_id for item in registry["stations"]):
        raise ValueError("Select a station that exists in the station list.")
    registry["active"] = station_id
    _save_station_registry(registry)


def create_station(name, source_database=None):
    """Create an isolated station database based on the current app schema."""
    name = str(name or "").strip()
    if len(name) < 2:
        raise ValueError("Enter a station name with at least 2 characters.")
    registry = _station_registry()
    if any(item.get("name", "").casefold() == name.casefold()
           for item in registry["stations"]):
        raise ValueError("A station with that name already exists.")
    slug = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    if not slug:
        raise ValueError("Use letters or numbers in the station name.")
    station_id = slug
    if any(item.get("id") == station_id for item in registry["stations"]):
        station_id = f"{slug}_{secrets.token_hex(3)}"
    stations_dir = APP_DIR / "stations"
    stations_dir.mkdir(parents=True, exist_ok=True)
    relative_db = str(Path("stations") / f"{station_id}.db")
    target = APP_DIR / relative_db
    source = Path(source_database or get_active_database()).resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Source station database was not found: {source}")
    with sqlite3.connect(str(source), timeout=15) as source_conn:
        with sqlite3.connect(str(target), timeout=15) as target_conn:
            source_conn.backup(target_conn)
    reset_operational_data(target)
    registry["stations"].append({"id": station_id, "name": name,
                                 "database": relative_db})
    registry["active"] = station_id
    _save_station_registry(registry)
    return station_id, target.resolve()


def _password_hash(password, salt):
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 240_000
    ).hex()


def ensure_app_settings(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_preferences (
            preference_key TEXT PRIMARY KEY,
            preference_value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_security (
            access_key TEXT PRIMARY KEY,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT OR IGNORE INTO app_preferences(preference_key,preference_value)
        VALUES ('theme_mode','dark')
    """)
    conn.executemany("""
        INSERT OR IGNORE INTO app_preferences(preference_key,preference_value)
        VALUES (?,?)
    """, (
        ("product_finished_email_sender", "ammarabdullahi3042@gmail.com"),
        ("product_finished_email_recipient", "cleonoilandgas@gmail.com"),
        ("product_finished_email_enabled", "1"),
        ("product_finished_email_status", "Product-finished email enabled; SMTP setup is required."),
    ))
    for access_key, password in DEFAULT_PASSWORDS.items():
        if not conn.execute(
            "SELECT 1 FROM app_security WHERE access_key=?", (access_key,)
        ).fetchone():
            salt = secrets.token_hex(16)
            conn.execute("""
                INSERT INTO app_security(access_key,salt,password_hash,updated_at)
                VALUES (?,?,?,?)
            """, (access_key, salt, _password_hash(password, salt),
                  datetime.now().isoformat(timespec="seconds")))


def get_theme_mode(database=DATABASE):
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        row = conn.execute(
            "SELECT preference_value FROM app_preferences WHERE preference_key='theme_mode'"
        ).fetchone()
    return row[0] if row and row[0] in ("dark", "light") else "dark"


def save_theme_mode(mode, database=DATABASE):
    if mode not in ("dark", "light"):
        raise ValueError("Choose Dark or Light theme.")
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        conn.execute("""
            INSERT INTO app_preferences(preference_key,preference_value)
            VALUES ('theme_mode',?)
            ON CONFLICT(preference_key) DO UPDATE SET preference_value=excluded.preference_value
        """, (mode,))


def get_display_scale(database=DATABASE):
    """Return the saved application text and widget scale."""
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        row = conn.execute(
            "SELECT preference_value FROM app_preferences "
            "WHERE preference_key='display_scale'"
        ).fetchone()
    try:
        scale = float(row[0]) if row else 1.0
    except (TypeError, ValueError):
        return 1.0
    return scale if 0.85 <= scale <= 1.20 else 1.0


def save_display_scale(scale, database=DATABASE):
    try:
        scale = float(scale)
    except (TypeError, ValueError) as error:
        raise ValueError("Choose a display scale between 85% and 120%.") from error
    if not 0.85 <= scale <= 1.20:
        raise ValueError("Choose a display scale between 85% and 120%.")
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        conn.execute("""
            INSERT INTO app_preferences(preference_key,preference_value)
            VALUES ('display_scale',?)
            ON CONFLICT(preference_key) DO UPDATE SET
                preference_value=excluded.preference_value
        """, (f"{scale:.2f}",))


def verify_access(access_key, password, database=DATABASE):
    if access_key not in DEFAULT_PASSWORDS:
        return False
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        row = conn.execute(
            "SELECT salt,password_hash FROM app_security WHERE access_key=?",
            (access_key,),
        ).fetchone()
    return bool(row and hmac.compare_digest(_password_hash(password, row[0]), row[1]))


def change_access_password(access_key, new_password, database=DATABASE):
    if access_key not in DEFAULT_PASSWORDS:
        raise ValueError("Unknown access type.")
    if len(new_password) < 10:
        raise ValueError("Use at least 10 characters for the new password.")
    salt = secrets.token_hex(16)
    with sqlite3.connect(database, timeout=10) as conn:
        ensure_app_settings(conn)
        conn.execute("""
            UPDATE app_security SET salt=?,password_hash=?,updated_at=?
            WHERE access_key=?
        """, (salt, _password_hash(new_password, salt),
              datetime.now().isoformat(timespec="seconds"), access_key))


def change_login_credentials(current_username, new_username, new_password,
                             database=DATABASE):
    """Change the currently signed-in user's username and password."""
    current_username = str(current_username or "").strip()
    new_username = str(new_username or "").strip()
    if not current_username:
        raise ValueError("The current login user could not be identified.")
    if not new_username:
        raise ValueError("Enter a username for the main login.")
    if len(new_password) < 10:
        raise ValueError("Use at least 10 characters for the new login password.")
    with sqlite3.connect(database, timeout=10) as conn:
        user = conn.execute(
            "SELECT id FROM users WHERE username=?", (current_username,)
        ).fetchone()
        if not user:
            raise ValueError("The current login user was not found.")
        duplicate = conn.execute(
            "SELECT 1 FROM users WHERE username=? AND id<>?",
            (new_username, user[0])
        ).fetchone()
        if duplicate:
            raise ValueError("That username is already in use.")
        conn.execute(
            "UPDATE users SET username=?, password=? WHERE id=?",
            (new_username, new_password, user[0])
        )
    return new_username


def backup_path(database=DATABASE):
    db_path = Path(database).resolve()
    return db_path.parent / "backups" / BACKUP_NAME


def save_database_backup(database=DATABASE):
    source_path = Path(database).resolve()
    if not source_path.exists():
        raise FileNotFoundError(f"Database was not found: {source_path}")
    destination = backup_path(database)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(source_path), timeout=15) as source:
        with sqlite3.connect(str(destination), timeout=15) as target:
            source.backup(target)
    return destination


def restore_last_backup(database=DATABASE):
    live_path = Path(database).resolve()
    saved_path = backup_path(database)
    if not saved_path.is_file():
        raise FileNotFoundError("No saved backup exists yet. Save a backup first.")

    safety_path = live_path.parent / "backups" / (
        f"before_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    safety_path.parent.mkdir(parents=True, exist_ok=True)
    security_rows = []
    preference_rows = []
    if live_path.exists():
        with sqlite3.connect(str(live_path), timeout=15) as current:
            try:
                security_rows = current.execute(
                    "SELECT access_key,salt,password_hash,updated_at FROM app_security"
                ).fetchall()
                preference_rows = current.execute(
                    "SELECT preference_key,preference_value FROM app_preferences"
                ).fetchall()
            except sqlite3.OperationalError:
                pass
            with sqlite3.connect(str(safety_path), timeout=15) as safety:
                current.backup(safety)

    with sqlite3.connect(str(saved_path), timeout=15) as saved:
        with sqlite3.connect(str(live_path), timeout=15) as current:
            saved.backup(current)
            ensure_app_settings(current)
            for row in security_rows:
                current.execute("""
                    INSERT INTO app_security(access_key,salt,password_hash,updated_at)
                    VALUES (?,?,?,?) ON CONFLICT(access_key) DO UPDATE SET
                    salt=excluded.salt,password_hash=excluded.password_hash,
                    updated_at=excluded.updated_at
                """, row)
            for key, value in preference_rows:
                current.execute("""
                    INSERT INTO app_preferences(preference_key,preference_value)
                    VALUES (?,?) ON CONFLICT(preference_key)
                    DO UPDATE SET preference_value=excluded.preference_value
                """, (key, value))
    return safety_path


def reset_operational_data(database=DATABASE):
    """Back up the database, then clear operating records and setup masters.

    Login credentials, application passwords and appearance preferences remain.
    """
    live_path = Path(database).resolve()
    if not live_path.is_file():
        raise FileNotFoundError(f"Database was not found: {live_path}")
    safety_path = live_path.parent / "backups" / (
        f"before_test_reset_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    )
    safety_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(live_path), timeout=15) as source:
        with sqlite3.connect(str(safety_path), timeout=15) as safety:
            source.backup(safety)

    tables_to_clear = (
        "fifo_session_allocations", "tank_dips", "pump_sessions",
        "fuel_receipts", "account_transactions", "expenses", "rtt",
        "product_prices", "pumps", "tanks", "attendants",
    )
    with sqlite3.connect(str(live_path), timeout=15) as conn:
        conn.execute("PRAGMA foreign_keys=OFF")
        existing = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        for table in tables_to_clear:
            if table in existing:
                conn.execute(f'DELETE FROM "{table}"')
        if "sqlite_sequence" in existing:
            conn.executemany(
                "DELETE FROM sqlite_sequence WHERE name=?",
                [(table,) for table in tables_to_clear]
            )
    return safety_path
