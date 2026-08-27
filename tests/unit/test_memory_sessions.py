from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mika.memory.sessions import SessionStore


@pytest.fixture
def store():
    with tempfile.TemporaryDirectory() as tmp:
        yield SessionStore(Path(tmp) / "sessions.db")


def test_create_session_returns_unique_id(store):
    id1 = store.create_session()
    id2 = store.create_session()
    assert id1 != id2
    assert store.session_exists(id1)
    assert store.session_exists(id2)


def test_add_message_persists_and_orders_messages(store):
    sid = store.create_session()
    store.add_message(sid, "user", "hello")
    store.add_message(sid, "assistant", "hi there")

    messages = store.get_messages(sid)
    assert [(m.role, m.text) for m in messages] == [
        ("user", "hello"),
        ("assistant", "hi there"),
    ]


def test_first_user_message_becomes_title(store):
    sid = store.create_session()
    store.add_message(sid, "user", "set up a firewall rule for VLAN 10")

    summaries = store.list_sessions()
    assert summaries[0].title == "set up a firewall rule for VLAN 10"


def test_title_truncated_to_60_chars(store):
    sid = store.create_session()
    long_text = "x" * 100
    store.add_message(sid, "user", long_text)

    summaries = store.list_sessions()
    assert len(summaries[0].title) == 60


def test_list_sessions_orders_by_most_recently_updated(store):
    old_sid = store.create_session()
    store.add_message(old_sid, "user", "first session")
    new_sid = store.create_session()
    store.add_message(new_sid, "user", "second session")

    summaries = store.list_sessions()
    assert summaries[0].id == new_sid
    assert summaries[1].id == old_sid


def test_message_count_reflected_in_summary(store):
    sid = store.create_session()
    store.add_message(sid, "user", "a")
    store.add_message(sid, "assistant", "b")
    store.add_message(sid, "user", "c")

    summaries = store.list_sessions()
    assert summaries[0].message_count == 3


def test_get_messages_respects_limit_keeping_most_recent(store):
    sid = store.create_session()
    for i in range(5):
        store.add_message(sid, "user", f"msg-{i}")

    messages = store.get_messages(sid, limit=2)
    assert [m.text for m in messages] == ["msg-3", "msg-4"]


def test_session_exists_false_for_unknown_id(store):
    assert store.session_exists("not-a-real-id") is False


def test_resolve_id_by_numeric_index(store):
    old_sid = store.create_session()
    store.add_message(old_sid, "user", "first")
    new_sid = store.create_session()
    store.add_message(new_sid, "user", "second")

    # index 1 = most recently updated
    assert store.resolve_id("1") == new_sid
    assert store.resolve_id("2") == old_sid


def test_resolve_id_out_of_range_returns_none(store):
    store.create_session()
    assert store.resolve_id("99") is None


def test_resolve_id_by_unique_prefix(store):
    sid = store.create_session()
    prefix = sid[:8]
    assert store.resolve_id(prefix) == sid


def test_resolve_id_ambiguous_or_unknown_prefix_returns_none(store):
    store.create_session()
    assert store.resolve_id("zzzzzzzz") is None
