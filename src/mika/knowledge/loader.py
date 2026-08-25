"""
Knowledge Document Loader.

Parses and loads markdown knowledge files and frontmatter metadata from
the knowledge repository into structured memory.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from mika.knowledge.errors import KnowledgeError
from mika.knowledge.frontmatter import parse_frontmatter
from mika.knowledge.models import KnowledgeDocument

_EXPECTED_ROUTEROS_BY_DIR: dict[str, str] = {
    "v6": "6",
    "v7": "7",
    "concepts": "any",
}


class KnowledgeLoader:

    def __init__(self, root: Path) -> None:
        self.root = root

    def load_all(self) -> list[KnowledgeDocument]:
        documents: list[KnowledgeDocument] = []

        for relative_dir, expected_routeros in (
            (Path("routeros") / "v6", "6"),
            (Path("routeros") / "v7", "7"),
            (Path("concepts"), "any"),
        ):
            directory = self.root / relative_dir
            if not directory.is_dir():
                continue

            for file_path in sorted(directory.glob("*.md")):
                documents.append(
                    self._load_one(file_path, expected_routeros=expected_routeros)
                )

        return documents

    def _load_one(self, file_path: Path, *, expected_routeros: str) -> KnowledgeDocument:
        relative_path = file_path.relative_to(self.root)

        try:
            raw_text = file_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeError(f"could not read knowledge file: {exc}", path=str(relative_path)) from exc

        try:
            parsed = parse_frontmatter(raw_text, source_name=str(relative_path))
        except ValueError as exc:
            raise KnowledgeError(str(exc), path=str(relative_path)) from exc

        if not parsed.body:
            raise KnowledgeError("document body is empty after frontmatter", path=str(relative_path))

        doc_id = relative_path.with_suffix("").as_posix()

        try:
            document = KnowledgeDocument(
                id=doc_id,
                content=parsed.body,
                path=relative_path,
                **parsed.metadata,
            )
        except ValidationError as exc:
            raise KnowledgeError(
                f"invalid knowledge document metadata: {exc}", path=str(relative_path)
            ) from exc

        if document.routeros != expected_routeros:
            raise KnowledgeError(
                f"document declares routeros={document.routeros!r} but lives under a "
                f"folder for routeros={expected_routeros!r}; move the file or fix its "
                "frontmatter -- CLAUDE.md Section 17 forbids guessing which version a "
                "document applies to",
                path=str(relative_path),
            )

        return document
