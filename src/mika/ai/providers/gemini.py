"""
Google Gemini AI Provider.

Implements the AIProvider interface using Google GenAI SDK.
Supports structured JSON generation for intent extraction and streaming chat responses.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from mika.ai.context import AIContext
from mika.ai.errors import (
    AIAuthenticationError,
    AIError,
    AIProviderError,
    AIRateLimitError,
    AISchemaError,
    AITimeoutError,
)
from mika.ai.prompts.builder import build_system_prompt, build_user_prompt
from mika.ai.schemas import AnyIntent, IntentValidationError, parse_intent
from mika.cli.wizard import register_model_fetcher

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-1.5-flash"
_DEFAULT_TIMEOUT = 30.0
_BASE_URL = "https://generativelanguage.googleapis.com"
_LIST_MODELS_PAGE_SIZE = 100


@register_model_fetcher("gemini", display_name="Google Gemini")
async def list_models(
    api_key: str,
    *,
    timeout: float = _DEFAULT_TIMEOUT,
    base_url: str = _BASE_URL,
    verify_tls: bool = True,
) -> list[str]:
    if not api_key or not api_key.strip():
        raise ValueError("api_key must not be empty")

    key = api_key.strip()
    url = f"{base_url.rstrip('/')}/v1beta/models"
    headers = {"x-goog-api-key": key}

    names: list[str] = []
    page_token: str | None = None

    async with httpx.AsyncClient(verify=verify_tls, timeout=timeout) as client:
        while True:
            params: dict[str, Any] = {"pageSize": _LIST_MODELS_PAGE_SIZE}
            if page_token:
                params["pageToken"] = page_token

            try:
                response = await client.get(url, headers=headers, params=params)
            except httpx.TimeoutException as exc:
                raise AITimeoutError(f"Gemini ListModels request timed out after {timeout}s") from exc
            except httpx.ConnectError as exc:
                raise AIProviderError(f"Failed to connect to Gemini API: {exc}") from exc
            except httpx.RequestError as exc:
                raise AIProviderError(f"Gemini ListModels network error: {exc}") from exc

            _check_list_models_status(response)

            try:
                data = response.json()
            except Exception as exc:
                raise AIProviderError(
                    f"Non-JSON response from Gemini ListModels endpoint: {response.text[:200]}"
                ) from exc

            for model in data.get("models", []):
                methods = model.get("supportedGenerationMethods") or []
                if "generateContent" not in methods:
                    continue
                raw_name = model.get("name", "")
                short_name = raw_name.removeprefix("models/")
                if short_name:
                    names.append(short_name)

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    if not names:
        raise AIProviderError(
            "Gemini API key is valid, but no models supporting generateContent were found."
        )

    return sorted(set(names))


def _check_list_models_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == 200:
        return

    detail = ""
    try:
        body = response.json()
        error_obj = body.get("error", {})
        if isinstance(error_obj, dict):
            detail = error_obj.get("message", "") or str(error_obj)
        else:
            detail = str(error_obj)
    except Exception:
        detail = response.text[:200]

    if status in (401, 403):
        raise AIAuthenticationError(
            f"Gemini authentication failed (HTTP {status}): {detail}",
            status_code=status,
            details=detail,
        )
    if status == 429:
        raise AIRateLimitError(
            f"Gemini rate limit or quota exceeded (HTTP 429): {detail}",
            status_code=status,
            details=detail,
        )
    raise AIProviderError(
        f"Gemini API returned error {status}: {detail}",
        status_code=status,
        details=detail,
    )


class GeminiProvider:

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
        base_url: str = _BASE_URL,
        verify_tls: bool = True,
    ) -> None:
        if not api_key or not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model or not model.strip():
            raise ValueError("model must not be empty")

        self._api_key = api_key.strip()
        self._model = model.strip()
        self._timeout = timeout
        self._base_url = base_url.rstrip("/")
        self._verify_tls = verify_tls
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "GeminiProvider":
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=self._verify_tls,
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
        return self._client

    async def generate_intent(
        self,
        request: str,
        context: AIContext | None = None,
    ) -> AnyIntent:
        if not request or not request.strip():
            raise ValueError("request must not be empty")

        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(request.strip(), context)

        payload = {
            "system_instruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        }

        url = f"{self._base_url}/v1beta/models/{self._model}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        client = self._get_client()

        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise AITimeoutError(
                f"Gemini request timed out after {self._timeout}s"
            ) from exc
        except httpx.ConnectError as exc:
            raise AIProviderError(
                f"Failed to connect to Gemini API: {exc}"
            ) from exc
        except httpx.RequestError as exc:
            raise AIProviderError(
                f"Gemini request network error: {exc}"
            ) from exc

        self._check_status_code(response, url)

        try:
            data = response.json()
        except Exception as exc:
            raise AIProviderError(
                f"Non-JSON response from Gemini endpoint: {response.text[:200]}"
            ) from exc

        raw_text = self._extract_text_from_response(data)
        return self._parse_and_validate_intent(raw_text)

    def _check_status_code(self, response: httpx.Response, url: str) -> None:
        _check_list_models_status(response)

    def _extract_text_from_response(self, data: dict[str, Any]) -> str:
        candidates = data.get("candidates")
        if not candidates or not isinstance(candidates, list):
            feedback = data.get("promptFeedback")
            if feedback:
                raise AIProviderError(
                    f"Gemini blocked prompt: {feedback}",
                    details=feedback,
                )
            raise AIProviderError(
                "Gemini returned no candidates in response",
                details=data,
            )

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason")
        if finish_reason and finish_reason not in ("STOP", None):
            logger.warning("Gemini finished with reason: %s", finish_reason)

        content = candidate.get("content", {})
        parts = content.get("parts", [])
        if not parts:
            raise AISchemaError(
                "Gemini candidate contains no content parts",
                raw_output=str(data),
            )

        text = parts[0].get("text", "")
        if not text.strip():
            raise AISchemaError(
                "Gemini returned empty text in candidate content",
                raw_output=str(data),
            )
        return text

    def _parse_and_validate_intent(self, text: str) -> AnyIntent:
        clean_text = text.strip()
        if clean_text.startswith("```"):
            clean_text = re.sub(r"^```(?:json)?\s*", "", clean_text)
            clean_text = re.sub(r"\s*```$", "", clean_text)
            clean_text = clean_text.strip()

        try:
            raw_dict = json.loads(clean_text)
        except json.JSONDecodeError as exc:
            raise AISchemaError(
                f"Failed to parse LLM output as JSON: {exc}",
                raw_output=text,
                cause=exc,
            ) from exc

        if not isinstance(raw_dict, dict):
            raise AISchemaError(
                f"Expected JSON object from LLM, got {type(raw_dict).__name__}",
                raw_output=text,
            )

        try:
            return parse_intent(raw_dict)
        except IntentValidationError as exc:
            raise AISchemaError(
                f"LLM output failed Intent schema validation: {exc}",
                raw_output=text,
                cause=exc,
            ) from exc
