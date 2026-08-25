from __future__ import annotations


class RouterError(Exception):
    pass


class RouterConnectionError(RouterError):
    pass


class RouterTimeoutError(RouterConnectionError):
    pass


class RouterAuthenticationError(RouterError):
    pass


class RouterPermissionError(RouterError):
    pass


class RouterApiError(RouterError):

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code
