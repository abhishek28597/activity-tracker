"""
Database utilities for Activity Tracker.

Provides connection management, thread-safety, and schema initialization.
"""

import sqlite3
from contextlib import contextmanager
from typing import Optional
import threading
from config import DATABASE_PATH, DB_TABLE_ACTIVITY_LOG, DB_TABLE_KEYSTROKE_LOG

# Thread-local storage for connections
_thread_local = threading.local()


@contextmanager
def get_db_connection(row_factory: bool = True):
    """
    Context manager for database connections.

    Args:
        row_factory: If True, use Row factory for dict-like access

    Yields:
        sqlite3.Connection: Database connection

    Example:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM activity_log")
    """
    conn = sqlite3.connect(str(DATABASE_PATH))
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def get_thread_local_connection() -> sqlite3.Connection:
    """
    Get or create a thread-local database connection.
    Useful for long-running threads like the tracker daemon.

    Returns:
        sqlite3.Connection: Thread-local connection
    """
    if not hasattr(_thread_local, 'conn') or _thread_local.conn is None:
        _thread_local.conn = sqlite3.connect(
            str(DATABASE_PATH),
            check_same_thread=False
        )
    return _thread_local.conn


def init_database(conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Initialize database schema. Safe to call multiple times.

    Args:
        conn: Optional connection to use. If None, creates temporary connection.
    """
    should_close = False
    if conn is None:
        conn = sqlite3.connect(str(DATABASE_PATH))
        should_close = True

    cursor = conn.cursor()

    # Activity log table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {DB_TABLE_ACTIVITY_LOG} (
            timestamp DATETIME,
            hour INTEGER,
            app_name TEXT,
            keystrokes INTEGER,
            clicks INTEGER
        )
    ''')

    # Keystroke log table
    cursor.execute(f'''
        CREATE TABLE IF NOT EXISTS {DB_TABLE_KEYSTROKE_LOG} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME,
            key_pressed TEXT,
            app_name TEXT
        )
    ''')

    conn.commit()

    if should_close:
        conn.close()
