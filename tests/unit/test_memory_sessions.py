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


def test_add_message_returns_message_id(store):
    sid = store.create_session()
    id1 = store.add_message(sid, "user", "first")
    id2 = store.add_message(sid, "assistant", "second")
    assert isinstance(id1, int)
    assert id2 > id1


def test_create_session_with_router_alias(store):
    sid = store.create_session(router_alias="lab-router")
    summaries = store.list_sessions()
    assert summaries[0].router_alias == "lab-router"


def test_create_session_without_router_alias_is_none(store):
    store.create_session()
    summaries = store.list_sessions()
    assert summaries[0].router_alias is None


def test_list_sessions_filtered_by_router(store):
    sid_a = store.create_session(router_alias="router-a")
    store.add_message(sid_a, "user", "on router a")
    sid_b = store.create_session(router_alias="router-b")
    store.add_message(sid_b, "user", "on router b")

    only_a = store.list_sessions(router_alias="router-a")
    assert [s.id for s in only_a] == [sid_a]


def test_list_sessions_filtered_by_no_router(store):
    sid_none = store.create_session(router_alias=None)
    store.create_session(router_alias="router-a")

    only_none = store.list_sessions(router_alias=None)
    assert [s.id for s in only_none] == [sid_none]


def test_list_routers_with_sessions_groups_and_counts(store):
    sid_a1 = store.create_session(router_alias="router-a")
    store.add_message(sid_a1, "user", "x")
    sid_a2 = store.create_session(router_alias="router-a")
    store.add_message(sid_a2, "user", "y")
    sid_b = store.create_session(router_alias="router-b")
    store.add_message(sid_b, "user", "z")
    sid_none = store.create_session(router_alias=None)
    store.add_message(sid_none, "user", "w")

    groups = {g.router_alias: g.session_count for g in store.list_routers_with_sessions()}
    assert groups == {"router-a": 2, "router-b": 1, None: 1}


def test_trim_after_deletes_later_messages(store):
    sid = store.create_session()
    id1 = store.add_message(sid, "user", "keep me")
    store.add_message(sid, "assistant", "drop me 1")
    store.add_message(sid, "user", "drop me 2")

    deleted = store.trim_after(sid, id1)

    assert deleted == 2
    remaining = store.get_messages(sid)
    assert [m.text for m in remaining] == ["keep me"]


def test_trim_after_no_later_messages_deletes_nothing(store):
    sid = store.create_session()
    id1 = store.add_message(sid, "user", "only message")

    deleted = store.trim_after(sid, id1)

    assert deleted == 0
    assert len(store.get_messages(sid)) == 1


def test_get_messages_include_ids(store):
    sid = store.create_session()
    mid = store.add_message(sid, "user", "hello")
    messages = store.get_messages(sid)
    assert messages[0].id == mid
