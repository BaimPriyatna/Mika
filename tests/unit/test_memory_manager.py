import tempfile
from pathlib import Path

import pytest

from mika.memory import Fact, FactCategory, MemoryManager


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    
    yield db_path
    
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def manager(temp_db):
    return MemoryManager.from_path(temp_db)


def test_manager_initialization(temp_db):
    manager = MemoryManager.from_path(temp_db)
    assert manager is not None
    assert manager.storage is not None


def test_remember_fact(manager):
    fact_id = manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    assert fact_id > 0


def test_recall_fact(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    fact = manager.recall("default_dns")
    assert fact is not None
    assert fact.key == "default_dns"
    assert fact.value == "8.8.8.8"


def test_recall_nonexistent(manager):
    fact = manager.recall("nonexistent")
    assert fact is None


def test_forget_fact(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
        source="test",
    )
    
    success = manager.forget("default_dns")
    assert success is True
    
    fact = manager.recall("default_dns")
    assert fact is None


def test_get_context_global(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    manager.remember(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH from WAN",
        source="test",
    )
    
    context = manager.get_context()
    assert len(context.facts) == 2
    assert context.router_id is None


def test_get_context_router_specific(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
        router_specific=False,
    )
    
    manager.remember(
        category=FactCategory.INTERFACE_PROTECTION,
        key="wan_interface_r1",
        value="ether1",
        description="WAN interface",
        source="test",
        router_specific=True,
        router_id="router1",
    )
    
    manager.remember(
        category=FactCategory.INTERFACE_PROTECTION,
        key="wan_interface_r2",
        value="ether2",
        description="WAN interface",
        source="test",
        router_specific=True,
        router_id="router2",
    )
    
    context = manager.get_context(router_id="router1")
    assert len(context.facts) == 2
    assert context.router_id == "router1"
    
    context = manager.get_context(router_id="router2")
    assert len(context.facts) == 2


def test_get_context_with_category_filter(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    manager.remember(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH",
        source="test",
    )
    
    context = manager.get_context(
        categories=[FactCategory.NETWORK_PREFERENCE]
    )
    assert len(context.facts) == 1
    assert context.facts[0].category == FactCategory.NETWORK_PREFERENCE


def test_remember_network_preference(manager):
    manager.remember_network_preference(
        key="default_gateway",
        value="192.168.1.1",
        description="Default gateway",
    )
    
    fact = manager.recall("default_gateway")
    assert fact is not None
    assert fact.category == FactCategory.NETWORK_PREFERENCE


def test_remember_interface_protection(manager):
    manager.remember_interface_protection(
        interface="ether1",
        reason="WAN interface, do not modify",
    )
    
    fact = manager.recall("protected_interface_ether1")
    assert fact is not None
    assert fact.category == FactCategory.INTERFACE_PROTECTION
    assert fact.value == "ether1"


def test_remember_security_policy(manager):
    manager.remember_security_policy(
        key="block_telnet",
        value=True,
        description="Always block telnet",
    )
    
    fact = manager.recall("block_telnet")
    assert fact is not None
    assert fact.category == FactCategory.SECURITY_POLICY


def test_remember_default_value(manager):
    manager.remember_default_value(
        key="hotspot_rate_limit",
        value="5M/5M",
        description="Default hotspot rate limit",
    )
    
    fact = manager.recall("hotspot_rate_limit")
    assert fact is not None
    assert fact.category == FactCategory.DEFAULT_VALUE


def test_get_protected_interfaces(manager):
    manager.remember_interface_protection("ether1", "WAN")
    manager.remember_interface_protection("ether2", "Management")
    
    protected = manager.get_protected_interfaces()
    assert len(protected) == 2
    assert "ether1" in protected
    assert "ether2" in protected


def test_is_interface_protected(manager):
    manager.remember_interface_protection("ether1", "WAN")
    
    assert manager.is_interface_protected("ether1") is True
    assert manager.is_interface_protected("ether2") is False


def test_is_interface_protected_router_specific(manager):
    manager.remember_interface_protection(
        interface="ether1",
        reason="WAN",
        router_id="router1",
    )
    
    assert manager.is_interface_protected("ether1", router_id="router1") is True
    
    assert manager.is_interface_protected("ether1", router_id="router2") is False


def test_list_memories(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    manager.remember(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH",
        source="test",
    )
    
    memories = manager.list_memories()
    assert len(memories) == 2


def test_clear_all(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    deleted = manager.clear_all()
    assert deleted == 1
    
    memories = manager.list_memories()
    assert len(memories) == 0


def test_memory_context_to_prompt_text(manager):
    manager.remember_network_preference(
        key="default_dns",
        value="8.8.8.8",
        description="Default DNS server",
    )
    
    manager.remember_interface_protection(
        interface="ether1",
        reason="WAN interface",
    )
    
    context = manager.get_context()
    prompt_text = context.to_prompt_text()
    
    assert "User Preferences and Context" in prompt_text
    assert "Network Preference" in prompt_text
    assert "Interface Protection" in prompt_text
    assert "8.8.8.8" in prompt_text
    assert "ether1" in prompt_text


def test_memory_context_get_by_key(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    context = manager.get_context()
    fact = context.get_by_key("dns1")
    
    assert fact is not None
    assert fact.value == "8.8.8.8"


def test_memory_context_get_by_category(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns2",
        value="1.1.1.1",
        description="DNS 2",
        source="test",
    )
    
    manager.remember(
        category=FactCategory.SECURITY_POLICY,
        key="block_ssh",
        value=True,
        description="Block SSH",
        source="test",
    )
    
    context = manager.get_context()
    network_facts = context.get_by_category(FactCategory.NETWORK_PREFERENCE)
    
    assert len(network_facts) == 2


def test_recall_records_access(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    entry = manager.storage.get("dns1")
    initial_count = entry.fact.access_count
    
    manager.recall("dns1")
    
    entry = manager.storage.get("dns1")
    assert entry.fact.access_count == initial_count + 1


def test_get_context_records_access(manager):
    manager.remember(
        category=FactCategory.NETWORK_PREFERENCE,
        key="dns1",
        value="8.8.8.8",
        description="DNS 1",
        source="test",
    )
    
    manager.get_context()
    
    entry = manager.storage.get("dns1")
    assert entry.fact.access_count > 0
