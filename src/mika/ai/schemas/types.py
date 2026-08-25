from __future__ import annotations

from ipaddress import IPv4Address, IPv4Interface, IPv4Network
from typing import Annotated

from pydantic import Field, StringConstraints

InterfaceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.\-]+$"),
]

ResourceName = InterfaceName

ResourceId = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=32, pattern=r"^\*[0-9A-Fa-f]+$"),
]

VlanId = Annotated[int, Field(ge=1, le=4094)]

Port = Annotated[int, Field(ge=1, le=65535)]

RateLimit = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d+[kKmMgG]?(/\d+[kKmMgG]?)?$"),
]

Comment = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]

__all__ = [
    "IPv4Address",
    "IPv4Interface",
    "IPv4Network",
    "InterfaceName",
    "ResourceName",
    "ResourceId",
    "VlanId",
    "Port",
    "RateLimit",
    "Comment",
]
