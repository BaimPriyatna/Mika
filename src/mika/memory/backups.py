"""
Plan Backup Persistence.

Stores every executed plan's PlanBackup (already produced by
executor/rollback.py), anchored to the exact conversation message that
triggered it, so /rewind can undo a chain of them back to any earlier
point in the conversation -- like `git checkout <commit>` for router
config, driven by conversation history rather than commit hashes.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mika.executor.rollback import PlanBackup
from mika.memory import db


@dataclass
class StoredBackup:
    id: int
    session_id: str
    message_id: int
    router_alias: str
    plan_id: str
    backup: PlanBackup
    created_at: str


class BackupStore:
    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    router_alias TEXT NOT NULL,
                    plan_id TEXT NOT NULL,
                    backup_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    rolled_back_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_plan_backups_session
                ON plan_backups(session_id)
            """)
            conn.commit()

    def add_backup(
        self,
        session_id: str,
        message_id: int,
        router_alias: str,
        backup: PlanBackup,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with db.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO plan_backups
                    (session_id, message_id, router_alias, plan_id, backup_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, message_id, router_alias, backup.plan_id, backup.model_dump_json(), now),
            )
            conn.commit()

    def list_backups_after(self, session_id: str, message_id: int) -> list[StoredBackup]:
        """Backups still available to undo (not yet rolled back), created
        after `message_id`, oldest first."""
        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, session_id, message_id, router_alias, plan_id, backup_json, created_at
                FROM plan_backups
                WHERE session_id = ? AND message_id > ? AND rolled_back_at IS NULL
                ORDER BY id ASC
                """,
                (session_id, message_id),
            ).fetchall()
        return [
            StoredBackup(
                id=row["id"],
                session_id=row["session_id"],
                message_id=row["message_id"],
                router_alias=row["router_alias"],
                plan_id=row["plan_id"],
                backup=PlanBackup.model_validate_json(row["backup_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def mark_rolled_back(self, backup_ids: list[int]) -> None:
        if not backup_ids:
            return
        now = datetime.now(timezone.utc).isoformat()
        placeholders = ",".join("?" for _ in backup_ids)
        with db.connect(self.db_path) as conn:
            conn.execute(
                f"UPDATE plan_backups SET rolled_back_at = ? WHERE id IN ({placeholders})",
                (now, *backup_ids),
            )
            conn.commit()
