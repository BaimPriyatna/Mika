from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from mika.ai.errors import (
    AIAuthenticationError,
    AIProviderError,
    AIRateLimitError,
    AITimeoutError,
)
from mika.ai.providers.gemini import list_models


def _response(status_code: int, body: dict) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        headers={"content-type": "application/json"},
        content=json.dumps(body).encode(),
    )


def _patch_client(responses: list[httpx.Response] | httpx.Response):
    if isinstance(responses, httpx.Response):
        responses = [responses]
    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=responses)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return patch("mika.ai.providers.gemini.httpx.AsyncClient", return_value=mock_client), mock_client


class TestListModels:
    @pytest.mark.asyncio
    async def test_empty_api_key_rejected(self):
        with pytest.raises(ValueError, match="api_key"):
            await list_models("")

    @pytest.mark.asyncio
    async def test_filters_to_generate_content_models_and_strips_prefix(self):
        body = {
            "models": [
                {"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]},
                {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
            ]
        }
        patcher, mock_client = _patch_client(_response(200, body))
        with patcher:
            models = await list_models("real-key")

        assert models == ["gemini-1.5-flash", "gemini-1.5-pro"]
        _, kwargs = mock_client.get.call_args
        assert kwargs["headers"]["x-goog-api-key"] == "real-key"

    @pytest.mark.asyncio
    async def test_paginates_until_no_next_page_token(self):
        page1 = _response(
            200,
            {
                "models": [{"name": "models/gemini-1.5-flash", "supportedGenerationMethods": ["generateContent"]}],
                "nextPageToken": "abc",
            },
        )
        page2 = _response(
            200,
            {"models": [{"name": "models/gemini-1.5-pro", "supportedGenerationMethods": ["generateContent"]}]},
        )
        patcher, mock_client = _patch_client([page1, page2])
        with patcher:
            models = await list_models("real-key")

        assert models == ["gemini-1.5-flash", "gemini-1.5-pro"]
        assert mock_client.get.call_count == 2

    @pytest.mark.asyncio
    async def test_401_raises_authentication_error(self):
        patcher, _ = _patch_client(_response(401, {"error": {"message": "API key not valid"}}))
        with patcher, pytest.raises(AIAuthenticationError):
            await list_models("bad-key")

    @pytest.mark.asyncio
    async def test_403_raises_authentication_error(self):
        patcher, _ = _patch_client(_response(403, {"error": {"message": "forbidden"}}))
        with patcher, pytest.raises(AIAuthenticationError):
            await list_models("bad-key")

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self):
        patcher, _ = _patch_client(_response(429, {"error": {"message": "quota exceeded"}}))
        with patcher, pytest.raises(AIRateLimitError):
            await list_models("real-key")

    @pytest.mark.asyncio
    async def test_5xx_raises_provider_error(self):
        patcher, _ = _patch_client(_response(500, {"error": {"message": "internal"}}))
        with patcher, pytest.raises(AIProviderError):
            await list_models("real-key")

    @pytest.mark.asyncio
    async def test_no_generate_content_models_raises_provider_error(self):
        body = {"models": [{"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]}]}
        patcher, _ = _patch_client(_response(200, body))
        with patcher, pytest.raises(AIProviderError):
            await list_models("real-key")

    @pytest.mark.asyncio
    async def test_timeout_raises_ai_timeout_error(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("mika.ai.providers.gemini.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AITimeoutError):
                await list_models("real-key")

    @pytest.mark.asyncio
    async def test_connect_error_raises_provider_error(self):
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("no route"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with patch("mika.ai.providers.gemini.httpx.AsyncClient", return_value=mock_client):
            with pytest.raises(AIProviderError):
                await list_models("real-key")
