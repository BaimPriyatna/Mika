"""
CLI Chat Session State.

Maintains active runtime state during REPL execution, including current
router connection, AI provider, conversation history, and user settings.
"""

from __future__ import annotations

import getpass
import os
from dataclasses import dataclass, field
from pathlib import Path

from mika.ai.base import LLMProvider
from mika.ai.providers.gemini import GeminiProvider
from mika.audit.logger import AuditLogger
from mika.cli import config as cli_config
from mika.cli import env_secrets
from mika.cli.errors import (
    NoActiveRouterError,
    RouterProfileNotFoundError,
    SecretNotFoundError,
    SessionNotFoundError,
)
from mika.executor.rollback import PlanBackup
from mika.knowledge.loader import KnowledgeLoader
from mika.knowledge.retriever import KnowledgeRetriever
from mika.memory.manager import MemoryManager
from mika.memory.sessions import SessionStore
from mika.planner.plan import Plan
from mika.router.client import RouterClient
from mika.router.binary import BinaryRouterClient
from mika.router.mock import MockRouterClient
from mika.router.profile import RouterProfile
from mika.router.rest import RestRouterClient

_DEFAULT_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[3] / "knowledge"

# Shared SQLite file for both long-term facts (MemoryStorage) and persisted
# conversation sessions (SessionStore) -- same file, different tables.
_DEFAULT_MEMORY_DB_PATH = Path.home() / ".config" / "mika" / "memory.db"

_MAX_HISTORY = 200
_MAX_CONTEXT_TURNS = 20


def _empty_mock_profile() -> RouterProfile:
    return RouterProfile(
        system_resource={
            "board-name": "CHR",
            "version": "7.15.3 (stable)",
            "architecture-name": "x86_64",
            "cpu": "x86_64",
            "cpu-count": "1",
            "cpu-load": "0",
            "uptime": "0s",
        }
    )


@dataclass
class HistoryEntry:
    role: str
    text: str


