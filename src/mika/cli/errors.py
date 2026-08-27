from __future__ import annotations


class CliError(Exception):
    pass


class ConfigError(CliError):
    pass


class RouterProfileNotFoundError(CliError):
    pass


class NoActiveRouterError(CliError):
    pass


class SecretNotFoundError(CliError):
    pass


class SessionNotFoundError(CliError):
    pass
