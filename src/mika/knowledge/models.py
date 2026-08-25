from __future__ import annotations

from datetime import date
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSource(str, Enum):

    OFFICIAL_CURRENT = "official_current"
    OFFICIAL_VERSION_SPECIFIC = "official_version_specific"
    VERIFIED_PROJECT_TEST = "verified_project_test"
    COMMUNITY = "community"


SOURCE_PRIORITY: dict[KnowledgeSource, int] = {
    KnowledgeSource.OFFICIAL_CURRENT: 0,
    KnowledgeSource.OFFICIAL_VERSION_SPECIFIC: 1,
    KnowledgeSource.VERIFIED_PROJECT_TEST: 2,
    KnowledgeSource.COMMUNITY: 3,
}

RouterOSScope = Literal["6", "7", "any"]


class KnowledgeDocument(BaseModel):

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        description="Stable identifier derived from the file's path relative "
        "to the knowledge root, e.g. 'routeros/v7/firewall'. Used for "
        "source attribution (Section 75) and de-duplication."
    )
    topic: str = Field(
        min_length=1,
        description="Single canonical topic tag, e.g. 'firewall', 'hotspot', "
        "'dhcp', 'vlan'. Retrieval matches on this field, not free-text "
        "search over the body (Section 19: retrieve only relevant "
        "knowledge, per-topic, not a full-text dump).",
    )
    routeros: RouterOSScope = Field(
        description="'6' or '7' for version-scoped documents, 'any' for "
        "version-agnostic ones (CLAUDE.md Section 17)."
    )
    source: KnowledgeSource
    verified_at: date = Field(
        description="Date this document was last checked against its "
        "source (Section 57/58). Not a guarantee the underlying RouterOS "
        "behavior hasn't changed since -- that judgment stays with the "
        "caller/human, this is just the recorded fact."
    )
    content: str = Field(description="Markdown body, frontmatter stripped.")
    path: Path = Field(
        description="Path to the source file, relative to the knowledge root."
    )

    @property
    def routeros_major(self) -> int | None:
        return None if self.routeros == "any" else int(self.routeros)
