"""
Memory Persistence Storage.

Provides atomic file-based persistence for stored memory facts and user preferences.
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mika.memory import db
from .models import Fact, FactCategory, MemoryEntry


class MemoryStorage:

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    key TEXT NOT NULL UNIQUE,
                    value TEXT NOT NULL,
                    description TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    router_specific INTEGER NOT NULL,
                    router_id TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    expires_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_category 
                ON memory(category)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_key 
                ON memory(key)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_router 
                ON memory(router_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memory_active 
                ON memory(active)
            """)
            conn.commit()

    def add(self, fact: Fact) -> int:
        with db.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT id FROM memory WHERE key = ?",
                (fact.key,)
            )
            existing = cursor.fetchone()

            if existing:
                conn.execute("""
                    UPDATE memory 
                    SET value = ?,
                        description = ?,
                        confidence = ?,
                        router_specific = ?,
                        router_id = ?,
                        updated_at = ?,
                        source = ?
                    WHERE key = ?
                """, (
                    json.dumps(fact.value),
                    fact.description,
                    fact.confidence,
                    int(fact.router_specific),
                    fact.router_id,
                    datetime.now(timezone.utc).isoformat(),
                    fact.source,
                    fact.key,
                ))
                return existing[0]
            else:
                cursor = conn.execute("""
                    INSERT INTO memory (
                        category, key, value, description, source,
                        confidence, router_specific, router_id,
                        created_at, updated_at, last_accessed
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fact.category.value,
                    fact.key,
                    json.dumps(fact.value),
                    fact.description,
                    fact.source,
                    fact.confidence,
                    int(fact.router_specific),
                    fact.router_id,
                    fact.created_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                    fact.last_accessed.isoformat(),
                ))
                conn.commit()
                return cursor.lastrowid

    def get(self, key: str) -> Optional[MemoryEntry]:
        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM memory WHERE key = ?",
                (key,)
            )
            row = cursor.fetchone()

            if row:
                return self._row_to_entry(row)
            return None

    def list_all(
        self,
        category: Optional[FactCategory] = None,
        router_id: Optional[str] = None,
        active_only: bool = True,
    ) -> list[MemoryEntry]:
        query = "SELECT * FROM memory WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if router_id:
            query += " AND (router_id = ? OR router_specific = 0)"
            params.append(router_id)

        if active_only:
            query += " AND active = 1"

        query += " ORDER BY created_at DESC"

        with db.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            entries = [self._row_to_entry(row) for row in cursor.fetchall()]

            return [e for e in entries if not active_only or e.is_valid()]

    def delete(self, key: str) -> bool:
        with db.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM memory WHERE key = ?",
                (key,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def deactivate(self, key: str) -> bool:
        with db.connect(self.db_path) as conn:
            cursor = conn.execute("""
                UPDATE memory 
                SET active = 0, updated_at = ?
                WHERE key = ?
            """, (
                datetime.now(timezone.utc).isoformat(),
                key,
            ))
            conn.commit()
            return cursor.rowcount > 0

    def record_access(self, key: str) -> None:
        with db.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memory 
                SET last_accessed = ?,
                    access_count = access_count + 1
                WHERE key = ?
            """, (
                datetime.now(timezone.utc).isoformat(),
                key,
            ))
            conn.commit()

    def clear_all(self, router_id: Optional[str] = None) -> int:
        with db.connect(self.db_path) as conn:
            if router_id:
                cursor = conn.execute(
                    "DELETE FROM memory WHERE router_id = ?",
                    (router_id,)
                )
            else:
                cursor = conn.execute("DELETE FROM memory")
            conn.commit()
            return cursor.rowcount

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        fact = Fact(
            category=FactCategory(row["category"]),
            key=row["key"],
            value=json.loads(row["value"]),
            description=row["description"],
            source=row["source"],
            confidence=row["confidence"],
            router_specific=bool(row["router_specific"]),
            router_id=row["router_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            access_count=row["access_count"],
        )

        return MemoryEntry(
            id=row["id"],
            fact=fact,
            active=bool(row["active"]),
            expires_at=datetime.fromisoformat(row["expires_at"]) if row["expires_at"] else None,
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
