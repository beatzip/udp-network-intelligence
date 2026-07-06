"""Async ICMP socket for receiving ICMP error messages.

Provides :class:`AsyncICMPSocket` for listening to ICMP Destination
Unreachable and Time Exceeded messages. Requires administrator
privileges on Windows.

The ICMP socket is essential for UDP traceroute — it receives the
ICMP responses generated when a UDP probe arrives at a router with
TTL=1 or when a port is unreachable.

Example::

    async with AsyncICMPSocket() as sock:
        msg = await sock.receive(timeout=5.0)
        if msg.is_time_exceeded:
            print(f"Hop: {msg.embedded_src_ip}")
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

logger = logging.getLogger(__name__)

# ICMP message type constants
ICMP_ECHO_REPLY = 0
ICMP_DEST_UNREACHABLE = 3
ICMP_SOURCE_QUENCH = 4
ICMP_REDIRECT = 5
ICMP_ECHO_REQUEST = 8
ICMP_TIME_EXCEEDED = 11


# ---------------------------------------------------------------------------
# ICMP message model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ICMPReceivedMessage:
    """Parsed ICMP message received from the network.

    Attributes:
        icmp_type: ICMP message type (0-255).
        code: ICMP subtype code.
        checksum: ICMP checksum.
        identifier: ICMP identifier (for echo messages).
        sequence: ICMP sequence number (for echo messages).
        source_ip: IP address that sent the ICMP message.
        original_dest_ip: Destination IP from the embedded header.
        original_dest_port: Destination port from the embedded UDP header.
        original_src_ip: Source IP from the embedded header.
        original_src_port: Source port from the embedded UDP header.
        received_at: Monotonic timestamp when received.
        raw_data: Complete raw ICMP message bytes.
    """

    icmp_type: int
    code: int
    checksum: int = 0
    identifier: int = 0
    sequence: int = 0
    source_ip: str = ""
    original_dest_ip: str = ""
    original_dest_port: int = 0
    original_src_ip: str = ""
    original_src_port: int = 0
    received_at: float = 0.0
    raw_data: bytes = b""

    @property
    def is_time_exceeded(self) -> bool:
        """True if this is a Time Exceeded message (type 11)."""
        return self.icmp_type == ICMP_TIME_EXCEEDED

    @property
    def is_dest_unreachable(self) -> bool:
        """True if this is a Destination Unreachable message (type 3)."""
        return self.icmp_type == ICMP_DEST_UNREACHABLE

    @property
    def is_echo_reply(self) -> bool:
        """True if this is an Echo Reply (type 0)."""
        return self.icmp_type == ICMP_ECHO_REPLY

    @property
    def is_redirect(self) -> bool:
        """True if this is a Redirect message (type 5)."""
        return self.icmp_type == ICMP_REDIRECT

    @property
    def type_name(self) -> str:
        """Human-readable ICMP type name."""
        names = {
            0: "Echo Reply",
            3: "Dest Unreachable",
            4: "Source Quench",
            5: "Redirect",
            8: "Echo Request",
            11: "Time Exceeded",
        }
        return names.get(self.icmp_type, f"Type {self.icmp_type}")

    @property
    def code_name(self) -> str:
        """Human-readable ICMP code name for the current type."""
        if self.icmp_type == ICMP_DEST_UNREACHABLE:
            codes = {
                0: "Net Unreachable",
                1: "Host Unreachable",
                2: "Protocol Unreachable",
                3: "Port Unreachable",
                4: "Fragmentation Needed",
                13: "Communication Admin Prohibited",
            }
        elif self.icmp_type == ICMP_TIME_EXCEEDED:
            codes = {
                0: "TTL Exceeded in Transit",
                1: "Fragment Reassembly Time Exceeded",
            }
        else:
            codes = {}
        return codes.get(self.code, f"Code {self.code}")

    def to_dict(self) -> dict:
        """Serialize to JSON-compatible dictionary."""
        return {
            "icmp_type": self.icmp_type,
            "code": self.code,
            "type_name": self.type_name,
            "code_name": self.code_name,
            "source_ip": self.source_ip,
            "original_dest_ip": self.original_dest_ip,
            "original_dest_port": self.original_dest_port,
            "original_src_ip": self.original_src_ip,
            "original_src_port": self.original_src_port,
        }


# ---------------------------------------------------------------------------
# ICMP parser
# ---------------------------------------------------------------------------

def _parse_icmp_packet(
    data: bytes, source_ip: str
) -> ICMPReceivedMessage:
    """Parse raw ICMP packet bytes into an ICMPReceivedMessage.

    Handles ICMP Time Exceeded and Destination Unreachable messages
    that contain the original IP + UDP header in their payload.

    Args:
        data: Raw ICMP packet bytes.
        source_ip: IP address of the ICMP sender.

    Returns:
        Parsed ICMPReceivedMessage.
    """
    received_at = time.monotonic()

    # Minimum ICMP header: type(1) + code(1) + checksum(2) = 4 bytes
    if len(data) < 4:
        return ICMPReceivedMessage(
            icmp_type=0, code=0, source_ip=source_ip, raw_data=data,
            received_at=received_at,
        )

    icmp_type = data[0]
    code = data[1]
    checksum_val = struct.unpack("!H", data[2:4])[0]

    identifier = 0
    sequence = 0
    original_dest_ip = ""
    original_dest_port = 0
    original_src_ip = ""
    original_src_port = 0

    # For Echo Request/Reply: bytes 4-7 contain id + seq
    if icmp_type in (ICMP_ECHO_REPLY, ICMP_ECHO_REQUEST) and len(data) >= 8:
        identifier, sequence = struct.unpack("!HH", data[4:8])

    # For Time Exceeded / Dest Unreachable: payload contains
    # original IP header + 8 bytes of original datagram
    # Minimum: 20 (IP header) + 8 (UDP header) = 28 bytes of payload
    if icmp_type in (ICMP_TIME_EXCEEDED, ICMP_DEST_UNREACHABLE):
        # ICMP header is 8 bytes, then embedded IP header starts
        if len(data) >= 28:
            ip_header = data[8:28]
            # Parse embedded IP header
            ihl = (ip_header[0] & 0x0F) * 4  # IP header length in bytes
            protocol = ip_header[9]
            src_ip_bytes = ip_header[12:16]
            dst_ip_bytes = ip_header[16:20]

            original_src_ip = ".".join(str(b) for b in src_ip_bytes)
            original_dest_ip = ".".join(str(b) for b in dst_ip_bytes)

            # For UDP (protocol 17), port numbers are at offset 0,2 in the
            # UDP header which starts right after the IP header
            if protocol == 17 and len(data) >= 8 + ihl + 4:
                udp_offset = 8 + ihl
                original_src_port = struct.unpack(
                    "!H", data[udp_offset:udp_offset + 2]
                )[0]
                original_dest_port = struct.unpack(
                    "!H", data[udp_offset + 2:udp_offset + 4]
                )[0]

    return ICMPReceivedMessage(
        icmp_type=icmp_type,
        code=code,
        checksum=checksum_val,
        identifier=identifier,
        sequence=sequence,
        source_ip=source_ip,
        original_dest_ip=original_dest_ip,
        original_dest_port=original_dest_port,
        original_src_ip=original_src_ip,
        original_src_port=original_src_port,
        received_at=received_at,
        raw_data=data,
    )


# ---------------------------------------------------------------------------
# Async ICMP Protocol
# ---------------------------------------------------------------------------

class _ICMPProtocol(asyncio.DatagramProtocol):
    """Internal asyncio protocol for ICMP reception."""

    def __init__(self) -> None:
        """Initialize the ICMP protocol."""
        self._transport: asyncio.DatagramTransport | None = None
        self._queue: asyncio.Queue[ICMPReceivedMessage] = asyncio.Queue()
        self._closed = asyncio.Event()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called when connection is made."""
        self._transport = transport  # type: ignore[assignment]

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when connection is lost."""
        self._transport = None
        self._closed.set()

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Called when an ICMP datagram is received."""
        source_ip = addr[0] if addr else ""
        msg = _parse_icmp_packet(data, source_ip)
        self._queue.put_nowait(msg)

    def error_received(self, exc: Exception) -> None:
        """Called when an error is received."""
        logger.debug("ICMP error received: %s", exc)

    async def receive(self, timeout: float) -> ICMPReceivedMessage:
        """Wait for an ICMP message with timeout.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            Parsed ICMP message.

        Raises:
            asyncio.TimeoutError: If no message within timeout.
        """
        return await asyncio.wait_for(self._queue.get(), timeout=timeout)


