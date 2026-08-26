from __future__ import annotations

import tomllib
from pathlib import Path

import tomli_w
from pydantic import BaseModel, ConfigDict, Field

from mika.cli.errors import ConfigError, RouterProfileNotFoundError

_DEFAULT_CONFIG_PATH = Path.home() / ".config" / "mika" / "config.toml"


class RouterProfileConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    host: str
    username: str
    port: int = 443
    verify_tls: bool = True
    backend: str = Field(
        default="rest",
        description="'rest' for RouterOS v7+ REST API, 'binary' for v6/v7 binary API (port 8728/8729), 'mock' for local testing.",
    )
    api_port: int | None = Field(
        default=None,
        description="Binary API port override. Defaults to 8728 (plaintext) or 8729 (SSL) when backend is 'binary'.",
    )
    api_ssl: bool = Field(
        default=False,
        description="Use SSL for binary API connection (port 8729). Only relevant when backend is 'binary'.",
    )
    api_ssl_cert: str | None = Field(
        default=None,
        description="Path to custom CA or certificate file (.crt/.pem) for binary API SSL verification.",
    )
    api_ssl_verify: bool = Field(
        default=False,
        description="Enable strict SSL certificate verification for binary API.",
    )

    @property
    def effective_port(self) -> int:
        """The port actually used to connect, given this profile's backend.

        For 'rest' and 'mock' backends this is simply `port`. For 'binary'
        backend, `port` is unrelated (it may hold a leftover REST-probe
        value from setup) — the real connection port is `api_port`, falling
        back to the binary API defaults (8728 plaintext / 8729 SSL) when
        `api_port` is unset. Use this instead of `port` anywhere a profile's
        port is displayed or connected to, so display and connection logic
        can never drift out of sync again.
        """
        if self.backend == "binary":
            if self.api_port is not None:
                return self.api_port
            return 8729 if self.api_ssl else 8728
        return self.port


class ModelEntry(BaseModel):

    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str


class AppConfig(BaseModel):

    model_config = ConfigDict(extra="forbid")

    active_router: str | None = None
    active_provider: str | None = None
    active_model: str | None = None
    routers: dict[str, RouterProfileConfig] = Field(default_factory=dict)
    models: list[ModelEntry] = Field(default_factory=list)

    def get_router(self, alias: str) -> RouterProfileConfig:
        try:
            return self.routers[alias]
        except KeyError:
            raise RouterProfileNotFoundError(f"No router profile named '{alias}'.") from None

    def remember_model(self, provider: str, model: str) -> None:
        for entry in self.models:
            if entry.provider == provider and entry.model == model:
                return
        self.models.append(ModelEntry(provider=provider, model=model))


def default_config_path() -> Path:
    return _DEFAULT_CONFIG_PATH


def load_config(path: Path | None = None) -> AppConfig:
    config_path = path if path is not None else default_config_path()
    if not config_path.exists():
        return AppConfig()

    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Could not parse {config_path}: {exc}") from exc

    try:
        return AppConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"Invalid config at {config_path}: {exc}") from exc


def save_config(config: AppConfig, path: Path | None = None) -> None:
    config_path = path if path is not None else default_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json", exclude_none=True)
    with config_path.open("wb") as f:
        tomli_w.dump(data, f)
