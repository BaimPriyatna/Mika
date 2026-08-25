import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mika.memory import Fact, FactCategory, MemoryStorage


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path
    
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def storage(temp_db):
    return MemoryStorage(temp_db)


def test_storage_initialization(temp_db):
    storage = MemoryStorage(temp_db)
    assert temp_db.exists()


def test_add_fact(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    fact_id = storage.add(fact)
    assert fact_id > 0


def test_add_duplicate_key_updates(storage):
    fact1 = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    id1 = storage.add(fact1)
    
    fact2 = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="1.1.1.1",
        description="Updated DNS server",
        source="test",
    )
    
    id2 = storage.add(fact2)
    
    assert id1 == id2
    
    entry = storage.get("default_dns")
    assert entry is not None
    assert entry.fact.value == "1.1.1.1"
    assert entry.fact.description == "Updated DNS server"


def test_get_fact(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    storage.add(fact)
    
    entry = storage.get("default_dns")
    assert entry is not None
    assert entry.fact.key == "default_dns"
    assert entry.fact.value == "8.8.8.8"
    assert entry.fact.category == FactCategory.NETWORK_PREFERENCE


def test_get_nonexistent_fact(storage):
    entry = storage.get("nonexistent")
    assert entry is None


def test_list_all_facts(storage):
    facts = [
        Fact(
            category=FactCategory.NETWORK_PREFERENCE,
            key="dns1",
            value="8.8.8.8",
            description="DNS 1",
            source="test",
        ),
        Fact(
            category=FactCategory.SECURITY_POLICY,
            key="block_ssh",
            value=True,
            description="Block SSH from WAN",
            source="test",
        ),
    ]
    
    for fact in facts:
        storage.add(fact)
    
    entries = storage.list_all()
    assert len(entries) == 2


def test_list_by_category(storage):
    storage.add(Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    ))
    
    storage.add(Fact(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH",
        source="test",
    ))
    
    network_entries = storage.list_all(category=FactCategory.NETWORK_PREFERENCE)
    assert len(network_entries) == 1
    assert network_entries[0].fact.category == FactCategory.NETWORK_PREFERENCE


def test_list_by_router(storage):
    storage.add(Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
        router_specific=True,
        router_id="router1",
    ))
    
    storage.add(Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns2",
        value="1.1.1.1",
        description="DNS 2",
        source="test",
        router_specific=False,
    ))
    
    storage.add(Fact(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH",
        source="test",
        router_specific=True,
        router_id="router2",
    ))
    
    router1_entries = storage.list_all(router_id="router1")
    assert len(router1_entries) == 2
    
    router2_entries = storage.list_all(router_id="router2")
    assert len(router2_entries) == 2


def test_delete_fact(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    storage.add(fact)
    
    assert storage.get("dns1") is not None
    
    success = storage.delete("dns1")
    assert success is True
    
    assert storage.get("dns1") is None


def test_delete_nonexistent(storage):
    success = storage.delete("nonexistent")
    assert success is False


def test_deactivate_fact(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    storage.add(fact)
    
    success = storage.deactivate("dns1")
    assert success is True
    
    entry = storage.get("dns1")
    assert entry is not None
    assert entry.active is False
    
    active_entries = storage.list_all(active_only=True)
    assert len(active_entries) == 0
    
    all_entries = storage.list_all(active_only=False)
    assert len(all_entries) == 1


def test_record_access(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    storage.add(fact)
    
    entry = storage.get("dns1")
    assert entry.fact.access_count == 0
    
    storage.record_access("dns1")
    
    entry = storage.get("dns1")
    assert entry.fact.access_count == 1
    
    storage.record_access("dns1")
    storage.record_access("dns1")
    
    entry = storage.get("dns1")
    assert entry.fact.access_count == 3


def test_clear_all(storage):
    for i in range(3):
        storage.add(Fact(
            category=FactCategory.NETWORK_PREFERENCE,
            key=f"dns{i}",
            value=f"8.8.8.{i}",
            description=f"DNS {i}",
            source="test",
        ))
    
    assert len(storage.list_all()) == 3
    
    deleted = storage.clear_all()
    assert deleted == 3
    
    assert len(storage.list_all()) == 0


def test_clear_by_router(storage):
    storage.add(Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
        router_specific=True,
        router_id="router1",
    ))
    
    storage.add(Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns2",
        value="1.1.1.1",
        description="DNS 2",
        source="test",
        router_specific=True,
        router_id="router2",
    ))
    
    deleted = storage.clear_all(router_id="router1")
    assert deleted == 1
    
    assert storage.get("dns1") is None
    assert storage.get("dns2") is not None


def test_memory_expiration(storage):
    fact = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="temp_dns",
        value="8.8.8.8",
        description="Temporary DNS",
        source="test",
    )
    
    fact_id = storage.add(fact)
    
    import sqlite3
    with sqlite3.connect(storage.db_path) as conn:
        past_time = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        conn.execute(
            "UPDATE memory SET expires_at = ? WHERE id = ?",
            (past_time, fact_id)
        )
        conn.commit()
    
    entry = storage.get("temp_dns")
    assert entry is not None
    assert entry.is_expired() is True
    assert entry.is_valid() is False


def test_complex_value_types(storage):
    fact_dict = Fact(
        category=FactCategory.NETWORK_PREFERENCE,
        key="vlans",
        value={"10": "management", "20": "guest", "30": "iot"},
        description="VLAN mapping",
        source="test",
    )
    
    storage.add(fact_dict)
    entry = storage.get("vlans")
    assert entry is not None
    assert isinstance(entry.fact.value, dict)
    assert entry.fact.value["10"] == "management"
    
    fact_list = Fact(
        category=FactCategory.SECURITY_POLICY,
        key="blocked_ports",
        value=[22, 23, 3389],
        description="Blocked ports",
        source="test",
    )
    
    storage.add(fact_list)
    entry = storage.get("blocked_ports")
    assert entry is not None
    assert isinstance(entry.fact.value, list)
    assert 22 in entry.fact.value
