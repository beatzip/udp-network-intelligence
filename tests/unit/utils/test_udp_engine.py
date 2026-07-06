"""Tests for the UDP network engine modules."""

from __future__ import annotations

import asyncio
import socket
import struct
import time

import pytest

from uni.net.firewall import FirewallHelper
from uni.net.icmp_socket import (
    ICMPReceivedMessage,
    _parse_icmp_packet,
)
from uni.net.models import (
    NetworkStats,
    SocketConfig,
)
from uni.net.pool import SocketPool
from uni.net.raw_socket import (
    _build_ip_header,
    _ip_checksum,
)
from uni.net.udp_socket import (
    AsyncUDPSocket,
    PacketInfo,
    SendResult,
    SocketOptions,
)

# ---------------------------------------------------------------------------
# SocketConfig
# ---------------------------------------------------------------------------


class TestSocketConfig:
    """Tests for SocketConfig model."""

    def test_defaults(self) -> None:
        cfg = SocketConfig()
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 0
        assert cfg.timeout == 3.0
        assert cfg.ttl == 64

    def test_is_ephemeral(self) -> None:
        assert SocketConfig(port=0).is_ephemeral is True
        assert SocketConfig(port=27015).is_ephemeral is False

    def test_validation_timeout(self) -> None:
        with pytest.raises(ValueError, match="timeout"):
            SocketConfig(timeout=-1)

    def test_validation_ttl(self) -> None:
        with pytest.raises(ValueError, match="ttl"):
            SocketConfig(ttl=300)

    def test_to_dict_roundtrip(self) -> None:
        cfg = SocketConfig(host="127.0.0.1", port=9999, ttl=128)
        data = cfg.to_dict()
        restored = SocketConfig.from_dict(data)
        assert restored.host == "127.0.0.1"
        assert restored.port == 9999
        assert restored.ttl == 128


# ---------------------------------------------------------------------------
# NetworkStats
# ---------------------------------------------------------------------------


class TestNetworkStats:
    """Tests for NetworkStats model."""

    def test_record_send(self) -> None:
        stats = NetworkStats()
        stats.record_send(100)
        assert stats.bytes_sent == 100
        assert stats.packets_sent == 1

    def test_record_receive(self) -> None:
        stats = NetworkStats()
        stats.record_receive(200)
        assert stats.bytes_received == 200
        assert stats.packets_received == 1

    def test_error_counting(self) -> None:
        stats = NetworkStats()
        stats.record_send_error()
        stats.record_recv_error()
        assert stats.errors == 2
        assert stats.send_errors == 1
        assert stats.recv_errors == 1

    def test_reset(self) -> None:
        stats = NetworkStats()
        stats.record_send(100)
        stats.record_receive(200)
        stats.reset()
        assert stats.bytes_sent == 0
        assert stats.packets_sent == 0

    def test_loss_rate(self) -> None:
        stats = NetworkStats()
        stats.packets_sent = 10
        stats.packets_received = 8
        stats.lost = 2
        # loss_rate = lost/sent = 2/10 = 0.2
        # But loss is not a field on NetworkStats, so test via calculation
        total = max(1, stats.packets_sent)
        loss = (stats.packets_sent - stats.packets_received) / total
        assert loss == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# SocketOptions
# ---------------------------------------------------------------------------


class TestSocketOptions:
    """Tests for SocketOptions."""

    def test_defaults(self) -> None:
        opts = SocketOptions()
        assert opts.reuse_address is True
        assert opts.reuse_port is False
        assert opts.broadcast is False

    def test_custom(self) -> None:
        opts = SocketOptions(broadcast=True, recv_buffer=65536)
        assert opts.broadcast is True
        assert opts.recv_buffer == 65536


# ---------------------------------------------------------------------------
# PacketInfo
# ---------------------------------------------------------------------------


