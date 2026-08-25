from __future__ import annotations

import asyncio
import socket
import struct
from dataclasses import dataclass, field


_MNDP_PORT = 5678
_MNDP_BROADCAST = "255.255.255.255"
_MNDP_QUERY = b"\x00\x00\x00\x00"

_TLV_MAC = 1
_TLV_IDENTITY = 5
_TLV_VERSION = 7
_TLV_PLATFORM = 8
_TLV_UPTIME = 10
_TLV_SOFTWARE_ID = 11
_TLV_BOARD = 12
_TLV_IP = 15
_TLV_IPV6 = 17
_TLV_INTERFACE = 16


@dataclass
class MndpDevice:
    mac_address: str
    identity: str
    platform: str = "MikroTik"
    version: str = ""
    board: str = ""
    ip_address: str | None = None
    ipv6_address: str | None = None
    interface: str | None = None
    uptime_seconds: int = 0
    software_id: str = ""
    raw_addr: tuple[str, int] = field(default_factory=lambda: ("", 0))

    @property
    def display_host(self) -> str:
        if self.ip_address:
            return self.ip_address
        if self.ipv6_address:
            return f"[{self.ipv6_address}]"
        return self.mac_address

    @property
    def display_label(self) -> str:
        host_part = self.display_host
        version_part = f"  RouterOS {self.version}" if self.version else ""
        board_part = f"  {self.board}" if self.board else ""
        return f"{self.identity}  [{self.mac_address}]  {host_part}{board_part}{version_part}"


def _parse_mndp_packet(data: bytes, src_addr: tuple[str, int]) -> MndpDevice | None:
    if len(data) < 4:
        return None

    offset = 4
    tlvs: dict[int, bytes] = {}

    try:
        while offset + 4 <= len(data):
            tlv_type = struct.unpack_from(">H", data, offset)[0]
            tlv_len = struct.unpack_from(">H", data, offset + 2)[0]
            offset += 4
            if offset + tlv_len > len(data):
                break
            tlvs[tlv_type] = data[offset: offset + tlv_len]
            offset += tlv_len
    except struct.error:
        return None

    if _TLV_MAC not in tlvs:
        return None

    mac_bytes = tlvs[_TLV_MAC]
    if len(mac_bytes) != 6:
        return None
    mac = ":".join(f"{b:02X}" for b in mac_bytes)

    identity = tlvs.get(_TLV_IDENTITY, b"").decode("utf-8", errors="replace")
    version = tlvs.get(_TLV_VERSION, b"").decode("utf-8", errors="replace")
    platform = tlvs.get(_TLV_PLATFORM, b"MikroTik").decode("utf-8", errors="replace")
    board = tlvs.get(_TLV_BOARD, b"").decode("utf-8", errors="replace")
    software_id = tlvs.get(_TLV_SOFTWARE_ID, b"").decode("utf-8", errors="replace")
    iface = tlvs.get(_TLV_INTERFACE, b"").decode("utf-8", errors="replace") or None

    ip_address: str | None = None
    if _TLV_IP in tlvs and len(tlvs[_TLV_IP]) == 4:
        ip_address = socket.inet_ntoa(tlvs[_TLV_IP])

    ipv6_address: str | None = None
    if _TLV_IPV6 in tlvs and len(tlvs[_TLV_IPV6]) == 16:
        try:
            ipv6_address = socket.inet_ntop(socket.AF_INET6, tlvs[_TLV_IPV6])
        except OSError:
            pass

    uptime_seconds = 0
    if _TLV_UPTIME in tlvs and len(tlvs[_TLV_UPTIME]) == 4:
        uptime_seconds = struct.unpack_from(">I", tlvs[_TLV_UPTIME])[0]

    return MndpDevice(
        mac_address=mac,
        identity=identity or mac,
        platform=platform,
        version=version,
        board=board,
        ip_address=ip_address,
        ipv6_address=ipv6_address,
        interface=iface,
        uptime_seconds=uptime_seconds,
        software_id=software_id,
        raw_addr=src_addr,
    )


async def scan(timeout: float = 5.0) -> list[MndpDevice]:
    loop = asyncio.get_event_loop()
    devices: dict[str, MndpDevice] = {}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0)
        sock.bind(("", _MNDP_PORT))
    except OSError:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(0)
        except OSError:
            return []

    deadline = loop.time() + timeout

    try:
        await loop.run_in_executor(
            None,
            lambda: sock.sendto(_MNDP_QUERY, (_MNDP_BROADCAST, _MNDP_PORT)),
        )
    except OSError:
        sock.close()
        return []

    async def _recv_loop() -> None:
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                data, addr = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: _safe_recvfrom(sock)),
                    timeout=min(remaining, 0.5),
                )
                if data:
                    device = _parse_mndp_packet(data, addr)
                    if device and device.mac_address not in devices:
                        devices[device.mac_address] = device
            except (asyncio.TimeoutError, OSError):
                pass

    try:
        await _recv_loop()
    finally:
        sock.close()

    return sorted(devices.values(), key=lambda d: d.identity.lower())


def _safe_recvfrom(sock: socket.socket) -> tuple[bytes, tuple[str, int]]:
    try:
        return sock.recvfrom(4096)
    except BlockingIOError:
        import time
        time.sleep(0.05)
        return b"", ("", 0)
    except OSError:
        return b"", ("", 0)
