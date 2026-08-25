from __future__ import annotations

from typing import Any


class AIError(Exception):
    pass


class AIProviderError(AIError):

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.details = details


class AIAuthenticationError(AIProviderError):
    pass


class AIRateLimitError(AIProviderError):
    pass


class AITimeoutError(AIProviderError):
    pass


class AISchemaError(AIError):

    def __init__(
        self,
        message: str,
        *,
        raw_output: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_output = raw_output
        self.cause = cause
        if cause is not None:
            self.__cause__ = cause
