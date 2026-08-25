from __future__ import annotations


class ExecutorError(Exception):
    pass


class ExecutionDenied(ExecutorError):
    pass


class ExecutionError(ExecutorError):
    pass


class StaleConfirmationError(ExecutorError):
    pass
