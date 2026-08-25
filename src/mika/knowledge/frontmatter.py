from __future__ import annotations

from dataclasses import dataclass

_DELIMITER = "---"


@dataclass(frozen=True)
class ParsedDocument:

    metadata: dict[str, str]
    body: str


def parse_frontmatter(raw_text: str, *, source_name: str) -> ParsedDocument:
    lines = raw_text.splitlines()

    if not lines or lines[0].strip() != _DELIMITER:
        raise ValueError(
            f"'{source_name}' does not start with a '---' frontmatter block"
        )

    closing_index: int | None = None
    for index in range(1, len(lines)):
        if lines[index].strip() == _DELIMITER:
            closing_index = index
            break

    if closing_index is None:
        raise ValueError(
            f"'{source_name}' has an opening '---' but no closing '---'"
        )

    metadata: dict[str, str] = {}
    for line in lines[1:closing_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ValueError(
                f"'{source_name}' has a malformed frontmatter line: {line!r} "
                "(expected 'key: value')"
            )
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = _unquote(value.strip())
        if not key:
            raise ValueError(
                f"'{source_name}' has a frontmatter line with an empty key: {line!r}"
            )
        metadata[key] = value

    body = "\n".join(lines[closing_index + 1 :]).strip("\n")
    return ParsedDocument(metadata=metadata, body=body)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value
