import pytest
from pydantic import ValidationError

from mika.ai.schemas import IntentCategory, IntentName, SafetyLevel, parse_intent
from mika.ai.schemas.registry import IntentValidationError
from mika.ai.schemas.configuration_intents import CreateHotspotIntent
from mika.ai.schemas.destructive_intents import DeleteFirewallRuleIntent
from mika.ai.schemas.modification_intents import ModifyAddressIntent
from mika.ai.schemas.read_intents import InspectInterfacesIntent


def test_read_intent_valid():
    intent = InspectInterfacesIntent(confidence=0.9, requires_confirmation=False)
    assert intent.category == IntentCategory.READ
    assert intent.safety_level == SafetyLevel.READ_ONLY
    assert intent.interface is None


def test_read_intent_rejects_requires_confirmation_true():
    with pytest.raises(ValidationError):
        InspectInterfacesIntent(confidence=0.9, requires_confirmation=True)


def test_create_hotspot_valid():
    intent = CreateHotspotIntent(
        confidence=0.93,
        requires_confirmation=True,
        interface="ether3",
        network="192.168.20.0/24",
        rate_limit="5M/5M",
    )
    assert intent.category == IntentCategory.CONFIGURATION
    assert str(intent.network) == "192.168.20.0/24"


def test_create_hotspot_rejects_requires_confirmation_false():
    with pytest.raises(ValidationError):
        CreateHotspotIntent(
            confidence=0.93,
            requires_confirmation=False,
            interface="ether3",
            network="192.168.20.0/24",
        )


def test_create_hotspot_rejects_bad_network():
    with pytest.raises(ValidationError):
        CreateHotspotIntent(
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="not-a-subnet",
        )


def test_create_hotspot_rejects_shell_metacharacters_in_interface():
    with pytest.raises(ValidationError):
        CreateHotspotIntent(
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3; rm -rf /",
            network="192.168.20.0/24",
        )


def test_create_hotspot_rejects_bad_rate_limit():
    with pytest.raises(ValidationError):
        CreateHotspotIntent(
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
            rate_limit="fast please",
        )


def test_extra_fields_are_rejected():
    with pytest.raises(ValidationError):
        CreateHotspotIntent(
            confidence=0.9,
            requires_confirmation=True,
            interface="ether3",
            network="192.168.20.0/24",
            totally_made_up_field="oops",
        )


def test_modify_address_valid():
    intent = ModifyAddressIntent(
        confidence=0.8,
        requires_confirmation=True,
        resource_id="*3F",
        comment="updated by AI assistant",
    )
    assert intent.resource_id == "*3F"


def test_modify_address_rejects_malformed_resource_id():
    with pytest.raises(ValidationError):
        ModifyAddressIntent(
            confidence=0.8,
            requires_confirmation=True,
            resource_id="drop table addresses",
            comment="x",
        )


def test_modify_address_rejects_empty_patch():
    with pytest.raises(ValidationError):
        ModifyAddressIntent(confidence=0.8, requires_confirmation=True, resource_id="*3F")


def test_delete_firewall_rule_valid():
    intent = DeleteFirewallRuleIntent(
        confidence=0.95,
        requires_confirmation=True,
        resource_id="*1A",
        expected_description="forward rule dropping VLAN 20 -> WAN",
    )
    assert intent.category == IntentCategory.DESTRUCTIVE
    assert intent.safety_level == SafetyLevel.DESTRUCTIVE


def test_delete_firewall_rule_rejects_requires_confirmation_false():
    with pytest.raises(ValidationError):
        DeleteFirewallRuleIntent(
            confidence=0.95,
            requires_confirmation=False,
            resource_id="*1A",
            expected_description="x",
        )


def test_parse_intent_dispatches_by_discriminator():
    raw = {
        "intent": "create_hotspot",
        "confidence": 0.93,
        "requires_confirmation": True,
        "interface": "ether3",
        "network": "192.168.20.0/24",
        "rate_limit": "5M/5M",
    }
    intent = parse_intent(raw)
    assert isinstance(intent, CreateHotspotIntent)
    assert intent.intent == IntentName.CREATE_HOTSPOT


def test_parse_intent_rejects_unknown_intent_name():
    raw = {
        "intent": "drop_all_tables",
        "confidence": 0.99,
        "requires_confirmation": True,
    }
    with pytest.raises(IntentValidationError):
        parse_intent(raw)


def test_parse_intent_rejects_invented_property():
    raw = {
        "intent": "create_hotspot",
        "confidence": 0.9,
        "requires_confirmation": True,
        "interface": "ether3",
        "network": "192.168.20.0/24",
        "quantum_encryption_mode": "enabled",
    }
    with pytest.raises(IntentValidationError):
        parse_intent(raw)


def test_parse_intent_rejects_missing_required_field():
    raw = {
        "intent": "create_hotspot",
        "confidence": 0.9,
        "requires_confirmation": True,
    }
    with pytest.raises(IntentValidationError):
        parse_intent(raw)


def test_all_intent_names_are_covered_by_some_model():
    from mika.ai.schemas.registry import ALL_INTENT_MODELS

    covered = {model.model_fields["intent"].default for model in ALL_INTENT_MODELS}
    assert covered == set(IntentName)


def test_advise_intent_valid():
    from mika.ai.schemas.read_intents import AdviseIntent

    intent = AdviseIntent(
        confidence=0.95,
        requires_confirmation=False,
        message="Here is my advice on setting up your MikroTik router.",
        options=["Option 1: Setup Hotspot", "Option 2: Setup DHCP"],
        suggested_action="setup hotspot on ether3",
    )
    assert intent.category == IntentCategory.READ
    assert intent.safety_level == SafetyLevel.READ_ONLY
    assert len(intent.options) == 2
    assert intent.suggested_action == "setup hotspot on ether3"
