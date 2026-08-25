"""
AI Provider Interface.

Defines the base contract for LLM backends (e.g. Gemini, OpenAI) to
generate structured intent schemas and conversational assistance.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from mika.ai.context import AIContext
from mika.ai.schemas import AnyIntent


@runtime_checkable
class LLMProvider(Protocol):

    async def generate_intent(
        self,
        request: str,
        context: AIContext | None = None,
    ) -> AnyIntent:
        ...
