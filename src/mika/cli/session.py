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
    RewindError,
    RouterProfileNotFoundError,
    SecretNotFoundError,
    SessionNotFoundError,
)
from mika.audit.models import RollbackResult
from mika.executor.rollback import PlanBackup, rollback_from_backup
from mika.knowledge.loader import KnowledgeLoader
from mika.knowledge.retriever import KnowledgeRetriever
from mika.memory.backups import BackupStore
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
_UNSET = object()


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
    message_id: int | None = None
    render_kind: str = "plain"
    render_payload: str | None = None


@dataclass
class RewindResult:
    attempted: int
    succeeded: int
    stopped_early: bool
    errors: list[str]


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
    backup_store: BackupStore | None = None
    session_id: str | None = None

    last_plan: Plan | None = None
    last_backup: PlanBackup | None = None
    pending_draft: str | None = None


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
        backup_store = BackupStore(db_path)
        session = cls(
            config=cfg,
            config_path=path,
            audit_logger=AuditLogger(db_path),
            knowledge_retriever=KnowledgeRetriever(documents),
            memory_manager=memory_manager,
            session_store=session_store,
            backup_store=backup_store,
            session_id=session_store.create_session(router_alias=cfg.active_router),
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


    def add_history(
        self,
        role: str,
        text: str,
        render_kind: str = "plain",
        render_payload: str | None = None,
    ) -> int | None:
        message_id = None
        if self.session_store is not None and self.session_id is not None:
            message_id = self.session_store.add_message(
                self.session_id, role, text, render_kind=render_kind, render_payload=render_payload
            )
        self.history.append(
            HistoryEntry(
                role=role, text=text, message_id=message_id,
                render_kind=render_kind, render_payload=render_payload,
            )
        )
        if len(self.history) > _MAX_HISTORY:
            del self.history[: len(self.history) - _MAX_HISTORY]
        return message_id

    def recent_context_turns(self, limit: int = _MAX_CONTEXT_TURNS) -> list[HistoryEntry]:
        """Recent conversation turns to feed the AI as context, oldest first."""
        if limit <= 0:
            return []
        return self.history[-limit:]

    def start_new_session(self, router_alias: str | None | object = _UNSET) -> None:
        """Begin a fresh persisted conversation session, clearing in-memory
        history. The previous session remains stored and can be resumed
        later via /history.

        `router_alias`: which router to anchor the new session to. Defaults
        to the currently active router (self.router_alias) -- correct for
        /clear and /reset, where the router isn't changing. Callers that are
        switching to a *different* router (e.g. /router select) must pass
        the target alias explicitly, since at the point this is called
        self.router_alias still holds the *old* router (connect_router()
        hasn't run yet) -- relying on the default there would tag the new
        session with the wrong router.
        """
        self.history.clear()
        if self.session_store is not None:
            effective_alias = self.router_alias if router_alias is _UNSET else router_alias
            self.session_id = self.session_store.create_session(router_alias=effective_alias)

    def resume_session(self, session_id: str, router_alias: str | None | object = _UNSET) -> int:
        """Load a past session's messages into current in-memory history and
        continue appending new messages to that same session. Returns the
        number of messages loaded.

        `router_alias`: the router this session is scoped to (from the
        /history picker). If given and it differs from the currently
        connected router, the live connection is dropped (router_client
        set to None) rather than left silently pointing at the wrong
        router -- callers must reconnect explicitly (/connect or
        /router select) before running any router action. Omit this for
        callers that don't track per-session router scope; router_alias
        and router_client are then left untouched."""
        if self.session_store is None:
            raise SessionNotFoundError("No session store available.")
        if not self.session_store.session_exists(session_id):
            raise SessionNotFoundError(f"No session found matching '{session_id}'.")
        messages = self.session_store.get_messages(session_id)
        self.history = [
            HistoryEntry(
                role=m.role, text=m.text, message_id=m.id,
                render_kind=m.render_kind, render_payload=m.render_payload,
            )
            for m in messages
        ]
        if len(self.history) > _MAX_HISTORY:
            del self.history[: len(self.history) - _MAX_HISTORY]
        self.session_id = session_id
        if router_alias is not _UNSET and router_alias != self.router_alias:
            self.router_alias = router_alias
            self.router_client = None
        return len(messages)

    async def rewind_to(self, message_id: int) -> "RewindResult":
        """Roll back router config to match the state right after
        `message_id` in the current session, by undoing every plan backup
        recorded after that point (most recent first). Stops at the first
        failed rollback rather than continuing past it. On full success,
        trims in-memory and persisted history after `message_id` so future
        state stays consistent with the rolled-back config.

        `message_id=0` rolls back every backup ever recorded for this
        session (there being no valid row id below 1), matching the
        rewind-to-the-very-start case."""
        if self.backup_store is None or self.session_id is None:
            raise RewindError("Backup storage is not available.")

        stored = self.backup_store.list_backups_after(self.session_id, message_id)
        if not stored:
            # Nothing to undo on the router, but the conversation still
            # needs trimming to anchor it to this point.
            if self.session_store is not None:
                self.session_store.trim_after(self.session_id, message_id)
                self.history = [h for h in self.history if h.message_id is None or h.message_id <= message_id]
            return RewindResult(attempted=0, succeeded=0, stopped_early=False, errors=[])

        router_alias = stored[-1].router_alias
        if any(s.router_alias != router_alias for s in stored):
            raise RewindError(
                "This range spans changes to more than one router; rewind isn't supported across routers."
            )
        if self.router_alias != router_alias:
            raise RewindError(
                f"Switch to router '{router_alias}' first (/router select) before rewinding this session."
            )
        client = self.router_client
        if client is None:
            raise RewindError("Not connected to the router; reconnect before rewinding.")

        results: list[RollbackResult] = []
        succeeded_ids: list[int] = []
        for stored_backup in reversed(stored):
            result = await rollback_from_backup(stored_backup.backup, client)
            results.append(result)
            if result.success:
                succeeded_ids.append(stored_backup.id)
            else:
                break

        self.backup_store.mark_rolled_back(succeeded_ids)

        stopped_early = len(results) < len(stored)
        if not stopped_early and self.session_store is not None:
            self.session_store.trim_after(self.session_id, message_id)
            self.history = [h for h in self.history if h.message_id is None or h.message_id <= message_id]

        return RewindResult(
            attempted=len(results),
            succeeded=len(succeeded_ids),
            stopped_early=stopped_early,
            errors=[r.notes for r in results if not r.success and r.notes],
        )


    @staticmethod
    def current_os_user() -> str:
        try:
            return getpass.getuser()
        except Exception:
            return os.environ.get("USER", "unknown")

    def close(self) -> None:
        self.audit_logger.close()