@dataclass
class ChatSession:
    config: cli_config.AppConfig
    config_path: Path
    audit_logger: AuditLogger
    knowledge_retriever: KnowledgeRetriever

    router_alias: str | None = None
    router_client: RouterClient | None = None

    provider_name: str | None = None
    model_name: str | None = None
    provider: LLMProvider | None = None

    _provider_secrets: dict[str, str] = field(default_factory=dict, repr=False)

    history: list[HistoryEntry] = field(default_factory=list)

    memory_manager: MemoryManager | None = None
    session_store: SessionStore | None = None
    session_id: str | None = None

    last_plan: Plan | None = None
    last_backup: PlanBackup | None = None


    @classmethod
    def create(
        cls,
        config_path: Path | None = None,
        memory_db_path: Path | None = None,
    ) -> "ChatSession":
        path = config_path if config_path is not None else cli_config.default_config_path()
        cfg = cli_config.load_config(path)
        knowledge_root = _DEFAULT_KNOWLEDGE_ROOT
        documents = KnowledgeLoader(root=knowledge_root).load_all() if knowledge_root.is_dir() else []
        db_path = memory_db_path if memory_db_path is not None else _DEFAULT_MEMORY_DB_PATH
        memory_manager = MemoryManager.from_path(db_path)
        session_store = SessionStore(db_path)
        session = cls(
            config=cfg,
            config_path=path,
            audit_logger=AuditLogger(),
            knowledge_retriever=KnowledgeRetriever(documents),
            memory_manager=memory_manager,
            session_store=session_store,
            session_id=session_store.create_session(),
        )
        if cfg.active_router:
            try:
                session.connect_router(cfg.active_router)
            except (
                NoActiveRouterError,
                SecretNotFoundError,
                RouterProfileNotFoundError,
                env_secrets.EnvFileError,
            ):
                # active_router may point to a profile that no longer
                # exists (e.g. config.toml edited by hand, or removed via
                # other tooling). Fall back to "no active router" instead
                # of crashing the whole CLI on startup.
                session.router_alias = None
                session.config.active_router = None
        if cfg.active_provider and cfg.active_model:
            try:
                session.activate_provider(cfg.active_provider, cfg.active_model)
            except (SecretNotFoundError, env_secrets.EnvFileError):
                pass
        return session


    def connect_router(self, alias: str) -> None:
        profile_cfg = self.config.get_router(alias)

        if profile_cfg.backend == "mock":
            self.router_client = MockRouterClient(_empty_mock_profile())
        elif profile_cfg.backend == "binary":
            password = env_secrets.get_router_secret(alias)
            if not password:
                raise SecretNotFoundError(
                    f"No stored password for router '{alias}' in .env. Run /router add to re-enter it."
                )
            self.router_client = BinaryRouterClient(
                profile_cfg.host,
                profile_cfg.username,
                password,
                port=profile_cfg.effective_port,
                use_ssl=profile_cfg.api_ssl,
                ssl_cert_path=profile_cfg.api_ssl_cert,
                ssl_verify=profile_cfg.api_ssl_verify,
            )
        else:
            # Default: REST API backend (RouterOS v7+)
            password = env_secrets.get_router_secret(alias)
            if not password:
                raise SecretNotFoundError(
                    f"No stored password for router '{alias}' in .env. Run /router add to re-enter it."
                )
            self.router_client = RestRouterClient(
                profile_cfg.host,
                profile_cfg.username,
                password,
                port=profile_cfg.port,
                verify=profile_cfg.verify_tls,
            )

        self.router_alias = alias

    def require_router(self) -> RouterClient:
        if self.router_client is None:
            raise NoActiveRouterError(
                "No active router. Use /router select <alias> or /router add first."
            )
        return self.router_client


    def activate_provider(self, provider_name: str, model_name: str, *, api_key: str | None = None) -> None:
        if provider_name == "gemini":
            key = api_key or self._provider_secrets.get(provider_name)
            if key is None:
                try:
                    key = env_secrets.get_provider_secret("gemini")
                except env_secrets.EnvFileError as exc:
                    raise SecretNotFoundError(
                        f"Could not read .env for the 'gemini' API key ({exc}). "
                        "Run /provider to set it up again."
                    ) from exc
            if not key:
                raise SecretNotFoundError(
                    "No stored API key for 'gemini' in .env. Run /provider to set it up."
                )
            self.provider = GeminiProvider(key, model=model_name)
            self._provider_secrets[provider_name] = key
        else:
            raise SecretNotFoundError(f"Provider '{provider_name}' is not implemented yet.")

        self.provider_name = provider_name
        self.model_name = model_name
        self.config.remember_model(provider_name, model_name)

    def cached_provider_secret(self, provider_name: str) -> str | None:
        return self._provider_secrets.get(provider_name)

    def require_provider(self) -> LLMProvider:
        if self.provider is None:
            raise SecretNotFoundError("No active AI provider. Use /provider to set one up.")
        return self.provider


    def persist_active_selection(self) -> None:
        self.config.active_router = self.router_alias
        self.config.active_provider = self.provider_name
        self.config.active_model = self.model_name
        cli_config.save_config(self.config, self.config_path)


    def add_history(self, role: str, text: str) -> None:
        self.history.append(HistoryEntry(role=role, text=text))
        if len(self.history) > _MAX_HISTORY:
            del self.history[: len(self.history) - _MAX_HISTORY]
        if self.session_store is not None and self.session_id is not None:
            self.session_store.add_message(self.session_id, role, text)

    def recent_context_turns(self, limit: int = _MAX_CONTEXT_TURNS) -> list[HistoryEntry]:
        """Recent conversation turns to feed the AI as context, oldest first."""
        if limit <= 0:
            return []
        return self.history[-limit:]

    def start_new_session(self) -> None:
        """Begin a fresh persisted conversation session, clearing in-memory
        history. The previous session remains stored and can be resumed
        later via /resume."""
        self.history.clear()
        if self.session_store is not None:
            self.session_id = self.session_store.create_session()

    def resume_session(self, session_id: str) -> int:
        """Load a past session's messages into current in-memory history and
        continue appending new messages to that same session. Returns the
        number of messages loaded."""
        if self.session_store is None:
            raise SessionNotFoundError("No session store available.")
        if not self.session_store.session_exists(session_id):
            raise SessionNotFoundError(f"No session found matching '{session_id}'.")
        messages = self.session_store.get_messages(session_id)
        self.history = [HistoryEntry(role=m.role, text=m.text) for m in messages]
        if len(self.history) > _MAX_HISTORY:
            del self.history[: len(self.history) - _MAX_HISTORY]
        self.session_id = session_id
        return len(messages)


    @staticmethod
    def current_os_user() -> str:
        try:
            return getpass.getuser()
        except Exception:
            return os.environ.get("USER", "unknown")

    def close(self) -> None:
        self.audit_logger.close()
