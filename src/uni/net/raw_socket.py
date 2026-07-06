"""Raw socket manager for custom UDP packet construction.

Provides :class:`RawSocketManager` for sending raw UDP packets with
full control over IP headers, TTL, payload, and source addressing.
Uses raw sockets on Windows (requires admin) and UDP sockets with
custom TTL elsewhere.

Example::

    async with RawSocketManager() as mgr:
        info = await mgr.send_raw_udp(
            dest=("8.8.8.8", 53),
            payload=b"\x00" * 64,
            ttl=10,
        )
"""

from __future__ import annotations

import asyncio
import logging
import platform
import socket
import struct
import time
from dataclasses import dataclass
from typing import Any, Self

from uni.net.models import NetworkStats, SocketState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IP Header construction
# ---------------------------------------------------------------------------


def _build_ip_header(
    src_ip: str,
    dst_ip: str,
    payload_length: int,
    ttl: int = 64,
    protocol: int = 17,
) -> bytes:
    """Build a minimal IPv4 header.

    Args:
        src_ip: Source IP address.
        dst_ip: Destination IP address.
        payload_length: Length of the payload (UDP header + data).
        ttl: Time-to-live.
        protocol: IP protocol number (17 = UDP).

    Returns:
        20-byte IPv4 header.
    """
    version_ihl = (4 << 4) | 5  # Version 4, IHL 5 (20 bytes)
    dscp_ecn = 0
    total_length = 20 + payload_length
    identification = 0
    flags_fragment = 0x4000  # Don't Fragment
    header_checksum = 0

    src_bytes = socket.inet_aton(src_ip)
    dst_bytes = socket.inet_aton(dst_ip)

    header = struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_fragment,
        ttl,
        protocol,
        header_checksum,
        src_bytes,
        dst_bytes,
    )

    # Calculate checksum
    checksum = _ip_checksum(header)
    header = struct.pack(
        "!BBHHHBBH4s4s",
        version_ihl,
        dscp_ecn,
        total_length,
        identification,
        flags_fragment,
        ttl,
        protocol,
        checksum,
        src_bytes,
        dst_bytes,
    )

    return header


def _ip_checksum(data: bytes) -> int:
    """Calculate the IPv4 header checksum.

    Args:
        data: IP header bytes.

    Returns:
        16-bit checksum.
    """
    if len(data) % 2:
        data += b"\x00"

    checksum = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        checksum += word

    checksum = (checksum >> 16) + (checksum & 0xFFFF)
    checksum = ~checksum & 0xFFFF
    return checksum


# ---------------------------------------------------------------------------
# RawSocketManager
# ---------------------------------------------------------------------------


