from __future__ import annotations

import pytest

from mika.cli import env_secrets


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(env_secrets, "_CONFIG_DIR", tmp_path / ".config" / "mika")
    yield tmp_path


def test_env_path_is_fixed_config_dir(tmp_path):
    assert env_secrets.env_path() == tmp_path / ".config" / "mika" / ".env"


def test_env_path_ignores_cwd(tmp_path, monkeypatch):
    (tmp_path / "other").mkdir()
    monkeypatch.chdir(tmp_path / "other")
    assert env_secrets.env_path() == tmp_path / ".config" / "mika" / ".env"


def test_get_secret_returns_none_when_env_file_absent():
    assert env_secrets.get_provider_secret("gemini") is None
    assert env_secrets.get_router_secret("lab") is None


def test_set_and_get_provider_secret():
    env_secrets.set_provider_secret("gemini", "sk-real-key")
    assert env_secrets.get_provider_secret("gemini") == "sk-real-key"


def test_set_and_get_router_secret():
    env_secrets.set_router_secret("lab", "hunter2")
    assert env_secrets.get_router_secret("lab") == "hunter2"


def test_provider_and_router_secrets_do_not_collide():
    env_secrets.set_provider_secret("lab", "provider-secret")
    env_secrets.set_router_secret("lab", "router-secret")
    assert env_secrets.get_provider_secret("lab") == "provider-secret"
    assert env_secrets.get_router_secret("lab") == "router-secret"


def test_alias_with_special_characters_is_sanitized():
    env_secrets.set_router_secret("kantor pusat-2", "s3cr3t")
    assert env_secrets.get_router_secret("kantor pusat-2") == "s3cr3t"


def test_set_creates_env_file_with_owner_only_permissions(tmp_path):
    env_secrets.set_provider_secret("gemini", "sk-real-key")
    path = tmp_path / ".config" / "mika" / ".env"
    assert path.exists()
    mode = path.stat().st_mode & 0o777
    assert mode == 0o600


def test_delete_provider_secret_removes_it():
    env_secrets.set_provider_secret("gemini", "sk-real-key")
    env_secrets.delete_provider_secret("gemini")
    assert env_secrets.get_provider_secret("gemini") is None


def test_delete_absent_secret_is_noop():
    env_secrets.delete_router_secret("never-existed")


def test_overwriting_a_secret_replaces_it():
    env_secrets.set_provider_secret("gemini", "old-key")
    env_secrets.set_provider_secret("gemini", "new-key")
    assert env_secrets.get_provider_secret("gemini") == "new-key"


def test_multiple_secrets_coexist_in_same_env_file():
    env_secrets.set_provider_secret("gemini", "gemini-key")
    env_secrets.set_router_secret("lab", "lab-password")
    env_secrets.set_router_secret("kantor", "kantor-password")
    assert env_secrets.get_provider_secret("gemini") == "gemini-key"
    assert env_secrets.get_router_secret("lab") == "lab-password"
    assert env_secrets.get_router_secret("kantor") == "kantor-password"


class TestLegacyEnvMigration:
    def test_migrates_legacy_cwd_env_to_config_dir(self, tmp_path):
        legacy = tmp_path / ".env"
        legacy.write_text("MIKA_PROVIDER_GEMINI_API_KEY=old-key\n")
        assert env_secrets.get_provider_secret("gemini") == "old-key"
        assert not legacy.exists()
        assert env_secrets.env_path().exists()

    def test_does_not_migrate_when_target_already_exists(self, tmp_path):
        env_secrets.set_provider_secret("gemini", "current-key")
        legacy = tmp_path / ".env"
        legacy.write_text("MIKA_PROVIDER_GEMINI_API_KEY=legacy-key\n")
        assert env_secrets.get_provider_secret("gemini") == "current-key"
        assert legacy.exists()
