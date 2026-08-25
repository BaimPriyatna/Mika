from __future__ import annotations

import pytest

from mika.cli import env_secrets


@pytest.fixture(autouse=True)
def _isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_env_path_is_cwd_dotenv(tmp_path):
    assert env_secrets.env_path() == tmp_path / ".env"


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
    path = tmp_path / ".env"
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


class TestEnsureGitignored:
    def test_no_gitignore_present_returns_false(self):
        assert env_secrets.ensure_gitignored() is False

    def test_appends_env_when_gitignore_exists_and_lacks_it(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/\n*.pyc\n")
        added = env_secrets.ensure_gitignored()
        assert added is True
        content = (tmp_path / ".gitignore").read_text()
        assert ".env" in content.splitlines()

    def test_does_not_duplicate_when_already_ignored(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/\n.env\n")
        added = env_secrets.ensure_gitignored()
        assert added is False
        content = (tmp_path / ".gitignore").read_text()
        assert content.count(".env") == 1

    def test_handles_gitignore_with_no_trailing_newline(self, tmp_path):
        (tmp_path / ".gitignore").write_text("__pycache__/")
        env_secrets.ensure_gitignored()
        content = (tmp_path / ".gitignore").read_text()
        assert "__pycache__/\n.env\n" in content
