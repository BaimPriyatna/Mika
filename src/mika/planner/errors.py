from __future__ import annotations


class PlannerError(Exception):
    pass


class InterfaceNotFoundError(PlannerError):
    pass


class InterfaceUnavailableError(PlannerError):
    pass


class HotspotAlreadyExistsError(PlannerError):
    pass


class SubnetConflictError(PlannerError):

    def __init__(self, message: str, *, conflicting_addresses: list[str]) -> None:
        super().__init__(message)
        self.conflicting_addresses = conflicting_addresses


class NetworkTooSmallError(PlannerError):
    pass
