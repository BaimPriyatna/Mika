"""
Shared SQLite connection helper for memory.db.

SessionStore, BackupStore, and MemoryStorage each open a short-lived
connection per call rather than holding one open, so WAL mode and
busy_timeout are applied on every connect() here rather than once at
init -- WAL mode is a one-time, persistent property of the database
file, but busy_timeout is per-connection and must be set every time.

WAL mode lets readers and writers proceed concurrently instead of
blocking each other, and busy_timeout makes a connection retry for a
while instead of raising "database is locked" immediately, so running
more than one `mika` session against the same memory.db (same machine)
no longer fails outright under light write contention.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_BUSY_TIMEOUT_MS = 5000


def connect(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=_BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS};")
    return conn
