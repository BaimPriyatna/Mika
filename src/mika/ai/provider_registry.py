"""
AI Provider Registry.

Deliberately dependency-free (only stdlib + questionary) so that both
mika.ai.providers.* (e.g. gemini.py, which registers its fetcher here via
the decorator) and mika.cli.wizard (which reads the registry to build the
provider picker) can import this module without creating a circular
import between them.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import questionary

_PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    "gemini": "Google Gemini",
    "openai": "OpenAI (coming soon)",
    "local": "Local model (coming soon)",
}

_MODEL_FETCHERS: dict[str, Callable[[str], Awaitable[list[str]]]] = {}


def register_model_fetcher(provider: str, display_name: str | None = None) -> Callable:
    """Register a provider's model fetcher.

    A provider is only ever selectable in the wizard if it has a fetcher
    registered here -- there is no separate "available" flag to fall out of
    sync. `display_name` is optional; if omitted, an existing entry in
    `_PROVIDER_DISPLAY_NAMES` (or the raw provider key) is used.
    """

    def decorator(fn: Callable[[str], Awaitable[list[str]]]) -> Callable:
        _MODEL_FETCHERS[provider] = fn
        if display_name:
            _PROVIDER_DISPLAY_NAMES[provider] = display_name
        else:
            _PROVIDER_DISPLAY_NAMES.setdefault(provider, provider)
        return fn

    return decorator


def provider_choices() -> list[questionary.Choice]:
    """Build the provider picker choices. A provider is selectable if and
    only if it has a registered model fetcher -- this makes it structurally
    impossible for the picker to offer a provider whose fetcher is missing."""
    return [
        questionary.Choice(
            title=label,
            value=key,
            disabled=None if key in _MODEL_FETCHERS else "coming soon",
        )
        for key, label in _PROVIDER_DISPLAY_NAMES.items()
    ]
