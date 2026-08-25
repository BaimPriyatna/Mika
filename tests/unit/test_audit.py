from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from mika.audit.models import (
    AuditOutcome,
    AuditRecord,
    ConfirmationRecord,
    ExecutionResult,
    RollbackResult,
    VerificationResult,
)
from mika.audit.logger import AuditLogger


def _make_record(**kwargs) -> AuditRecord:
    defaults: dict = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(tz=timezone.utc),
        "user": "alice",
        "router": "10.0.0.1",
        "request": "show interfaces",
        "outcome": AuditOutcome.PENDING,
    }
    defaults.update(kwargs)
    return AuditRecord(**defaults)


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture()
def audit(db_path: Path) -> AuditLogger:
    with AuditLogger(db_path=db_path) as al:
        yield al


class TestAuditRecord:

    def test_minimal_valid_record(self):
        r = _make_record()
        assert r.outcome == AuditOutcome.PENDING
        assert r.intent is None
        assert r.plan is None

    def test_user_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            _make_record(user="")

    def test_router_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            _make_record(router="")

    def test_request_must_not_be_empty(self):
        with pytest.raises(ValidationError):
            _make_record(request="")

    def test_secret_in_request_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            _make_record(request="password=hunter2 please configure")

    def test_secret_in_user_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            _make_record(user="token=abc123user")

    def test_secret_in_router_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            _make_record(router="secret=key@10.0.0.1")

    def test_routeros_version_valid(self):
        r = _make_record(routeros_version="7.14.3")
        assert r.routeros_version == "7.14.3"

    def test_routeros_version_invalid(self):
        with pytest.raises(ValidationError):
            _make_record(routeros_version="not a version!!")

    def test_outcome_success_requires_execution_result(self):
        with pytest.raises(ValidationError, match="outcome=SUCCESS"):
            _make_record(outcome=AuditOutcome.SUCCESS)

    def test_outcome_success_requires_execution_success_true(self):
        exec_result = ExecutionResult(success=False, commands_applied=1, summary="failed")
        with pytest.raises(ValidationError, match="outcome=SUCCESS"):
            _make_record(outcome=AuditOutcome.SUCCESS, execution_result=exec_result)

    def test_outcome_success_valid(self):
        exec_result = ExecutionResult(success=True, commands_applied=2, summary="done")
        r = _make_record(outcome=AuditOutcome.SUCCESS, execution_result=exec_result)
        assert r.outcome == AuditOutcome.SUCCESS

    def test_outcome_rolled_back_requires_rollback_result(self):
        with pytest.raises(ValidationError, match="outcome=ROLLED_BACK"):
            _make_record(outcome=AuditOutcome.ROLLED_BACK)

    def test_extra_fields_rejected(self):
        with pytest.raises((ValidationError, TypeError)):
            _make_record(nonexistent_field="oops")

    def test_intent_accepts_dict(self):
        r = _make_record(intent={"intent": "inspect_interfaces", "confidence": 0.9})
        assert r.intent is not None

    def test_plan_accepts_dict(self):
        r = _make_record(plan={"steps": [], "validated": False})
        assert r.plan is not None


class TestConfirmationRecord:

    def test_valid_confirmed(self):
        cr = ConfirmationRecord(confirmed=True, method="yes/no prompt")
        assert cr.confirmed is True

    def test_valid_cancelled(self):
        cr = ConfirmationRecord(confirmed=False, method="yes/no prompt")
        assert cr.confirmed is False

    def test_secret_in_method_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            ConfirmationRecord(confirmed=True, method="password=xyz confirmation")


class TestExecutionResult:

    def test_valid_success(self):
        er = ExecutionResult(success=True, commands_applied=3, summary="hotspot created")
        assert er.success is True
        assert er.commands_applied == 3

    def test_valid_failure(self):
        er = ExecutionResult(success=False, commands_applied=0, error="timeout")
        assert er.error == "timeout"

    def test_negative_commands_rejected(self):
        with pytest.raises(ValidationError):
            ExecutionResult(success=True, commands_applied=-1)

    def test_secret_in_summary_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            ExecutionResult(success=True, commands_applied=1, summary="password=abc set")

    def test_secret_in_error_rejected(self):
        with pytest.raises(ValidationError, match="secret"):
            ExecutionResult(success=False, commands_applied=0, error="api_key=xyz failed")


class TestVerificationResult:

    def test_valid_verified(self):
        vr = VerificationResult(verified=True, checks_passed=3, checks_failed=0)
        assert vr.verified is True

    def test_verified_true_with_no_checks_rejected(self):
        with pytest.raises(ValidationError):
            VerificationResult(verified=True, checks_passed=0, checks_failed=0)

    def test_verified_true_with_failures_rejected(self):
        with pytest.raises(ValidationError):
            VerificationResult(verified=True, checks_passed=2, checks_failed=1)

    def test_not_verified_with_failures_valid(self):
        vr = VerificationResult(verified=False, checks_passed=1, checks_failed=2)
        assert vr.verified is False


