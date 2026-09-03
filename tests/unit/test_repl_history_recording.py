"""
Regression tests: _handle_chat_turn() must record exactly one assistant
history entry per turn, tagged with the render_kind/render_payload that
matches what was actually rendered (v0.3.0 schema).

Previously, an unconditional `add_history("assistant", f"intent=...")`
fired for every intent, and advise/troubleshoot/execution branches then
added a *second* entry on top of it -- double-writing history. Inspect
intents, meanwhile, wrote no assistant entry at all. Both are fixed by
having each terminal branch record its own single, descriptive entry.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from rich.console import Console

from mika.ai.schemas.read_intents import AdviseIntent, InspectRouterIntent, TroubleshootIntent
from mika.cli import config as cli_config
from mika.cli.repl import _handle_chat_turn
from mika.cli.session import ChatSession
from mika.router.mock import MockRouterClient
from mika.troubleshoot.models import DiagnosisResult


@pytest.fixture
def connected_session(tmp_path):
    cfg = cli_config.AppConfig(
        routers={"mock-router": cli_config.RouterProfileConfig(host="192.168.88.1", username="admin", port=443, backend="mock")}
    )
    config_path = tmp_path / "config.toml"
    cli_config.save_config(cfg, config_path)
    session = ChatSession.create(config_path, tmp_path / "memory.db")
    session.connect_router("mock-router")
    session.provider = AsyncMock()
    session.provider_name = "gemini"
    return session


def _assistant_entries(session):
    return [h for h in session.history if h.role == "assistant"]


@pytest.mark.asyncio
async def test_advise_intent_writes_exactly_one_entry(connected_session):
    intent = AdviseIntent(confidence=0.9, requires_confirmation=False, message="Consider enabling NAT.")
    connected_session.provider.generate_intent = AsyncMock(return_value=intent)

    await _handle_chat_turn("should I enable nat?", connected_session, Console(record=True))

    entries = _assistant_entries(connected_session)
    assert len(entries) == 1
    assert entries[0].text == "Consider enabling NAT."
    assert entries[0].render_kind == "advice"
    payload = json.loads(entries[0].render_payload)
    assert payload["message"] == "Consider enabling NAT."


@pytest.mark.asyncio
async def test_inspect_intent_writes_exactly_one_entry(connected_session):
    intent = InspectRouterIntent(confidence=0.9, requires_confirmation=False)
    connected_session.provider.generate_intent = AsyncMock(return_value=intent)

    await _handle_chat_turn("show me the interfaces", connected_session, Console(record=True))

    entries = _assistant_entries(connected_session)
    assert len(entries) == 1
    assert "inspected" in entries[0].text
    assert entries[0].render_kind == "inspect"
    payload = json.loads(entries[0].render_payload)
    assert "target" in payload and "ctx" in payload


@pytest.mark.asyncio
async def test_troubleshoot_intent_writes_exactly_one_entry_with_real_diagnosis_text(connected_session):
    intent = TroubleshootIntent(confidence=0.9, requires_confirmation=False, problem_description="clients can't reach the internet")
    connected_session.provider.generate_intent = AsyncMock(return_value=intent)

    diagnosis = DiagnosisResult(
        problem_description="clients can't reach the internet",
        router_identity="mock-router",
        hypotheses=(),
        recommended_fixes=(),
    )
    with patch("mika.cli.troubleshoot_ui.troubleshoot_problem", AsyncMock(return_value=diagnosis)):
        await _handle_chat_turn("clients can't reach the internet", connected_session, Console(record=True))

    entries = _assistant_entries(connected_session)
    assert len(entries) == 1
    assert entries[0].text == "clients can't reach the internet"
    assert entries[0].text != "(diagnosis shown)"
    assert entries[0].render_kind == "troubleshoot"
    payload = json.loads(entries[0].render_payload)
    assert payload["problem_description"] == "clients can't reach the internet"


@pytest.mark.asyncio
async def test_execution_summary_writes_execution_summary_render_kind(connected_session):
    from datetime import datetime, timezone
    from unittest.mock import Mock, patch

    from mika.ai.schemas.configuration_intents import CreateAddressIntent
    from mika.ai.schemas.enums import IntentName
    from mika.executor.confirmation import ConfirmationState, ConfirmationStatus

    intent = CreateAddressIntent(
        intent=IntentName.CREATE_ADDRESS,
        confidence=0.95,
        requires_confirmation=True,
        interface="ether3",
        address="192.168.20.1/24",
    )
    connected_session.provider.generate_intent = AsyncMock(return_value=intent)

    from mika.router.mock import MockRouterClient
    from mika.router.profile import RouterProfile

    connected_session.router_client = MockRouterClient(
        RouterProfile(
            system_resource={"board-name": "CHR", "version": "7.15.3", "architecture-name": "x86_64"},
            interfaces=[{".id": "*1", "name": "ether3", "type": "ether", "running": "true", "disabled": "false"}],
        )
    )

    confirmed = ConfirmationState(
        plan_id="whatever",
        status=ConfirmationStatus.CONFIRMED,
        confirmed_at=datetime.now(timezone.utc),
        confirmed_by="test",
    )
    with patch("mika.cli.repl.prompt_for_confirmation", Mock(return_value=confirmed)):
        await _handle_chat_turn("add address 192.168.20.1/24 on ether3", connected_session, Console(record=True))

    entries = _assistant_entries(connected_session)
    assert len(entries) == 1
    assert entries[0].render_kind == "execution_summary"
    payload = json.loads(entries[0].render_payload)
    assert set(payload) == {"plan_summary", "diff", "outcome"}


@pytest.mark.asyncio
async def test_ai_error_writes_error_render_kind(connected_session):
    from mika.ai.errors import AIError

    connected_session.provider.generate_intent = AsyncMock(side_effect=AIError("provider timed out"))

    await _handle_chat_turn("do something", connected_session, Console(record=True))

    entries = _assistant_entries(connected_session)
    assert len(entries) == 1
    assert entries[0].render_kind == "error"
    assert json.loads(entries[0].render_payload)["message"] == "provider timed out"
