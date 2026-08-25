from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from mika.ai import (
    AIAuthenticationError,
    AIContext,
    AIError,
    AIProviderError,
    AIRateLimitError,
    AISchemaError,
    AITimeoutError,
    GeminiProvider,
    LLMProvider,
)
from mika.ai.prompts.builder import build_system_prompt, build_user_prompt
from mika.ai.schemas import (
    IntentCategory,
    IntentName,
)
from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.destructive_intents import DeleteFirewallRuleIntent
from mika.ai.schemas.modification_intents import ModifyAddressIntent
from mika.ai.schemas.read_intents import InspectInterfacesIntent
from mika.knowledge.models import KnowledgeDocument, KnowledgeSource


def _make_gemini_response(
    status_code: int = 200,
    text: str | None = None,
    *,
    error: dict | None = None,
    prompt_feedback: dict | None = None,
    finish_reason: str = "STOP",
) -> httpx.Response:
    if error is not None:
        body = {"error": error}
    elif prompt_feedback is not None:
        body = {"promptFeedback": prompt_feedback}
    elif text is not None:
        body = {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": text}],
                        "role": "model",
                    },
                    "finishReason": finish_reason,
                }
            ]
        }
    else:
        body = {"candidates": []}

    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=json.dumps(body).encode(),
    )


def _patch_gemini_client(
    provider: GeminiProvider,
    responses: list[httpx.Response] | httpx.Response,
):
    if isinstance(responses, httpx.Response):
        responses = [responses]
    mock_post = AsyncMock(side_effect=responses)
    mock_httpx = MagicMock()
    mock_httpx.post = mock_post
    mock_httpx.aclose = AsyncMock()
    provider._client = mock_httpx
    return mock_post


class TestGeminiProviderInit:

    def test_implements_llm_provider_protocol(self):
        provider = GeminiProvider("test-key")
        assert isinstance(provider, LLMProvider)

    def test_empty_api_key_rejected(self):
        with pytest.raises(ValueError, match="api_key"):
            GeminiProvider("")

    def test_whitespace_api_key_rejected(self):
        with pytest.raises(ValueError, match="api_key"):
            GeminiProvider("   ")

    def test_empty_model_rejected(self):
        with pytest.raises(ValueError, match="model"):
            GeminiProvider("test-key", model="")

    @pytest.mark.asyncio
    async def test_empty_request_rejected(self):
        provider = GeminiProvider("test-key")
        with pytest.raises(ValueError, match="request"):
            await provider.generate_intent("")

    def test_custom_parameters(self):
        provider = GeminiProvider(
            "key123",
            model="gemini-1.5-pro",
            timeout=45.0,
            base_url="https://custom.api.com",
            verify_tls=False,
        )
        assert provider._api_key == "key123"
        assert provider._model == "gemini-1.5-pro"
        assert provider._timeout == 45.0
        assert provider._base_url == "https://custom.api.com"
        assert provider._verify_tls is False

    @pytest.mark.asyncio
    async def test_context_manager_and_aclose(self):
        async with GeminiProvider("test-key") as p:
            assert p._client is None
            client = p._get_client()
            assert client is not None
        assert p._client is None