class TestRollbackResult:

    def test_valid_attempted_success(self):
        rr = RollbackResult(attempted=True, success=True)
        assert rr.success is True

    def test_success_without_attempted_rejected(self):
        with pytest.raises(ValidationError):
            RollbackResult(attempted=False, success=True)

    def test_attempted_failure_valid(self):
        rr = RollbackResult(attempted=True, success=False)
        assert rr.attempted is True
        assert rr.success is False


class TestAuditLogger:

    def test_record_returns_uuid(self, audit: AuditLogger):
        rid = audit.record(user="alice", router="10.0.0.1", request="inspect")
        assert uuid.UUID(rid)

    def test_record_stored_and_queryable(self, audit: AuditLogger):
        rid = audit.record(user="bob", router="192.168.1.1", request="show routes")
        records = audit.query(router="192.168.1.1")
        assert len(records) == 1
        assert records[0].id == rid
        assert records[0].outcome == AuditOutcome.PENDING

    def test_finalise_updates_outcome(self, audit: AuditLogger):
        rid = audit.record(user="alice", router="10.0.0.1", request="create hotspot")
        exec_res = ExecutionResult(success=True, commands_applied=3, summary="done")
        audit.finalise(rid, outcome=AuditOutcome.SUCCESS, execution_result=exec_res)

        records = audit.query()
        assert records[0].outcome == AuditOutcome.SUCCESS
        assert records[0].execution_result is not None
        assert records[0].execution_result.success is True

    def test_finalise_nonexistent_raises(self, audit: AuditLogger):
        with pytest.raises(KeyError):
            audit.finalise("nonexistent-id", outcome=AuditOutcome.FAILED)

    def test_query_filter_by_router(self, audit: AuditLogger):
        audit.record(user="alice", router="10.0.0.1", request="req1")
        audit.record(user="alice", router="10.0.0.2", request="req2")
        results = audit.query(router="10.0.0.1")
        assert len(results) == 1
        assert results[0].router == "10.0.0.1"

    def test_query_filter_by_user(self, audit: AuditLogger):
        audit.record(user="alice", router="10.0.0.1", request="req1")
        audit.record(user="bob", router="10.0.0.1", request="req2")
        results = audit.query(user="bob")
        assert len(results) == 1
        assert results[0].user == "bob"

    def test_query_filter_by_outcome(self, audit: AuditLogger):
        rid = audit.record(user="alice", router="10.0.0.1", request="do it")
        exec_res = ExecutionResult(success=True, commands_applied=1, summary="ok")
        audit.finalise(rid, outcome=AuditOutcome.SUCCESS, execution_result=exec_res)
        audit.record(user="alice", router="10.0.0.1", request="another")

        successes = audit.query(outcome=AuditOutcome.SUCCESS)
        assert len(successes) == 1
        assert successes[0].outcome == AuditOutcome.SUCCESS

    def test_query_limit(self, audit: AuditLogger):
        for i in range(5):
            audit.record(user="alice", router="10.0.0.1", request=f"req{i}")
        results = audit.query(limit=3)
        assert len(results) == 3

    def test_query_most_recent_first(self, audit: AuditLogger):
        rid1 = audit.record(user="alice", router="10.0.0.1", request="first")
        rid2 = audit.record(user="alice", router="10.0.0.1", request="second")
        results = audit.query()
        ids = [r.id for r in results]
        assert ids.index(rid2) < ids.index(rid1)

    def test_export_json_valid_array(self, audit: AuditLogger):
        audit.record(user="alice", router="10.0.0.1", request="inspect")
        output = audit.export_json()
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["user"] == "alice"

    def test_record_with_full_lifecycle(self, audit: AuditLogger):
        confirmation = ConfirmationRecord(confirmed=True, method="yes/no prompt")
        rid = audit.record(
            user="alice",
            router="10.0.0.1",
            request="create hotspot on ether3",
            routeros_version="7.14.3",
            intent={"intent": "create_hotspot", "confidence": 0.95},
            plan={"steps": ["add hotspot"], "validated": True},
            confirmation=confirmation,
        )
        exec_res = ExecutionResult(success=True, commands_applied=4, summary="hotspot created")
        verif_res = VerificationResult(verified=True, checks_passed=2, checks_failed=0)
        audit.finalise(
            rid,
            outcome=AuditOutcome.SUCCESS,
            execution_result=exec_res,
            verification_result=verif_res,
        )
        records = audit.query()
        r = records[0]
        assert r.outcome == AuditOutcome.SUCCESS
        assert r.confirmation is not None
        assert r.confirmation.confirmed is True
        assert r.verification_result is not None
        assert r.verification_result.verified is True
        assert r.routeros_version == "7.14.3"

    def test_context_manager_closes_db(self, db_path: Path):
        with AuditLogger(db_path=db_path) as al:
            al.record(user="alice", router="10.0.0.1", request="test")
        with AuditLogger(db_path=db_path) as al2:
            records = al2.query()
            assert len(records) == 1

    def test_record_validation_error_propagates(self, audit: AuditLogger):
        with pytest.raises(ValidationError):
            audit.record(user="alice", router="10.0.0.1", request="password=hunter2 cfg")

    def test_db_created_at_custom_path(self, tmp_path: Path):
        nested = tmp_path / "nested" / "dir" / "audit.db"
        with AuditLogger(db_path=nested) as al:
            al.record(user="alice", router="r1", request="test")
        assert nested.exists()
