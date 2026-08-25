"""
Contextual Memory Manager.

Manages short-term session context and long-term learned facts about the
network environment (e.g. custom VLAN IDs, topology notes).
"""

from pathlib import Path
from typing import Any, Optional

from .models import Fact, FactCategory, MemoryContext, MemoryEntry
from .storage import MemoryStorage


class MemoryManager:

    def __init__(self, storage: MemoryStorage):
        self.storage = storage

    @classmethod
    def from_path(cls, db_path: Path | str) -> "MemoryManager":
        storage = MemoryStorage(db_path)
        return cls(storage)

    def remember(
        self,
        category: FactCategory,
        key: str,
        value: Any,
        description: str,
        source: str = "explicit",
        confidence: float = 1.0,
        router_specific: bool = False,
        router_id: Optional[str] = None,
    ) -> int:
        fact = Fact(
            category=category,
            key=key,
            value=value,
            description=description,
            source=source,
            confidence=confidence,
            router_specific=router_specific,
            router_id=router_id,
        )
        return self.storage.add(fact)

    def forget(self, key: str) -> bool:
        return self.storage.delete(key)

    def recall(self, key: str) -> Optional[Fact]:
        entry = self.storage.get(key)
        if entry and entry.is_valid():
            self.storage.record_access(key)
            return entry.fact
        return None

    def get_context(
        self,
        router_id: Optional[str] = None,
        categories: Optional[list[FactCategory]] = None,
    ) -> MemoryContext:
        entries = self.storage.list_all(router_id=router_id, active_only=True)

        if categories:
            entries = [e for e in entries if e.fact.category in categories]

        facts = []
        for entry in entries:
            if entry.is_valid():
                facts.append(entry.fact)
                self.storage.record_access(entry.fact.key)

        return MemoryContext(facts=facts, router_id=router_id)

    def list_memories(
        self,
        category: Optional[FactCategory] = None,
        router_id: Optional[str] = None,
        active_only: bool = True,
    ) -> list[MemoryEntry]:
        return self.storage.list_all(
            category=category,
            router_id=router_id,
            active_only=active_only,
        )

    def clear_all(self, router_id: Optional[str] = None) -> int:
        return self.storage.clear_all(router_id=router_id)

    def remember_network_preference(
        self,
        key: str,
        value: Any,
        description: str,
        router_id: Optional[str] = None,
    ) -> int:
        return self.remember(
            category=FactCategory.NETWORK_PREFERENCE,
            key=key,
            value=value,
            description=description,
            router_specific=router_id is not None,
            router_id=router_id,
        )

    def remember_interface_protection(
        self,
        interface: str,
        reason: str,
        router_id: Optional[str] = None,
    ) -> int:
        return self.remember(
            category=FactCategory.INTERFACE_PROTECTION,
            key=f"protected_interface_{interface}",
            value=interface,
            description=f"Interface {interface} is protected: {reason}",
            router_specific=router_id is not None,
            router_id=router_id,
        )

    def remember_security_policy(
        self,
        key: str,
        value: Any,
        description: str,
        router_id: Optional[str] = None,
    ) -> int:
        return self.remember(
            category=FactCategory.SECURITY_POLICY,
            key=key,
            value=value,
            description=description,
            router_specific=router_id is not None,
            router_id=router_id,
        )

    def remember_default_value(
        self,
        key: str,
        value: Any,
        description: str,
        router_id: Optional[str] = None,
    ) -> int:
        return self.remember(
            category=FactCategory.DEFAULT_VALUE,
            key=key,
            value=value,
            description=description,
            router_specific=router_id is not None,
            router_id=router_id,
        )

    def get_protected_interfaces(
        self,
        router_id: Optional[str] = None,
    ) -> list[str]:
        context = self.get_context(
            router_id=router_id,
            categories=[FactCategory.INTERFACE_PROTECTION],
        )
        return [fact.value for fact in context.facts]

    def is_interface_protected(
        self,
        interface: str,
        router_id: Optional[str] = None,
    ) -> bool:
        key = f"protected_interface_{interface}"
        fact = self.recall(key)
        if fact is None:
            return False

        if fact.router_specific and fact.router_id != router_id:
            return False

        return True