# ---------------------------------------------------------------------------
# AsyncICMPSocket
# ---------------------------------------------------------------------------

class AsyncICMPSocket:
    """Async ICMP socket for receiving ICMP error messages.

    Listens for ICMP Time Exceeded and Destination Unreachable
    messages generated by routers and hosts in response to UDP probes.

    On Windows, raw sockets require administrator privileges.
    The socket falls back gracefully if not running as admin.

    Attributes:
        is_admin: Whether the process has admin privileges.
        stats: Number of messages received.

    Example::

        async with AsyncICMPSocket() as sock:
            msg = await sock.receive(timeout=5.0)
            if msg.is_time_exceeded:
                print(f"Hop at {msg.source_ip}: {msg.code_name}")
    """

    def __init__(self, bind_host: str = "0.0.0.0") -> None:
        """Initialize the ICMP socket.

        Args:
            bind_host: Local address to bind to.
        """
        self.bind_host = bind_host
        self._protocol: _ICMPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._is_open = False
        self._messages_received = 0
        self.is_admin = self._check_admin()

    @property
    def messages_received(self) -> int:
        """Number of ICMP messages received."""
        return self._messages_received

    @staticmethod
    def _check_admin() -> bool:
        """Check if the process has administrator privileges."""
        if platform.system() == "Windows":
            try:
                import ctypes
                return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
            except (AttributeError, OSError):
                return False
        else:
            import os
            return os.geteuid() == 0

    async def open(self) -> None:
        """Open the ICMP socket.

        Creates a raw ICMP socket and starts listening. On Windows,
        this requires administrator privileges for full functionality.

        Raises:
            PermissionError: If not running as admin on Windows.
            OSError: If the socket cannot be opened.
        """
        if self._is_open:
            return

        try:
            # Create raw ICMP socket
            if platform.system() == "Windows":
                # On Windows, use IPPROTO_ICMP with raw socket
                sock = socket.socket(
                    socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP
                )
            else:
                # On Linux/macOS, ICMP can be received via raw socket
                sock = socket.socket(
                    socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP
                )

            sock.setblocking(False)
            sock.bind((self.bind_host, 0))

            loop = asyncio.get_running_loop()
            self._protocol = _ICMPProtocol()
            transport, _ = await loop.create_datagram_endpoint(
                lambda: self._protocol,
                sock=sock,
            )
            self._transport = transport
            self._is_open = True
            logger.debug("ICMP socket opened on %s", self.bind_host)

        except PermissionError:
            logger.warning(
                "ICMP socket requires admin privileges. "
                "ICMP-based features will be limited."
            )
            raise
        except OSError as exc:
            logger.warning("Failed to open ICMP socket: %s", exc)
            raise

    async def close(self) -> None:
        """Close the ICMP socket."""
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
        self._protocol = None
        self._is_open = False
        logger.debug("ICMP socket closed")

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

    async def receive(
        self, timeout: float = 5.0
    ) -> ICMPReceivedMessage:
        """Receive an ICMP message with timeout.

        Args:
            timeout: Maximum wait time in seconds.

        Returns:
            Parsed ICMPReceivedMessage.

        Raises:
            asyncio.TimeoutError: If no message within timeout.
            RuntimeError: If the socket is not open.
        """
        if not self._is_open or self._protocol is None:
            raise RuntimeError("ICMP socket is not open")

        msg = await self._protocol.receive(timeout)
        self._messages_received += 1
        return msg

    async def receive_matching(
        self,
        dest_port: int,
        timeout: float = 5.0,
        source_ip: str | None = None,
    ) -> ICMPReceivedMessage | None:
        """Receive an ICMP message matching specific criteria.

        Filters incoming ICMP messages to find ones related to a
        specific destination port (from the embedded UDP header).

        Args:
            dest_port: Expected destination port in the embedded header.
            timeout: Maximum wait time in seconds.
            source_ip: Optional source IP filter.

        Returns:
            Matching ICMPReceivedMessage, or None on timeout.
        """
        if not self._is_open or self._protocol is None:
            raise RuntimeError("ICMP socket is not open")

        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break

            try:
                msg = await self._protocol.receive(remaining)
                self._messages_received += 1

                # Check if this matches our criteria
                if msg.original_dest_port == dest_port:
                    if source_ip is None or msg.source_ip == source_ip:
                        return msg

            except TimeoutError:
                break

        return None
