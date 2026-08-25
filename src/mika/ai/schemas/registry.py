"""
Intent Schema Registry.

Maintains mappings between raw AI output strings and strongly-typed
Pydantic Intent models, categorized by safety levels (SAFE, MODIFICATION, DESTRUCTIVE).
"""

from __future__ import annotations

from typing import Annotated, Union

from pydantic import Field, TypeAdapter, ValidationError

from mika.ai.schemas.configuration_intents import CONFIGURATION_INTENTS
from mika.ai.schemas.destructive_intents import DESTRUCTIVE_INTENTS
from mika.ai.schemas.modification_intents import MODIFICATION_INTENTS
from mika.ai.schemas.read_intents import READ_INTENTS

ALL_INTENT_MODELS = READ_INTENTS + CONFIGURATION_INTENTS + MODIFICATION_INTENTS + DESTRUCTIVE_INTENTS

AnyIntent = Annotated[
    Union[ALL_INTENT_MODELS],
    Field(discriminator="intent"),
]

_adapter: TypeAdapter[AnyIntent] = TypeAdapter(AnyIntent)


class IntentValidationError(ValueError):

    def __init__(self, original: ValidationError):
        self.original = original
        super().__init__(str(original))


def parse_intent(raw: dict) -> AnyIntent:

    try:
        return _adapter.validate_python(raw)
    except ValidationError as exc:
        raise IntentValidationError(exc) from exc


__all__ = ["AnyIntent", "ALL_INTENT_MODELS", "IntentValidationError", "parse_intent"]