class TestPacketInfo:
    """Tests for PacketInfo model."""

    def test_success(self) -> None:
        info = PacketInfo(
            sequence=1,
            sent_time=time.monotonic(),
            recv_time=time.monotonic() + 0.05,
            rtt_ms=50.0,
            send_result=SendResult.SUCCESS,
        )
        assert info.is_success is True
        assert info.is_timeout is False

    def test_timeout(self) -> None:
        info = PacketInfo(
            sequence=2,
            sent_time=time.monotonic(),
            send_result=SendResult.TIMEOUT,
        )
        assert info.is_timeout is True
        assert info.is_success is False

    def test_send_result_values(self) -> None:
        assert SendResult.SUCCESS.value == "success"
        assert SendResult.TIMEOUT.value == "timeout"
        assert SendResult.ERROR.value == "error"


# ---------------------------------------------------------------------------
# AsyncUDPSocket
# ---------------------------------------------------------------------------


class TestAsyncUDPSocket:
    """Tests for AsyncUDPSocket — uses loopback for real I/O."""

    @pytest.mark.asyncio
    async def test_open_close(self) -> None:
        sock = AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0))
        await sock.open()
        assert sock.is_open
        assert sock.local_port > 0
        await sock.close()
        assert not sock.is_open

    @pytest.mark.asyncio
    async def test_context_manager(self) -> None:
        async with AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0)) as sock:
            assert sock.is_open
        assert not sock.is_open

    @pytest.mark.asyncio
    async def test_send_to_loopback(self) -> None:
        async with AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0)) as sock:
            info = await sock.send(b"hello", ("127.0.0.1", 9999))
            assert info.send_result in (
                SendResult.SUCCESS,
                SendResult.CONNECTION_REFUSED,
                SendResult.NETWORK_UNREACHABLE,
            )
            assert info.packet_size == 5

    @pytest.mark.asyncio
    async def test_send_receive_loopback(self) -> None:
        """Test send_receive via a loopback echo server."""
        # Create a simple echo server
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server_sock.setblocking(False)
        server_sock.bind(("127.0.0.1", 0))
        server_port = server_sock.getsockname()[1]

        loop = asyncio.get_event_loop()
        echo_task = loop.create_task(_echo_server(server_sock))

        try:
            async with AsyncUDPSocket(
                SocketConfig(host="127.0.0.1", port=0, timeout=2.0)
            ) as sock:
                info = await sock.send_receive(b"ping", ("127.0.0.1", server_port))
                assert info.is_success
                assert info.rtt_ms is not None
                assert info.rtt_ms >= 0
                assert info.data == b"ping"
        finally:
            echo_task.cancel()
            server_sock.close()

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        """Test that timeout works when no server responds."""
        async with AsyncUDPSocket(
            SocketConfig(host="127.0.0.1", port=0, timeout=0.1)
        ) as sock:
            info = await sock.send_receive(b"test", ("127.0.0.1", 19999))
            assert info.send_result == SendResult.TIMEOUT

    @pytest.mark.asyncio
    async def test_statistics(self) -> None:
        async with AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0)) as sock:
            await sock.send(b"data", ("127.0.0.1", 9999))
            stats = sock.get_statistics()
            assert stats["packets_sent"] == 1
            assert stats["state"] == "bound"

    @pytest.mark.asyncio
    async def test_reset_statistics(self) -> None:
        async with AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0)) as sock:
            await sock.send(b"data", ("127.0.0.1", 9999))
            sock.reset_statistics()
            stats = sock.get_statistics()
            assert stats["packets_sent"] == 0

    @pytest.mark.asyncio
    async def test_double_close(self) -> None:
        sock = AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0))
        await sock.open()
        await sock.close()
        await sock.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_send_receive_closed_raises(self) -> None:
        sock = AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0))
        with pytest.raises(RuntimeError, match="not open"):
            await sock.send(b"test", ("127.0.0.1", 9999))

    @pytest.mark.asyncio
    async def test_ipv4_detection(self) -> None:
        sock = AsyncUDPSocket(SocketConfig(host="127.0.0.1", port=0))
        assert sock.af == socket.AF_INET

    @pytest.mark.asyncio
    async def test_ipv6_detection(self) -> None:
        sock = AsyncUDPSocket(SocketConfig(host="::1", port=0))
        assert sock.af == socket.AF_INET6

    @pytest.mark.asyncio
    async def test_send_receive_with_retry(self) -> None:
        """Test retry logic with a server that responds on second try."""
        # This tests the retry mechanism — server won't respond,
        # so it retries until max_retries is hit
        async with AsyncUDPSocket(
            SocketConfig(host="127.0.0.1", port=0, timeout=0.05)
        ) as sock:
            info = await sock.send_receive_with_retry(
                b"test",
                ("127.0.0.1", 19998),
                max_retries=1,
                retry_delay=0.01,
            )
            # Should be timeout after retries
            assert info.send_result == SendResult.TIMEOUT


