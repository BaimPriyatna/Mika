"""
Conversation Session Persistence.

Stores conversation sessions and their messages so they survive across
`mika` restarts. A new session is started by default on every launch;
past sessions can be listed and resumed explicitly (/sessions, /resume).
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class SessionSummary:
    id: str
    title: str
    started_at: str
    updated_at: str
    message_count: int


@dataclass
class SessionMessage:
    role: str
    text: str
    created_at: str


class SessionStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_session_messages_session
                ON session_messages(session_id)
            """)
            conn.commit()

    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, started_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, "", now, now),
            )
            conn.commit()
        return session_id

    def add_message(self, session_id: str, role: str, text: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO session_messages (session_id, role, text, created_at) VALUES (?, ?, ?, ?)",
                (session_id, role, text, now),
            )
            # Keep the session's title as its first user message, and bump updated_at.
            row = conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            new_title = None
            if row and row[0] == "" and role == "user":
                new_title = text[:60]
            if new_title is not None:
                conn.execute(
                    "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (new_title, now, session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET updated_at = ? WHERE id = ?",
                    (now, session_id),
                )
            conn.commit()

    def list_sessions(self, limit: int = 20) -> list[SessionSummary]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT s.id, s.title, s.started_at, s.updated_at,
                       COUNT(m.id) AS message_count
                FROM sessions s
                LEFT JOIN session_messages m ON m.session_id = s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            SessionSummary(
                id=row["id"],
                title=row["title"] or "(empty)",
                started_at=row["started_at"],
                updated_at=row["updated_at"],
                message_count=row["message_count"],
            )
            for row in rows
        ]

    def get_messages(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        query = "SELECT role, text, created_at FROM session_messages WHERE session_id = ? ORDER BY id ASC"
        params: list = [session_id]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        messages = [SessionMessage(role=r["role"], text=r["text"], created_at=r["created_at"]) for r in rows]
        if limit is not None and len(messages) > limit:
            messages = messages[-limit:]
        return messages

    def session_exists(self, session_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row is not None

    def resolve_id(self, ref: str) -> str | None:
        """Resolve a session reference: either a full/partial id prefix or a
        1-based index into the most-recently-updated sessions list."""
        if ref.isdigit():
            summaries = self.list_sessions(limit=1000)
            idx = int(ref) - 1
            if 0 <= idx < len(summaries):
                return summaries[idx].id
            return None
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE id LIKE ?", (f"{ref}%",)
            ).fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None
