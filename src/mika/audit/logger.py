from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mika.audit.models import (
    AuditOutcome,
    AuditRecord,
    ConfirmationRecord,
    ExecutionResult,
    RollbackResult,
    VerificationResult,
)

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = Path.home() / ".mikrotik-ai" / "app.db"

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS audit_records (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    user        TEXT NOT NULL,
    router      TEXT NOT NULL,
    outcome     TEXT NOT NULL,
    record_json TEXT NOT NULL
);
"""

_CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_audit_router_ts
    ON audit_records (router, timestamp DESC);
"""


class AuditLogger:

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else _DEFAULT_DB_PATH
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(
            str(self._db_path),
            check_same_thread=False,
        )
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._conn.executescript(_CREATE_TABLE_SQL + _CREATE_INDEX_SQL)
        self._conn.commit()
        logger.debug("AuditLogger initialised at %s", self._db_path)


    def record(
        self,
        *,
        user: str,
        router: str,
        request: str,
        routeros_version: str | None = None,
        intent: dict[str, Any] | None = None,
        plan: dict[str, Any] | None = None,
        confirmation: ConfirmationRecord | None = None,
        execution_result: ExecutionResult | None = None,
        verification_result: VerificationResult | None = None,
        rollback_result: RollbackResult | None = None,
        outcome: AuditOutcome = AuditOutcome.PENDING,
    ) -> str:
        record_id = str(uuid.uuid4())
        now = datetime.now(tz=timezone.utc)

        audit = AuditRecord(
            id=record_id,
            timestamp=now,
            user=user,
            router=router,
            request=request,
            routeros_version=routeros_version,
            intent=intent,
            plan=plan,
            confirmation=confirmation,
            execution_result=execution_result,
            verification_result=verification_result,
            rollback_result=rollback_result,
            outcome=outcome,
        )

        self._insert(audit)
        logger.info(
            "audit record created id=%s user=%s router=%s outcome=%s",
            record_id, user, router, outcome.value,
        )
        return record_id

    def finalise(
        self,
        record_id: str,
        *,
        outcome: AuditOutcome,
        execution_result: ExecutionResult | None = None,
        verification_result: VerificationResult | None = None,
        rollback_result: RollbackResult | None = None,
    ) -> None:
        existing = self._load(record_id)
        if existing is None:
            raise KeyError(f"No audit record found with id={record_id!r}")

        updates: dict[str, Any] = {"outcome": outcome}
        if execution_result is not None:
            updates["execution_result"] = execution_result
        if verification_result is not None:
            updates["verification_result"] = verification_result
        if rollback_result is not None:
            updates["rollback_result"] = rollback_result

        updated = existing.model_copy(update=updates)
        self._upsert(updated)
        logger.info(
            "audit record finalised id=%s outcome=%s", record_id, outcome.value
        )

    def query(
        self,
        *,
        router: str | None = None,
        user: str | None = None,
        outcome: AuditOutcome | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AuditRecord]:
        limit = min(limit, 1000)
        clauses: list[str] = []
        params: list[Any] = []

        if router is not None:
            clauses.append("router = ?")
            params.append(router)
        if user is not None:
            clauses.append("user = ?")
            params.append(user)
        if outcome is not None:
            clauses.append("outcome = ?")
            params.append(outcome.value)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = (
            f"SELECT record_json FROM audit_records {where} "
            f"ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])

        rows = self._conn.execute(sql, params).fetchall()
        return [AuditRecord.model_validate_json(row[0]) for row in rows]

    def export_json(
        self,
        *,
        router: str | None = None,
        user: str | None = None,
        outcome: AuditOutcome | None = None,
        limit: int = 50,
    ) -> str:
        records = self.query(router=router, user=user, outcome=outcome, limit=limit)
        return json.dumps(
            [json.loads(r.model_dump_json()) for r in records],
            indent=2,
            ensure_ascii=False,
        )

    def close(self) -> None:
        self._conn.close()
        logger.debug("AuditLogger closed db=%s", self._db_path)

    def __enter__(self) -> "AuditLogger":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


    def _insert(self, record: AuditRecord) -> None:
        self._conn.execute(
            "INSERT INTO audit_records (id, timestamp, user, router, outcome, record_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.timestamp.isoformat(),
                record.user,
                record.router,
                record.outcome.value,
                record.model_dump_json(),
            ),
        )
        self._conn.commit()

    def _upsert(self, record: AuditRecord) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO audit_records "
            "(id, timestamp, user, router, outcome, record_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                record.id,
                record.timestamp.isoformat(),
                record.user,
                record.router,
                record.outcome.value,
                record.model_dump_json(),
            ),
        )
        self._conn.commit()

    def _load(self, record_id: str) -> AuditRecord | None:
        row = self._conn.execute(
            "SELECT record_json FROM audit_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            return None
        return AuditRecord.model_validate_json(row[0])