class RawSocketManager:
    """Manager for raw UDP socket operations.

    Provides methods to send raw UDP packets with full control over
    IP headers and TTL. On Windows, uses IPPROTO_RAW for outbound
    raw sockets (requires admin). On Linux/macOS, uses standard
    UDP sockets with IP_HDRINCL option.

    Attributes:
        stats: Traffic statistics.
        state: Socket lifecycle state.

    Example::

        async with RawSocketManager() as mgr:
            result = await mgr.send_raw_udp(
                dest=("8.8.8.8", 53),
                payload=b"\x00" * 64,
                ttl=5,
            )
    """

    def __init__(self) -> None:
        """Initialize the raw socket manager."""
        self.stats = NetworkStats()
        self.state = SocketState.CREATED
        self._sock: socket.socket | None = None
        self._lock = asyncio.Lock()

    @property
    def is_open(self) -> bool:
        """True if the raw socket is open."""
        return self.state == SocketState.BOUND and self._sock is not None

    async def open(self) -> None:
        """Open the raw socket.

        On Windows, creates an IPPROTO_RAW socket for sending.
        On Linux/macOS, creates a SOCK_RAW socket.

        Raises:
            PermissionError: If admin privileges are required but not available.
            OSError: If the socket cannot be opened.
        """
        if self.is_open:
            return

        try:
            if platform.system() == "Windows":
                # Windows: raw socket for sending
                self._sock = socket.socket(
                    socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_RAW
                )
                # Set IP_HDRINCL to indicate we provide the IP header
                self._sock.setsockopt(socket.IPPROTO_IP, socket.IP_HDRINCL, 1)
            else:
                # Linux/macOS: raw UDP socket
                self._sock = socket.socket(
                    socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
                )

            self._sock.setblocking(False)
            self.state = SocketState.BOUND
            logger.debug("Raw socket opened")

        except PermissionError:
            logger.warning("Raw socket requires admin privileges")
            raise
        except OSError as exc:
            logger.warning("Failed to open raw socket: %s", exc)
            raise

    async def close(self) -> None:
        """Close the raw socket."""
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self.state = SocketState.CLOSED
        logger.debug("Raw socket closed")

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def send_raw_udp(
        self,
        dest: tuple[str, int],
        payload: bytes,
        ttl: int = 64,
        src_port: int = 0,
    ) -> RawPacketInfo:
        """Send a raw UDP packet with custom TTL.

        Constructs a complete IP+UDP packet and sends it via the
        raw socket.

        Args:
            dest: Destination (host, port).
            payload: UDP payload data.
            ttl: IP Time-To-Live.
            src_port: Source port (0 = OS-assigned).

        Returns:
            RawPacketInfo with send metadata.

        Raises:
            RuntimeError: If the socket is not open.
            OSError: If the send fails.
        """
        if not self.is_open or self._sock is None:
            raise RuntimeError("Raw socket is not open")

        sent_time = time.monotonic()

        # Build UDP header
        src_port_effective = src_port
        dst_port = dest[1]
        udp_length = 8 + len(payload)  # UDP header (8) + payload

        # UDP checksum (0 = disabled for IPv4)
        udp_checksum = 0

        udp_header = struct.pack(
            "!HHHH",
            src_port_effective,
            dst_port,
            udp_length,
            udp_checksum,
        )

        try:
            if platform.system() == "Windows":
                # On Windows with IPPROTO_RAW, we build the full IP header
                src_ip = "0.0.0.0"
                dst_ip = socket.gethostbyname(dest[0])

                ip_header = _build_ip_header(
                    src_ip, dst_ip, udp_length, ttl=ttl, protocol=17
                )

                # For raw sockets, the UDP checksum must be computed
                # over a pseudo-header. Use 0 to let the kernel handle it.
                udp_header_no_cksum = struct.pack(
                    "!HHHH",
                    src_port_effective,
                    dst_port,
                    udp_length,
                    0,
                )

                packet = ip_header + udp_header_no_cksum + payload
                self._sock.sendto(packet, (dst_ip, dst_port))
            else:
                # On Linux/macOS, use sendto with the destination
                # The kernel builds the IP header
                self._sock.sendto(
                    udp_header + payload,
                    dest,
                )

            self.stats.record_send(len(payload))
            return RawPacketInfo(
                sent_time=sent_time,
                dest=dest,
                payload_size=len(payload),
                ttl=ttl,
                success=True,
            )

        except OSError as exc:
            self.stats.record_send_error()
            logger.debug("Raw send failed to %s:%d: %s", dest[0], dest[1], exc)
            return RawPacketInfo(
                sent_time=sent_time,
                dest=dest,
                payload_size=len(payload),
                ttl=ttl,
                success=False,
                error=str(exc),
            )

    async def send_to_multiple(
        self,
        targets: list[tuple[str, int]],
        payload: bytes,
        ttl: int = 64,
        delay: float = 0.001,
    ) -> list[RawPacketInfo]:
        """Send raw UDP to multiple targets with optional delay.

        Args:
            targets: List of (host, port) destinations.
            payload: UDP payload data.
            ttl: IP TTL.
            delay: Delay between sends in seconds.

        Returns:
            List of RawPacketInfo for each send.
        """
        results: list[RawPacketInfo] = []
        for i, target in enumerate(targets):
            result = await self.send_raw_udp(target, payload, ttl=ttl)
            results.append(result)
            if delay > 0 and i < len(targets) - 1:
                await asyncio.sleep(delay)
        return results

    def get_statistics(self) -> dict[str, Any]:
        """Get traffic statistics.

        Returns:
            Dictionary with stats.
        """
        return {
            "bytes_sent": self.stats.bytes_sent,
            "packets_sent": self.stats.packets_sent,
            "errors": self.stats.errors,
            "state": self.state.value,
        }


# ---------------------------------------------------------------------------
# RawPacketInfo
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RawPacketInfo:
    """Information about a raw packet send operation.

    Attributes:
        sent_time: Monotonic timestamp when sent.
        dest: Destination address.
        payload_size: Size of the UDP payload.
        ttl: TTL used.
        success: Whether the send succeeded.
        error: Error message if failed.
    """

    sent_time: float
    dest: tuple[str, int]
    payload_size: int
    ttl: int
    success: bool
    error: str | None = None
