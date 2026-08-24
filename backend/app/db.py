import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_column(conn, table, column, ddl):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db():
    schema = """
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_id TEXT,
        name TEXT NOT NULL,
        debt_amount INTEGER NOT NULL DEFAULT 0,
        telegram_chat_id TEXT UNIQUE,
        telegram_group_title TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        collection_active INTEGER NOT NULL DEFAULT 0,
        collection_started_at TEXT,
        last_contact_at TEXT,
        last_reply_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_external_id
      ON customers(external_id) WHERE external_id IS NOT NULL AND external_id <> '';

    CREATE TABLE IF NOT EXISTS promises (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        amount INTEGER NOT NULL,
        due_date TEXT,
        due_date_jalali TEXT,
        status TEXT NOT NULL DEFAULT 'awaiting_date',
        reminder_sent INTEGER NOT NULL DEFAULT 0,
        source_message TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_promises_due ON promises(status, due_date);

    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
        direction TEXT NOT NULL,
        body TEXT NOT NULL,
        telegram_message_id TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS imports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT NOT NULL,
        file_type TEXT NOT NULL,
        row_count INTEGER NOT NULL DEFAULT 0,
        inserted_count INTEGER NOT NULL DEFAULT 0,
        updated_count INTEGER NOT NULL DEFAULT 0,
        skipped_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """
    with db() as conn:
        conn.executescript(schema)
        # Lightweight forward migrations for databases created by older MVP builds.
        _ensure_column(conn, "customers", "collection_active", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(conn, "customers", "collection_started_at", "TEXT")
