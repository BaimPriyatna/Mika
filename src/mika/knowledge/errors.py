from __future__ import annotations


class KnowledgeError(Exception):

    def __init__(self, message: str, *, path: str | None = None) -> None:
        if path:
            message = f"{message} (file: {path})"
        super().__init__(message)
        self.path = path
