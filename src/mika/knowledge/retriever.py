"""
Knowledge Base Retriever.

Retrieves relevant MikroTik documentation, configuration guides, and
best practices to ground AI responses in accurate RouterOS syntax.
"""

from __future__ import annotations

from dataclasses import dataclass

from mika.knowledge.models import SOURCE_PRIORITY, KnowledgeDocument


@dataclass(frozen=True)
class RetrievalResult:

    topic: str
    documents: tuple[KnowledgeDocument, ...]
    version_uncertain: bool

    @property
    def is_empty(self) -> bool:
        return len(self.documents) == 0


class KnowledgeRetriever:

    def __init__(self, documents: list[KnowledgeDocument]) -> None:
        self._documents = list(documents)
        self._by_topic: dict[str, list[KnowledgeDocument]] = {}
        for document in self._documents:
            key = document.topic.strip().lower()
            self._by_topic.setdefault(key, []).append(document)

    def available_topics(self) -> set[str]:
        return set(self._by_topic)

    def retrieve(self, topic: str, *, routeros_major: int | None = None) -> RetrievalResult:
        key = topic.strip().lower()
        candidates = self._by_topic.get(key, [])

        if routeros_major is None:
            ranked = sorted(candidates, key=lambda doc: SOURCE_PRIORITY[doc.source])
            return RetrievalResult(topic=topic, documents=tuple(ranked), version_uncertain=False)

        matching = [
            doc
            for doc in candidates
            if doc.routeros_major is None or doc.routeros_major == routeros_major
        ]
        version_uncertain = len(matching) == 0 and len(candidates) > 0

        ranked = sorted(
            matching,
            key=lambda doc: (
                SOURCE_PRIORITY[doc.source],
                0 if doc.routeros_major == routeros_major else 1,
            ),
        )
        return RetrievalResult(topic=topic, documents=tuple(ranked), version_uncertain=version_uncertain)

    def retrieve_many(
        self, topics: list[str], *, routeros_major: int | None = None
    ) -> list[RetrievalResult]:
        return [self.retrieve(topic, routeros_major=routeros_major) for topic in topics]
