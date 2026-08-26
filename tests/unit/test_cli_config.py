from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mika.cli import config as cli_config


@pytest.fixture
def temp_config_path():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".toml", delete=False) as f:
        path = Path(f.name)
    try:
        yield path
    finally:
        if path.exists():
            path.unlink()


def test_load_empty_config_when_file_absent(temp_config_path):
    temp_config_path.unlink()
    cfg = cli_config.load_config(temp_config_path)
    assert cfg.active_router is None
    assert cfg.active_provider is None
    assert cfg.routers == {}
    assert cfg.models == []


def test_save_and_load_config(temp_config_path):
    cfg = cli_config.AppConfig(
        active_router="lab",
        active_provider="gemini",
        active_model="gemini-1.5-flash",
        routers={
            "lab": cli_config.RouterProfileConfig(
                host="192.168.88.1",
                username="admin",
                port=443,
                verify_tls=False,
                backend="rest",
            )
        },
        models=[cli_config.ModelEntry(provider="gemini", model="gemini-1.5-flash")],
    )
    cli_config.save_config(cfg, temp_config_path)

    loaded = cli_config.load_config(temp_config_path)
    assert loaded.active_router == "lab"
    assert loaded.active_provider == "gemini"
    assert loaded.active_model == "gemini-1.5-flash"
    assert "lab" in loaded.routers
    assert loaded.routers["lab"].host == "192.168.88.1"
    assert loaded.routers["lab"].verify_tls is False
    assert loaded.models == [cli_config.ModelEntry(provider="gemini", model="gemini-1.5-flash")]


def test_get_router_raises_when_alias_not_found():
    cfg = cli_config.AppConfig()
    with pytest.raises(cli_config.RouterProfileNotFoundError, match="No router profile named 'unknown'"):
        cfg.get_router("unknown")


def test_remember_model_appends_new_entry():
    cfg = cli_config.AppConfig()
    cfg.remember_model("gemini", "gemini-1.5-flash")
    cfg.remember_model("gemini", "gemini-1.5-pro")
    assert [m.model for m in cfg.models] == ["gemini-1.5-flash", "gemini-1.5-pro"]


def test_remember_model_deduplicates():
    cfg = cli_config.AppConfig()
    cfg.remember_model("gemini", "gemini-1.5-flash")
    cfg.remember_model("gemini", "gemini-1.5-flash")
    assert len(cfg.models) == 1


def test_effective_port_rest_backend_uses_port():
    profile = cli_config.RouterProfileConfig(
        host="192.168.88.1", username="admin", port=443, backend="rest"
    )
    assert profile.effective_port == 443


def test_effective_port_mock_backend_uses_port():
    profile = cli_config.RouterProfileConfig(
        host="192.168.88.1", username="admin", port=443, backend="mock"
    )
    assert profile.effective_port == 443


def test_effective_port_binary_backend_uses_api_port_when_set():
    profile = cli_config.RouterProfileConfig(
        host="192.168.88.1",
        username="admin",
        port=443,  # leftover REST-probe value from setup; must be ignored
        backend="binary",
        api_port=8728,
    )
    assert profile.effective_port == 8728


def test_effective_port_binary_backend_falls_back_to_default_plain():
    profile = cli_config.RouterProfileConfig(
        host="192.168.88.1",
        username="admin",
        port=443,
        backend="binary",
        api_port=None,
        api_ssl=False,
    )
    assert profile.effective_port == 8728


def test_effective_port_binary_backend_falls_back_to_default_ssl():
    profile = cli_config.RouterProfileConfig(
        host="192.168.88.1",
        username="admin",
        port=443,
        backend="binary",
        api_port=None,
        api_ssl=True,
    )
    assert profile.effective_port == 8729
