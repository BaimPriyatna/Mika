from datetime import date
from pathlib import Path

import pytest

from mika.knowledge import (
    KnowledgeDocument,
    KnowledgeError,
    KnowledgeLoader,
    KnowledgeRetriever,
    KnowledgeSource,
)

REPO_KNOWLEDGE_ROOT = Path(__file__).resolve().parents[2] / "knowledge"


def test_loads_all_seed_documents():
    documents = KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all()
    ids = {doc.id for doc in documents}
    assert "routeros/v7/firewall" in ids
    assert "routeros/v6/firewall" in ids
    assert "routeros/v7/hotspot" in ids
    assert "concepts/vlan" in ids
    assert "concepts/subnetting" in ids


def test_loaded_document_fields_are_parsed_correctly():
    documents = KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all()
    firewall_v7 = next(doc for doc in documents if doc.id == "routeros/v7/firewall")

    assert firewall_v7.topic == "firewall"
    assert firewall_v7.routeros == "7"
    assert firewall_v7.routeros_major == 7
    assert firewall_v7.source == KnowledgeSource.OFFICIAL_CURRENT
    assert firewall_v7.verified_at == date(2024, 6, 1)
    assert "input" in firewall_v7.content
    assert firewall_v7.path == Path("routeros/v7/firewall.md")


def test_concept_document_has_no_major_version():
    documents = KnowledgeLoader(root=REPO_KNOWLEDGE_ROOT).load_all()
    vlan = next(doc for doc in documents if doc.id == "concepts/vlan")
    assert vlan.routeros == "any"
    assert vlan.routeros_major is None


def test_missing_knowledge_root_returns_empty_list(tmp_path):
    documents = KnowledgeLoader(root=tmp_path / "does-not-exist").load_all()
    assert documents == []


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_rejects_document_missing_frontmatter(tmp_path):
    _write(tmp_path / "routeros" / "v7" / "bad.md", "# No frontmatter here\n")
    with pytest.raises(KnowledgeError, match="frontmatter"):
        KnowledgeLoader(root=tmp_path).load_all()


def test_rejects_document_with_unclosed_frontmatter(tmp_path):
    _write(
        tmp_path / "routeros" / "v7" / "bad.md",
        "---\ntopic: firewall\nrouteros: \"7\"\n",
    )
    with pytest.raises(KnowledgeError, match="closing"):
        KnowledgeLoader(root=tmp_path).load_all()


def test_rejects_document_with_invalid_metadata(tmp_path):
    _write(
        tmp_path / "routeros" / "v7" / "bad.md",
        "---\ntopic: firewall\nrouteros: \"7\"\nsource: made_up_source\nverified_at: 2024-01-01\n---\nBody.\n",
    )
    with pytest.raises(KnowledgeError, match="invalid knowledge document metadata"):
        KnowledgeLoader(root=tmp_path).load_all()


def test_rejects_document_with_routeros_mismatching_its_folder(tmp_path):
    _write(
        tmp_path / "routeros" / "v6" / "bad.md",
        "---\ntopic: firewall\nrouteros: \"7\"\nsource: official_current\nverified_at: 2024-01-01\n---\nBody.\n",
    )
    with pytest.raises(KnowledgeError, match="lives under a folder"):
        KnowledgeLoader(root=tmp_path).load_all()


def test_rejects_document_with_empty_body(tmp_path):
    _write(
        tmp_path / "concepts" / "bad.md",
        "---\ntopic: vlan\nrouteros: \"any\"\nsource: official_current\nverified_at: 2024-01-01\n---\n",
    )
    with pytest.raises(KnowledgeError, match="empty"):
        KnowledgeLoader(root=tmp_path).load_all()


def _doc(
    doc_id: str,
    topic: str,
    routeros: str,
    source: KnowledgeSource,
    content: str = "content",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        id=doc_id,
        topic=topic,
        routeros=routeros,
        source=source,
        verified_at=date(2024, 1, 1),
        content=content,
        path=Path(f"{doc_id}.md"),
    )


def test_retrieve_never_returns_unrelated_topics():
    docs = [
        _doc("a", "firewall", "7", KnowledgeSource.OFFICIAL_CURRENT),
        _doc("b", "hotspot", "7", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    result = KnowledgeRetriever(docs).retrieve("firewall")
    assert [d.id for d in result.documents] == ["a"]


def test_retrieve_is_case_insensitive_on_topic():
    docs = [_doc("a", "Firewall", "7", KnowledgeSource.OFFICIAL_CURRENT)]
    result = KnowledgeRetriever(docs).retrieve("FIREWALL")
    assert [d.id for d in result.documents] == ["a"]


def test_retrieve_without_version_returns_all_versions_ranked_by_source():
    docs = [
        _doc("community", "firewall", "7", KnowledgeSource.COMMUNITY),
        _doc("official", "firewall", "6", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    result = KnowledgeRetriever(docs).retrieve("firewall")
    assert [d.id for d in result.documents] == ["official", "community"]
    assert result.version_uncertain is False


def test_retrieve_with_version_excludes_other_major_versions():
    docs = [
        _doc("v6doc", "firewall", "6", KnowledgeSource.OFFICIAL_VERSION_SPECIFIC),
        _doc("v7doc", "firewall", "7", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    result = KnowledgeRetriever(docs).retrieve("firewall", routeros_major=7)
    assert [d.id for d in result.documents] == ["v7doc"]
    assert result.version_uncertain is False


def test_retrieve_includes_version_agnostic_concept_docs():
    docs = [
        _doc("v7doc", "vlan", "7", KnowledgeSource.OFFICIAL_CURRENT),
        _doc("concept", "vlan", "any", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    result = KnowledgeRetriever(docs).retrieve("vlan", routeros_major=7)
    ids = [d.id for d in result.documents]
    assert set(ids) == {"v7doc", "concept"}


def test_retrieve_flags_version_uncertain_when_only_other_version_exists():
    docs = [_doc("v6doc", "hotspot", "6", KnowledgeSource.OFFICIAL_VERSION_SPECIFIC)]
    result = KnowledgeRetriever(docs).retrieve("hotspot", routeros_major=7)
    assert result.documents == ()
    assert result.version_uncertain is True


def test_retrieve_no_documents_at_all_is_not_version_uncertain():
    result = KnowledgeRetriever([]).retrieve("nonexistent-topic", routeros_major=7)
    assert result.is_empty
    assert result.version_uncertain is False


def test_retrieve_many_keeps_topics_separate():
    docs = [
        _doc("fw", "firewall", "7", KnowledgeSource.OFFICIAL_CURRENT),
        _doc("hs", "hotspot", "7", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    results = KnowledgeRetriever(docs).retrieve_many(["firewall", "hotspot", "dhcp"])
    by_topic = {r.topic: r for r in results}
    assert [d.id for d in by_topic["firewall"].documents] == ["fw"]
    assert [d.id for d in by_topic["hotspot"].documents] == ["hs"]
    assert by_topic["dhcp"].is_empty


def test_available_topics():
    docs = [
        _doc("a", "firewall", "7", KnowledgeSource.OFFICIAL_CURRENT),
        _doc("b", "hotspot", "7", KnowledgeSource.OFFICIAL_CURRENT),
    ]
    assert KnowledgeRetriever(docs).available_topics() == {"firewall", "hotspot"}