class TestGeminiProviderGenerateIntent:

    @pytest.mark.asyncio
    async def test_generate_read_intent_success(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "inspect_interfaces",
            "confidence": 0.95,
            "requires_confirmation": False,
            "reasoning": "User asked to view interfaces",
            "interface": "ether1",
        })
        mock_post = _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        intent = await provider.generate_intent("show ether1 interface")

        assert isinstance(intent, InspectInterfacesIntent)
        assert intent.intent == IntentName.INSPECT_INTERFACES
        assert intent.category == IntentCategory.READ
        assert intent.requires_confirmation is False
        assert intent.interface == "ether1"
        assert intent.confidence == 0.95

        assert mock_post.await_count == 1
        call_kwargs = mock_post.call_args.kwargs
        assert "x-goog-api-key" in mock_post.call_args.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_generate_config_intent_success(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "create_hotspot",
            "confidence": 0.92,
            "requires_confirmation": True,
            "interface": "ether3",
            "network": "192.168.30.0/24",
            "rate_limit": "10M/10M",
            "reasoning": "Setting up hotspot on ether3",
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        intent = await provider.generate_intent("setup hotspot on ether3 with 192.168.30.0/24")

        assert isinstance(intent, CreateHotspotIntent)
        assert intent.intent == IntentName.CREATE_HOTSPOT
        assert intent.category == IntentCategory.CONFIGURATION
        assert intent.requires_confirmation is True
        assert intent.interface == "ether3"
        assert str(intent.network) == "192.168.30.0/24"
        assert intent.rate_limit == "10M/10M"

    @pytest.mark.asyncio
    async def test_generate_modification_intent_success(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "modify_address",
            "confidence": 0.88,
            "requires_confirmation": True,
            "resource_id": "*1A",
            "comment": "LAN gateway",
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        intent = await provider.generate_intent("update address *1A comment to LAN gateway")

        assert isinstance(intent, ModifyAddressIntent)
        assert intent.intent == IntentName.MODIFY_ADDRESS
        assert intent.resource_id == "*1A"
        assert intent.comment == "LAN gateway"

    @pytest.mark.asyncio
    async def test_generate_destructive_intent_success(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "delete_firewall_rule",
            "confidence": 0.99,
            "requires_confirmation": True,
            "resource_id": "*4F",
            "expected_description": "drop telnet rule",
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        intent = await provider.generate_intent("delete firewall rule *4F")

        assert isinstance(intent, DeleteFirewallRuleIntent)
        assert intent.intent == IntentName.DELETE_FIREWALL_RULE
        assert intent.resource_id == "*4F"

    @pytest.mark.asyncio
    async def test_strips_markdown_code_fence(self):
        provider = GeminiProvider("test-key")
        raw_text = "```json\n" + json.dumps({
            "intent": "inspect_interfaces",
            "confidence": 0.9,
            "requires_confirmation": False,
        }) + "\n```"
        _patch_gemini_client(provider, _make_gemini_response(text=raw_text))

        intent = await provider.generate_intent("list interfaces")
        assert isinstance(intent, InspectInterfacesIntent)


class TestGeminiProviderSchemaFailures:

    @pytest.mark.asyncio
    async def test_non_json_text_raises_ai_schema_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(provider, _make_gemini_response(text="I cannot help configure your router."))

        with pytest.raises(AISchemaError, match="Failed to parse LLM output as JSON") as exc_info:
            await provider.generate_intent("do something")
        assert exc_info.value.raw_output == "I cannot help configure your router."

    @pytest.mark.asyncio
    async def test_json_array_raises_ai_schema_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(provider, _make_gemini_response(text="[1, 2, 3]"))

        with pytest.raises(AISchemaError, match="Expected JSON object"):
            await provider.generate_intent("do something")

    @pytest.mark.asyncio
    async def test_unknown_intent_raises_ai_schema_error(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "format_router_drive",
            "confidence": 0.9,
            "requires_confirmation": True,
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        with pytest.raises(AISchemaError, match="failed Intent schema validation"):
            await provider.generate_intent("format drive")

    @pytest.mark.asyncio
    async def test_missing_required_fields_raises_ai_schema_error(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "create_hotspot",
            "confidence": 0.9,
            "requires_confirmation": True,
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        with pytest.raises(AISchemaError, match="failed Intent schema validation"):
            await provider.generate_intent("create hotspot")

    @pytest.mark.asyncio
    async def test_invented_extra_property_rejected(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "create_hotspot",
            "confidence": 0.9,
            "requires_confirmation": True,
            "interface": "ether3",
            "network": "192.168.10.0/24",
            "unauthorized_custom_backdoor": True,
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        with pytest.raises(AISchemaError, match="failed Intent schema validation"):
            await provider.generate_intent("create hotspot")

    @pytest.mark.asyncio
    async def test_empty_candidate_parts_raises_ai_schema_error(self):
        provider = GeminiProvider("test-key")
        resp = httpx.Response(
            status_code=200,
            headers={"content-type": "application/json"},
            content=json.dumps({"candidates": [{"content": {"parts": []}}]}).encode(),
        )
        _patch_gemini_client(provider, resp)

        with pytest.raises(AISchemaError, match="contains no content parts"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_no_candidates_raises_ai_provider_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(provider, _make_gemini_response(text=None))

        with pytest.raises(AIProviderError, match="no candidates"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_prompt_blocked_feedback_raises_ai_provider_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(
            provider,
            _make_gemini_response(prompt_feedback={"blockReason": "SAFETY"}),
        )

        with pytest.raises(AIProviderError, match="blocked prompt"):
            await provider.generate_intent("dangerous command")




    @pytest.mark.asyncio
    async def test_generate_intent_advise(self):
        provider = GeminiProvider("test-key")
        llm_json = json.dumps({
            "intent": "advise",
            "confidence": 0.95,
            "requires_confirmation": False,
            "message": "I recommend configuring ether3 with a 5M limit.",
            "options": ["1. Apply 5M limit", "2. Use 10M limit", "3. Enable trial"],
            "suggested_action": "create hotspot on ether3",
        })
        _patch_gemini_client(provider, _make_gemini_response(text=llm_json))

        intent = await provider.generate_intent("what is the best hotspot setup?")
        assert intent.intent == IntentName.ADVISE
        assert intent.message == "I recommend configuring ether3 with a 5M limit."
        assert len(intent.options) == 3


class TestGeminiProviderHttpErrors:

    @pytest.mark.asyncio
    async def test_401_unauthorized_raises_ai_authentication_error(self):
        provider = GeminiProvider("bad-key")
        _patch_gemini_client(
            provider,
            _make_gemini_response(
                status_code=401,
                error={"message": "API key not valid"},
            ),
        )

        with pytest.raises(AIAuthenticationError, match="authentication failed"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_403_forbidden_raises_ai_authentication_error(self):
        provider = GeminiProvider("bad-key")
        _patch_gemini_client(
            provider,
            _make_gemini_response(
                status_code=403,
                error={"message": "Permission denied"},
            ),
        )

        with pytest.raises(AIAuthenticationError, match="authentication failed"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_429_rate_limit_raises_ai_rate_limit_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(
            provider,
            _make_gemini_response(
                status_code=429,
                error={"message": "Resource has been exhausted"},
            ),
        )

        with pytest.raises(AIRateLimitError, match="rate limit or quota exceeded"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_500_server_error_raises_ai_provider_error(self):
        provider = GeminiProvider("test-key")
        _patch_gemini_client(
            provider,
            _make_gemini_response(
                status_code=500,
                error={"message": "Internal error"},
            ),
        )

        with pytest.raises(AIProviderError, match="returned error 500"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_timeout_raises_ai_timeout_error(self):
        provider = GeminiProvider("test-key", timeout=5.0)
        mock_httpx = MagicMock()
        mock_httpx.post = AsyncMock(side_effect=httpx.TimeoutException("Read timed out"))
        provider._client = mock_httpx

        with pytest.raises(AITimeoutError, match="timed out after 5.0s"):
            await provider.generate_intent("show interfaces")

    @pytest.mark.asyncio
    async def test_connection_error_raises_ai_provider_error(self):
        provider = GeminiProvider("test-key")
        mock_httpx = MagicMock()
        mock_httpx.post = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
        provider._client = mock_httpx

        with pytest.raises(AIProviderError, match="Failed to connect"):
            await provider.generate_intent("show interfaces")


class TestPromptBuilder:

    def test_system_prompt_contains_mandatory_rules(self):
        sp = build_system_prompt()
        assert "You do not execute commands" in sp
        assert "You do not invent RouterOS syntax" in sp
        assert "Prompt Injection Defense" in sp
        assert "<untrusted_router_data>" in sp
        assert "inspect_interfaces" in sp
        assert "create_hotspot" in sp

    def test_user_prompt_without_context(self):
        up = build_user_prompt("show routes")
        assert "<user_request>\nshow routes\n</user_request>" in up
        assert "<untrusted_router_data>" not in up

    def test_user_prompt_with_context(self):
        doc = KnowledgeDocument(
            id="routeros/v7/hotspot",
            topic="hotspot",
            routeros="7",
            source=KnowledgeSource.OFFICIAL_CURRENT,
            verified_at=date(2026, 1, 1),
            content="Hotspot setup requires interface and pool.",
            path=Path("routeros/v7/hotspot.md"),
        )
        ctx = AIContext(
            router_identity="RB5009-Core",
            routeros_version="7.14.3",
            interfaces=["ether1", "ether2", "ether3"],
            relevant_knowledge=[doc],
            safety_constraints=["Do not touch ether1 WAN"],
        )

        up = build_user_prompt("setup hotspot on ether3", ctx)

        assert "<untrusted_router_data>" in up
        assert "Router Identity: RB5009-Core" in up
        assert "RouterOS Version: 7.14.3" in up
        assert "Available Interfaces: ether1, ether2, ether3" in up
        assert "<relevant_knowledge>" in up
        assert "Hotspot setup requires interface and pool." in up
        assert "<safety_constraints>" in up
        assert "- Do not touch ether1 WAN" in up
        assert "<user_request>\nsetup hotspot on ether3\n</user_request>" in up
