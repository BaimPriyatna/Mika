from __future__ import annotations

import os
import re
import stat
from pathlib import Path

from dotenv import dotenv_values, set_key, unset_key

from mika.cli.errors import CliError

_ENV_FILENAME = ".env"


class EnvFileError(CliError):
    pass


def env_path() -> Path:
    return Path.cwd() / _ENV_FILENAME


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", name.strip())
    return cleaned.upper().strip("_") or "UNNAMED"


def _provider_var(provider: str) -> str:
    return f"MIKA_PROVIDER_{_sanitize(provider)}_API_KEY"


def _router_var(alias: str) -> str:
    return f"MIKA_ROUTER_{_sanitize(alias)}_PASSWORD"


def ensure_env_file() -> Path:
    path = env_path()
    if not path.exists():
        try:
            path.touch(mode=0o600)
        except OSError as exc:
            raise EnvFileError(f"Could not create {path}: {exc}") from exc
    else:
        try:
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    return path


def ensure_gitignored() -> bool:
    gitignore = Path.cwd() / ".gitignore"
    if not gitignore.exists():
        return False
    try:
        content = gitignore.read_text()
    except OSError:
        return False
    if any(line.strip() in (".env", "/.env", ".env*") for line in content.splitlines()):
        return False
    try:
        with gitignore.open("a") as f:
            if content and not content.endswith("\n"):
                f.write("\n")
            f.write(".env\n")
        return True
    except OSError:
        return False


def _read(var_name: str) -> str | None:
    path = env_path()
    if not path.exists():
        return None
    try:
        values = dotenv_values(path)
    except Exception as exc:
        raise EnvFileError(f"Could not read {path}: {exc}") from exc
    return values.get(var_name) or None


def _write(var_name: str, value: str) -> None:
    path = ensure_env_file()
    try:
        set_key(str(path), var_name, value, quote_mode="always")
    except OSError as exc:
        raise EnvFileError(f"Could not write to {path}: {exc}") from exc


def _delete(var_name: str) -> None:
    path = env_path()
    if not path.exists():
        return
    try:
        unset_key(str(path), var_name)
    except OSError as exc:
        raise EnvFileError(f"Could not update {path}: {exc}") from exc


def get_provider_secret(provider: str) -> str | None:
    return _read(_provider_var(provider))


def set_provider_secret(provider: str, api_key: str) -> None:
    _write(_provider_var(provider), api_key)


def delete_provider_secret(provider: str) -> None:
    _delete(_provider_var(provider))


def get_router_secret(alias: str) -> str | None:
    return _read(_router_var(alias))


def set_router_secret(alias: str, password: str) -> None:
    _write(_router_var(alias), password)


def delete_router_secret(alias: str) -> None:
    _delete(_router_var(alias))