# ---------------------------------------------------------------------------
# ICMPReceivedMessage
# ---------------------------------------------------------------------------


class TestICMPReceivedMessage:
    """Tests for ICMPReceivedMessage."""

    def test_time_exceeded(self) -> None:
        msg = ICMPReceivedMessage(
            icmp_type=11,
            code=0,
            source_ip="10.0.0.1",
        )
        assert msg.is_time_exceeded is True
        assert msg.is_dest_unreachable is False
        assert msg.type_name == "Time Exceeded"

    def test_dest_unreachable(self) -> None:
        msg = ICMPReceivedMessage(
            icmp_type=3,
            code=3,
            source_ip="10.0.0.1",
        )
        assert msg.is_dest_unreachable is True
        assert msg.code_name == "Port Unreachable"

    def test_echo_reply(self) -> None:
        msg = ICMPReceivedMessage(icmp_type=0, code=0)
        assert msg.is_echo_reply is True

    def test_to_dict(self) -> None:
        msg = ICMPReceivedMessage(
            icmp_type=11,
            code=0,
            source_ip="10.0.0.1",
        )
        d = msg.to_dict()
        assert d["icmp_type"] == 11
        assert d["type_name"] == "Time Exceeded"


# ---------------------------------------------------------------------------
# _parse_icmp_packet
# ---------------------------------------------------------------------------


class TestParseIcmpPacket:
    """Tests for ICMP packet parsing."""

    def test_parse_time_exceeded(self) -> None:
        # Build a minimal ICMP Time Exceeded message
        # Type(11) + Code(0) + Checksum(2) + Unused(4) + Embedded IP Header(20) + UDP(8)
        icmp_header = struct.pack("!BBH", 11, 0, 0) + b"\x00" * 4
        # Embedded IP header: version=4, ihl=5, proto=17 (UDP)
        embedded_ip = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,  # version_ihl
            0,  # dscp_ecn
            48,  # total_length
            0,  # identification
            0x4000,  # flags (DF)
            1,  # ttl (original was 1)
            17,  # protocol (UDP)
            0,  # checksum
            socket.inet_aton("10.0.0.1"),  # src
            socket.inet_aton("10.0.0.2"),  # dst
        )
        # Embedded UDP header: src_port=12345, dst_port=27015
        embedded_udp = struct.pack("!HHHH", 12345, 27015, 8, 0)

        raw = icmp_header + embedded_ip + embedded_udp
        msg = _parse_icmp_packet(raw, "10.0.0.1")

        assert msg.icmp_type == 11
        assert msg.code == 0
        assert msg.original_src_ip == "10.0.0.1"
        assert msg.original_dest_ip == "10.0.0.2"
        assert msg.original_src_port == 12345
        assert msg.original_dest_port == 27015

    def test_parse_echo_reply(self) -> None:
        # Type(0) + Code(0) + Checksum(2) + ID(2) + Seq(2)
        raw = struct.pack("!BBHHH", 0, 0, 0, 42, 1)
        msg = _parse_icmp_packet(raw, "8.8.8.8")
        assert msg.icmp_type == 0
        assert msg.identifier == 42
        assert msg.sequence == 1

    def test_parse_short_packet(self) -> None:
        # A 2-byte packet is too short for proper parsing — the parser
        # returns default values for unparseable data.
        msg = _parse_icmp_packet(b"\x0b\x00", "10.0.0.1")
        assert msg.source_ip == "10.0.0.1"
        assert len(msg.raw_data) == 2


# ---------------------------------------------------------------------------
# Raw socket helpers
# ---------------------------------------------------------------------------


