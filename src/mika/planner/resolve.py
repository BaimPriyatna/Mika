"""
Resource resolution helper for MODIFY/DELETE planners.

CLAUDE.md Section 27: a resource_id carried on an intent must never be
trusted as-is -- RouterOS recycles .id values after deletion, so an id the
LLM saw in an earlier turn (or a stale plan) might now point at a
completely different object. Every modify/delete planner re-resolves the
id against a freshly-discovered RouterContext (discover() is called right
before planning, in repl.py) and fails clearly if it's no longer present,
rather than silently sending a possibly-wrong id to the executor.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, TypeVar

from mika.planner.errors import ResourceNotFoundError


class _HasId(Protocol):
    id: str


T = TypeVar("T", bound=_HasId)


def resolve_resource(collection: Sequence[T], resource_id: str, *, resource_kind: str) -> T:
    for item in collection:
        if item.id == resource_id:
            return item
    raise ResourceNotFoundError(
        f"No {resource_kind} with id '{resource_id}' exists on the router right "
        "now. It may have been deleted, or RouterOS may have reused this id for "
        "a different object since it was last seen -- re-inspect the router "
        "(e.g. /inspect) to get a current id before retrying (CLAUDE.md Section 27)."
    )
