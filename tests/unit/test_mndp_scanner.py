from __future__ import annotations

import socket
import struct
import pytest

from mika.router.mndp import MndpDevice, _parse_mndp_packet


def _build_mndp_packet(
    mac: bytes,
    identity: str = "MikroTik",
    version: str = "7.14.2",
    platform: str = "MikroTik",
    board: str = "RB951G",
    ip: bytes | None = None,
    uptime: int = 3600,
) -> bytes:
    def tlv(t: int, v: bytes) -> bytes:
        return struct.pack(">HH", t, len(v)) + v

    parts = bytearray(b"\x00\x00\x00\x00")
    parts += tlv(1, mac)
    parts += tlv(5, identity.encode())
    parts += tlv(7, version.encode())
    parts += tlv(8, platform.encode())
    parts += tlv(12, board.encode())
    parts += tlv(10, struct.pack(">I", uptime))
    if ip is not None:
        parts += tlv(15, ip)
    return bytes(parts)


def _mac_str(mac_bytes: bytes) -> str:
    return ":".join(f"{b:02X}" for b in mac_bytes)


class TestParsePacket:

    def test_valid_packet_with_ip(self):
        mac = bytes([0xAA, 0xBB, 0xCC, 0x11, 0x22, 0x33])
        ip = socket.inet_aton("192.168.88.1")
        pkt = _build_mndp_packet(mac, ip=ip, identity="office-router")

        device = _parse_mndp_packet(pkt, ("192.168.88.1", 5678))

        assert device is not None
        assert device.mac_address == _mac_str(mac)
        assert device.identity == "office-router"
        assert device.ip_address == "192.168.88.1"
        assert device.version == "7.14.2"
        assert device.board == "RB951G"
        assert device.uptime_seconds == 3600

    def test_valid_packet_without_ip(self):
        mac = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
        pkt = _build_mndp_packet(mac, identity="fresh-router", ip=None)

        device = _parse_mndp_packet(pkt, ("0.0.0.0", 5678))

        assert device is not None
        assert device.ip_address is None
        assert device.identity == "fresh-router"

    def test_packet_too_short_returns_none(self):
        result = _parse_mndp_packet(b"\x00\x00", ("", 0))
        assert result is None

    def test_packet_missing_mac_tlv_returns_none(self):
        def tlv(t: int, v: bytes) -> bytes:
            return struct.pack(">HH", t, len(v)) + v

        pkt = b"\x00\x00\x00\x00" + tlv(5, b"no-mac-router")
        result = _parse_mndp_packet(pkt, ("", 0))
        assert result is None

    def test_malformed_tlv_does_not_crash(self):
        # Header ok but truncated TLV body
        pkt = b"\x00\x00\x00\x00" + struct.pack(">HH", 1, 100)
        result = _parse_mndp_packet(pkt, ("", 0))
        assert result is None

    def test_empty_identity_falls_back_to_mac(self):
        mac = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x00, 0x01])

        def tlv(t: int, v: bytes) -> bytes:
            return struct.pack(">HH", t, len(v)) + v

        pkt = b"\x00\x00\x00\x00" + tlv(1, mac) + tlv(5, b"")
        device = _parse_mndp_packet(pkt, ("", 0))

        assert device is not None
        assert device.identity == _mac_str(mac)

    def test_mac_wrong_length_returns_none(self):
        def tlv(t: int, v: bytes) -> bytes:
            return struct.pack(">HH", t, len(v)) + v

        pkt = b"\x00\x00\x00\x00" + tlv(1, b"\x01\x02\x03")
        result = _parse_mndp_packet(pkt, ("", 0))
        assert result is None


class TestMndpDevice:

    def test_display_host_prefers_ip(self):
        d = MndpDevice(
            mac_address="AA:BB:CC:DD:EE:FF",
            identity="router",
            ip_address="192.168.1.1",
        )
        assert d.display_host == "192.168.1.1"

    def test_display_host_falls_back_to_ipv6(self):
        d = MndpDevice(
            mac_address="AA:BB:CC:DD:EE:FF",
            identity="router",
            ip_address=None,
            ipv6_address="fe80::1",
        )
        assert d.display_host == "[fe80::1]"

    def test_display_host_falls_back_to_mac(self):
        d = MndpDevice(
            mac_address="AA:BB:CC:DD:EE:FF",
            identity="fresh-router",
            ip_address=None,
            ipv6_address=None,
        )
        assert d.display_host == "AA:BB:CC:DD:EE:FF"

    def test_display_label_includes_key_info(self):
        d = MndpDevice(
            mac_address="AA:BB:CC:DD:EE:FF",
            identity="lab",
            version="7.14.2",
            board="hEX",
            ip_address="10.0.0.1",
        )
        label = d.display_label
        assert "lab" in label
        assert "AA:BB:CC:DD:EE:FF" in label
        assert "10.0.0.1" in label
        assert "7.14.2" in label
        assert "hEX" in label


@pytest.mark.asyncio
async def test_scan_returns_empty_list_on_socket_error(monkeypatch):
    import mika.router.mndp as mndp_mod

    def _bad_socket(*args, **kwargs):
        raise OSError("no network")

    monkeypatch.setattr(mndp_mod.socket, "socket", _bad_socket)

    result = await mndp_mod.scan(timeout=0.1)
    assert result == []


@pytest.mark.asyncio
async def test_scan_deduplicates_by_mac(monkeypatch):
    import asyncio
    import mika.router.mndp as mndp_mod

    mac = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    pkt = _build_mndp_packet(mac, identity="dup-router", ip=socket.inet_aton("10.0.0.1"))

    call_count = 0

    def _fake_recvfrom(sock):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return pkt, ("10.0.0.1", 5678)
        import time; time.sleep(0.5)
        return b"", ("", 0)

    class _FakeSocket:
        def setsockopt(self, *a): pass
        def settimeout(self, *a): pass
        def bind(self, *a): pass
        def sendto(self, *a): pass
        def close(self): pass

    monkeypatch.setattr(mndp_mod.socket, "socket", lambda *a, **kw: _FakeSocket())
    monkeypatch.setattr(mndp_mod, "_safe_recvfrom", _fake_recvfrom)

    result = await mndp_mod.scan(timeout=0.3)

    assert len(result) == 1
    assert result[0].mac_address == "AA:BB:CC:DD:EE:FF"
    assert result[0].identity == "dup-router"