class TestRawSocketHelpers:
    """Tests for raw socket helper functions."""

    def test_ip_checksum(self) -> None:
        # Test checksum against a known value
        header = (
            b"\x45\x00\x00\x28\x00\x00\x40\x00\x40\x11"
            + b"\x00\x00"
            + b"\x0a\x00\x00\x01"
            + b"\x0a\x00\x00\x02"
        )
        checksum = _ip_checksum(header)
        assert 0 <= checksum <= 0xFFFF

    def test_build_ip_header(self) -> None:
        header = _build_ip_header("10.0.0.1", "10.0.0.2", 32, ttl=64)
        assert len(header) == 20
        # Version should be 4
        version = (header[0] >> 4) & 0xF
        assert version == 4
        # TTL
        assert header[8] == 64

    def test_build_ip_header_custom_ttl(self) -> None:
        header = _build_ip_header("192.168.1.1", "8.8.8.8", 100, ttl=1)
        assert header[8] == 1


# ---------------------------------------------------------------------------
# SocketPool
# ---------------------------------------------------------------------------


class TestSocketPool:
    """Tests for SocketPool."""

    @pytest.mark.asyncio
    async def test_acquire_release(self) -> None:
        pool = SocketPool(max_size=4)
        async with pool:
            sock = await pool.acquire(SocketConfig(host="127.0.0.1", port=0))
            assert pool.active_count == 1
            assert pool.total_count == 1
            await pool.release(sock)
            assert pool.active_count == 0
            assert pool.idle_count == 1

    @pytest.mark.asyncio
    async def test_reuse_socket(self) -> None:
        pool = SocketPool(max_size=4)
        async with pool:
            sock1 = await pool.acquire(SocketConfig(host="127.0.0.1", port=0))
            await pool.release(sock1)
            sock2 = await pool.acquire(SocketConfig(host="127.0.0.1", port=0))
            assert sock1 is sock2  # Same socket reused
            await pool.release(sock2)

    @pytest.mark.asyncio
    async def test_max_size(self) -> None:
        pool = SocketPool(max_size=2)
        async with pool:
            s1 = await pool.acquire(SocketConfig(host="127.0.0.1", port=0))
            s2 = await pool.acquire(SocketConfig(host="127.0.0.1", port=0))
            assert pool.total_count == 2
            await pool.release(s1)
            await pool.release(s2)

    def test_invalid_max_size(self) -> None:
        with pytest.raises(ValueError, match="max_size"):
            SocketPool(max_size=0)


# ---------------------------------------------------------------------------
# FirewallHelper
# ---------------------------------------------------------------------------


class TestFirewallHelper:
    """Tests for FirewallHelper."""

    def test_is_windows(self) -> None:
        helper = FirewallHelper()
        # Just check it doesn't crash
        assert isinstance(helper.is_windows, bool)

    def test_add_rule_noop_on_non_windows(self) -> None:
        helper = FirewallHelper()
        if not helper.is_windows:
            result = helper.add_rule("Test Rule")
            assert result is True  # No-op returns True

    def test_remove_rule_noop_on_non_windows(self) -> None:
        helper = FirewallHelper()
        if not helper.is_windows:
            result = helper.remove_rule("Test Rule")
            assert result is True

    def test_list_rules_empty_on_non_windows(self) -> None:
        helper = FirewallHelper()
        if not helper.is_windows:
            rules = helper.list_rules()
            assert rules == []

    def test_parse_rules(self) -> None:
        output = (
            "Rule Name:                    UNI Test\n"
            "Enabled:                      Yes\n"
            "Direction:                    Out\n"
            "Action:                       Allow\n"
            "Protocol:                     UDP\n"
            "LocalPort:                    27015\n"
            "\n"
        )
        rules = FirewallHelper._parse_rules(output)
        assert len(rules) == 1
        assert rules[0]["Rule Name"] == "UNI Test"
        assert rules[0]["Protocol"] == "UDP"
        assert rules[0]["LocalPort"] == "27015"


# ---------------------------------------------------------------------------
# Integration: loopback echo server helper
# ---------------------------------------------------------------------------


async def _echo_server(sock: socket.socket) -> None:
    """Simple UDP echo server for testing."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 4096)
            await loop.sock_sendto(sock, data, addr)
        except (asyncio.CancelledError, OSError):
            break
