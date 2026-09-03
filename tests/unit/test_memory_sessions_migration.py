"""
Regression tests for the render_kind/render_payload schema migration on
session_messages (v0.3.0 prerequisite for /history replay).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from mika.memory import db
from mika.memory.sessions import SessionStore


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp) / "sessions.db"


def test_new_database_has_render_columns(db_path):
    store = SessionStore(db_path)
    sid = store.create_session()
    message_id = store.add_message(sid, "assistant", "hi", render_kind="advice", render_payload='{"message": "hi"}')

    [msg] = store.get_messages(sid)
    assert msg.id == message_id
    assert msg.render_kind == "advice"
    assert msg.render_payload == '{"message": "hi"}'


def test_add_message_defaults_to_plain_with_no_payload(db_path):
    store = SessionStore(db_path)
    sid = store.create_session()
    store.add_message(sid, "user", "hello")

    [msg] = store.get_messages(sid)
    assert msg.render_kind == "plain"
    assert msg.render_payload is None


def test_migration_is_idempotent_across_reinit(db_path):
    # First run creates the table + columns via _init_database().
    SessionStore(db_path)
    # Second run against the same file re-triggers _migrate(); the
    # duplicate-column path must be swallowed, not raised.
    store2 = SessionStore(db_path)
    sid = store2.create_session()
    store2.add_message(sid, "user", "still works")
    assert store2.get_messages(sid)[0].text == "still works"


def test_legacy_database_without_render_columns_upgrades_cleanly(db_path):
    # Simulate a pre-0.3.0 database: create the old schema by hand,
    # bypassing SessionStore entirely, then open it with SessionStore
    # and confirm the columns get added and old rows still read fine.
    with db.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                router_alias TEXT,
                started_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            )
        """)
        conn.execute(
            "INSERT INTO sessions (id, title, router_alias, started_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("legacy-1", "old session", None, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO session_messages (session_id, role, text, created_at) VALUES (?, ?, ?, ?)",
            ("legacy-1", "assistant", "(diagnosis shown)", "2026-01-01T00:00:00"),
        )
        conn.commit()

    store = SessionStore(db_path)
    [msg] = store.get_messages("legacy-1")
    assert msg.text == "(diagnosis shown)"
    assert msg.render_kind == "plain"
    assert msg.render_payload is None
