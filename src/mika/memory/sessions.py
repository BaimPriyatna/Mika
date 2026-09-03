"""
Conversation Session Persistence.

Stores conversation sessions and their messages so they survive across
`mika` restarts. A new session is started by default on every launch, and
also whenever the active router is switched to a different one (so each
session's messages all belong to a single router). Past sessions can be
browsed and resumed via /history (grouped by router, then by session).
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mika.memory import db


@dataclass
class SessionSummary:
    id: str
    title: str
    started_at: str
    updated_at: str
    message_count: int
    router_alias: str | None


@dataclass
class RouterSessionGroup:
    router_alias: str | None  # None = sessions created before any router was ever selected
    session_count: int


@dataclass
class SessionMessage:
    id: int
    role: str
    text: str
    created_at: str
    render_kind: str = "plain"
    render_payload: str | None = None


class SessionStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    router_alias TEXT,
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
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add columns introduced after the initial CREATE TABLE. Each
        ALTER TABLE is wrapped since SQLite has no "ADD COLUMN IF NOT
        EXISTS" -- a duplicate-column OperationalError means a previous
        run (or another concurrent process) already applied it."""
        for ddl in (
            "ALTER TABLE session_messages ADD COLUMN render_kind TEXT NOT NULL DEFAULT 'plain'",
            "ALTER TABLE session_messages ADD COLUMN render_payload TEXT",
        ):
            try:
                conn.execute(ddl)
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise
        conn.commit()

    def create_session(self, router_alias: str | None = None) -> str:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        with db.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO sessions (id, title, router_alias, started_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "", router_alias, now, now),
            )
            conn.commit()
        return session_id

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        render_kind: str = "plain",
        render_payload: str | None = None,
    ) -> int:
        """Persist a message and return its row id (used to anchor rewind
        points and plan backups to a precise point in the conversation).

        `render_kind`/`render_payload` capture enough structure to replay
        the original rendered output (e.g. advice options, inspect
        target) on /history resume -- `text` alone stays a plain
        description for search and AI context."""
        now = datetime.now(timezone.utc).isoformat()
        with db.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO session_messages (session_id, role, text, created_at, render_kind, render_payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, role, text, now, render_kind, render_payload),
            )
            message_id = cursor.lastrowid
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
        return message_id

    def list_routers_with_sessions(self) -> list[RouterSessionGroup]:
        """Level-1 grouping for /history: one entry per router that has at
        least one saved session with at least one message, plus a
        '(no router)' bucket for such sessions created before any router
        was ever selected. Empty sessions (0 messages -- nothing to
        resume) don't count. Ordered by most recently active."""
        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT s.router_alias AS router_alias,
                       COUNT(*) AS session_count,
                       MAX(s.updated_at) AS last_active
                FROM sessions s
                WHERE EXISTS (
                    SELECT 1 FROM session_messages m WHERE m.session_id = s.id
                )
                GROUP BY s.router_alias
                ORDER BY last_active DESC
            """).fetchall()
        return [
            RouterSessionGroup(router_alias=row["router_alias"], session_count=row["session_count"])
            for row in rows
        ]

    def list_sessions(self, router_alias: str | None = "__any__", limit: int = 50) -> list[SessionSummary]:
        """List sessions that have at least one message (empty sessions have
        nothing to resume, so they're excluded), most recently updated
        first. `router_alias`:
        - "__any__" (default): no filter, all sessions
        - None: only sessions with no router (router_alias IS NULL)
        - a string: only sessions for that router
        """
        query = """
            SELECT s.id, s.title, s.router_alias, s.started_at, s.updated_at,
                   COUNT(m.id) AS message_count
            FROM sessions s
            LEFT JOIN session_messages m ON m.session_id = s.id
        """
        params: list = []
        if router_alias != "__any__":
            query += " WHERE s.router_alias IS ?"
            params.append(router_alias)
        query += " GROUP BY s.id HAVING COUNT(m.id) > 0 ORDER BY s.updated_at DESC LIMIT ?"
        params.append(limit)

        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, params).fetchall()
        return [
            SessionSummary(
                id=row["id"],
                title=row["title"] or "(empty)",
                started_at=row["started_at"],
                updated_at=row["updated_at"],
                message_count=row["message_count"],
                router_alias=row["router_alias"],
            )
            for row in rows
        ]

    def get_messages(self, session_id: str, limit: int | None = None) -> list[SessionMessage]:
        query = (
            "SELECT id, role, text, created_at, render_kind, render_payload "
            "FROM session_messages WHERE session_id = ? ORDER BY id ASC"
        )
        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(query, [session_id]).fetchall()
        messages = [
            SessionMessage(
                id=r["id"],
                role=r["role"],
                text=r["text"],
                created_at=r["created_at"],
                render_kind=r["render_kind"],
                render_payload=r["render_payload"],
            )
            for r in rows
        ]
        if limit is not None and len(messages) > limit:
            messages = messages[-limit:]
        return messages

    def trim_after(self, session_id: str, message_id: int) -> int:
        """Delete messages after `message_id` in this session (used after a
        successful /rewind so future history stays consistent with the
        rolled-back router config). Returns the number of rows deleted."""
        with db.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM session_messages WHERE session_id = ? AND id > ?",
                (session_id, message_id),
            )
            now = datetime.now(timezone.utc).isoformat()
            conn.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, session_id))
            conn.commit()
        return cursor.rowcount

    def session_exists(self, session_id: str) -> bool:
        with db.connect(self.db_path) as conn:
            row = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row is not None

    def resolve_id(self, ref: str) -> str | None:
        """Resolve a session reference: either a full/partial id prefix or a
        1-based index into the most-recently-updated sessions list.

        Numeric refs up to 4 digits (index into a realistically small list)
        are tried as an index; longer numeric-looking refs are almost
        certainly a UUID prefix that happens to be all digits, so those go
        straight to prefix lookup instead.
        """
        if ref.isdigit() and len(ref) <= 4:
            summaries = self.list_sessions(limit=1000)
            idx = int(ref) - 1
            if 0 <= idx < len(summaries):
                return summaries[idx].id
            return None
        with db.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id FROM sessions WHERE id LIKE ?", (f"{ref}%",)
            ).fetchall()
        if len(rows) == 1:
            return rows[0][0]
        return None
