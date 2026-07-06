"""Async UDP socket engine — asyncio DatagramProtocol with full telemetry.

Provides :class:`AsyncUDPSocket` for high-performance async UDP I/O with
built-in RTT measurement, packet loss tracking, jitter calculation,
socket option management, and optional ICMP error handling.

Supports both IPv4 and IPv6, configurable TTL, socket buffer sizes,
and per-packet timestamps.

Example::

    async with AsyncUDPSocket(config) as sock:
        rtt, data = await sock.send_receive(b"hello", ("8.8.8.8", 53))
        print(f"RTT: {rtt:.2f}ms")
        print(f"Stats: {sock.stats}")
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Self

from uni.app.constants import (
    DEFAULT_SOCKET_TIMEOUT,
    DEFAULT_TTL,
)
from uni.net.models import NetworkStats, SocketConfig, SocketState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Socket options
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class SocketOptions:
    """Extended socket options beyond the basic SocketConfig.

    Attributes:
        reuse_address: Set SO_REUSEADDR.
        reuse_port: Set SO_REUSEPORT (Linux/macOS).
        keepalive: Set SO_KEEPALIVE.
        broadcast: Set SO_BROADCAST.
        no_delay: Disable Nagle (TCP only, ignored for UDP).
        recv_buffer: SO_RCVBUF size in bytes (0 = OS default).
        send_buffer: SO_SNDBUF size in bytes (0 = OS default).
    """

    reuse_address: bool = True
    reuse_port: bool = False
    keepalive: bool = False
    broadcast: bool = False
    no_delay: bool = False
    recv_buffer: int = 0
    send_buffer: int = 0


# ---------------------------------------------------------------------------
# Protocol result types
# ---------------------------------------------------------------------------

class SendResult(Enum):
    """Result of a send operation."""

    SUCCESS = "success"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    NETWORK_UNREACHABLE = "network_unreachable"
    ERROR = "error"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value


@dataclass(frozen=True, slots=True)
class PacketInfo:
    """Information about a single sent/received packet.

    Attributes:
        sequence: Packet sequence number.
        sent_time: Unix timestamp when the packet was sent.
        recv_time: Unix timestamp when the response was received (None if lost).
        rtt_ms: Round-trip time in milliseconds (None if lost).
        data: Raw packet data.
        source: Source address tuple (host, port).
        dest: Destination address tuple (host, port).
        send_result: Result of the send operation.
        packet_size: Size of the sent packet in bytes.
        response_size: Size of the response packet in bytes.
        ttl: TTL used for this packet.
    """

    sequence: int
    sent_time: float
    recv_time: float | None = None
    rtt_ms: float | None = None
    data: bytes = b""
    source: tuple[str, int] = ("", 0)
    dest: tuple[str, int] = ("", 0)
    send_result: SendResult = SendResult.SUCCESS
    packet_size: int = 0
    response_size: int = 0
    ttl: int = 0

    @property
    def is_timeout(self) -> bool:
        """True if the packet was not received."""
        return self.send_result == SendResult.TIMEOUT

    @property
    def is_success(self) -> bool:
        """True if a response was received."""
        return self.recv_time is not None and self.rtt_ms is not None


# ---------------------------------------------------------------------------
# Protocol class
# ---------------------------------------------------------------------------

class _UDPProtocol(asyncio.DatagramProtocol):
    """Internal asyncio DatagramProtocol implementation.

    Bridges asyncio's callback-based protocol to the async/await
    interface of AsyncUDPSocket.
    """

    def __init__(self) -> None:
        """Initialize the protocol."""
        self._transport: asyncio.DatagramTransport | None = None
        self._recv_queue: asyncio.Queue[
            tuple[bytes, tuple[str, int]]
        ] = asyncio.Queue()
        self._error_queue: asyncio.Queue[Exception] = asyncio.Queue()
        self._closed = asyncio.Event()

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called when the connection is made.

        Args:
            transport: The transport object.
        """
        self._transport = transport  # type: ignore[assignment]
        logger.debug("UDP connection established")

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when the connection is lost.

        Args:
            exc: Exception if the connection was lost due to an error.
        """
        self._transport = None
        self._closed.set()
        if exc is not None:
            logger.debug("UDP connection lost: %s", exc)

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Called when a datagram is received.

        Args:
            data: Received data.
            addr: Source address (host, port).
        """
        self._recv_queue.put_nowait((data, addr))

    def error_received(self, exc: Exception) -> None:
        """Called when an error is received.

        Args:
            exc: The error.
        """
        self._error_queue.put_nowait(exc)

    async def receive(
        self, timeout: float
    ) -> tuple[bytes, tuple[str, int]]:
        """Wait for a received datagram with timeout.

        Args:
            timeout: Maximum time to wait in seconds.

        Returns:
            Tuple of (data, source_address).

        Raises:
            asyncio.TimeoutError: If no data received within timeout.
            ConnectionError: If the socket is closed.
        """
        try:
            return await asyncio.wait_for(
                self._recv_queue.get(), timeout=timeout
            )
        except TimeoutError:
            raise
        except asyncio.CancelledError:
            raise


# ---------------------------------------------------------------------------
# AsyncUDPSocket
# ---------------------------------------------------------------------------

class AsyncUDPSocket:
    """High-performance async UDP socket with full telemetry.

    Wraps asyncio's DatagramProtocol with:
    - IPv4 and IPv6 support
    - Configurable socket options (TTL, buffers, reuse)
    - Per-packet timestamps for RTT measurement
    - Running statistics (loss, jitter, throughput)
    - Send-receive with timeout
    - Send-only (fire-and-forget)
    - Context manager for clean lifecycle

    Attributes:
        config: Socket configuration.
        options: Extended socket options.
        stats: Network traffic statistics.
        state: Current socket state.

    Example::

        config = SocketConfig(host="0.0.0.0", port=0, ttl=64)
        async with AsyncUDPSocket(config) as sock:
            info = await sock.send_receive(b"ping", ("1.2.3.4", 27015))
            print(f"RTT: {info.rtt_ms:.1f}ms")
    """

    def __init__(
        self,
        config: SocketConfig | None = None,
        options: SocketOptions | None = None,
    ) -> None:
        """Initialize the async UDP socket.

        Args:
            config: Socket configuration. Uses defaults if None.
            options: Extended socket options. Uses defaults if None.
        """
        self.config = config or SocketConfig()
        self.options = options or SocketOptions()
        self.stats = NetworkStats()
        self.state = SocketState.CREATED

        self._protocol: _UDPProtocol | None = None
        self._transport: asyncio.DatagramTransport | None = None
        self._sequence: int = 0
        self._lock = asyncio.Lock()
        self._bound_addr: tuple[str, int] = ("", 0)

    @property
    def is_open(self) -> bool:
        """True if the socket is open and ready for I/O."""
        return self.state == SocketState.BOUND and self._transport is not None

    @property
    def local_addr(self) -> tuple[str, int]:
        """Local address the socket is bound to."""
        if self._transport:
            return self._transport.get_extra_info("sockname", ("", 0))
        return self._bound_addr

    @property
    def local_host(self) -> str:
        """Local host address."""
        return self.local_addr[0]

    @property
    def local_port(self) -> int:
        """Local port number."""
        return self.local_addr[1]

    @property
    def af(self) -> int:
        """Address family (AF_INET or AF_INET6)."""
        if ":" in self.config.host:
            return socket.AF_INET6
        return socket.AF_INET

    def _next_sequence(self) -> int:
        """Get the next sequence number."""
        self._sequence += 1
        return self._sequence

    async def open(self) -> None:
        """Open the socket and bind to the configured address.

        Creates the asyncio transport and protocol, applies socket
        options, and binds to the local address.

        Raises:
            OSError: If the socket cannot be opened.
            ValueError: If the configuration is invalid.
        """
        if self.state != SocketState.CREATED:
            raise RuntimeError(f"Socket already in state: {self.state}")

        try:
            # Create socket with appropriate address family
            sock = socket.socket(self.af, socket.SOCK_DGRAM)

            # Apply socket options
            self._apply_options(sock)

            # Bind
            bind_addr = (self.config.host, self.config.port)
            sock.bind(bind_addr)

            # Get the event loop and create transport
            loop = asyncio.get_running_loop()
            self._protocol = _UDPProtocol()
            transport, _protocol = await loop.create_datagram_endpoint(
                lambda: self._protocol,
                sock=sock,
            )
            self._transport = transport
            self._bound_addr = transport.get_extra_info("sockname", ("", 0))
            self.state = SocketState.BOUND
            logger.debug(
                "UDP socket opened on %s:%d (af=%s)",
                self.local_host,
                self.local_port,
                "IPv6" if self.af == socket.AF_INET6 else "IPv4",
            )

        except Exception:
            self.state = SocketState.ERROR
            raise

    async def close(self) -> None:
        """Close the socket and release resources.

        Safe to call multiple times.
        """
        if self._transport is not None:
            try:
                self._transport.close()
            except Exception:
                pass
            self._transport = None
        self._protocol = None
        self.state = SocketState.CLOSED
        logger.debug("UDP socket closed")

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

    def _apply_options(self, sock: socket.socket) -> None:
        """Apply socket options to the raw socket.

        Args:
            sock: Raw socket to configure.
        """
        # SO_REUSEADDR
        if self.options.reuse_address:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        # SO_REUSEPORT (Linux/macOS only)
        if self.options.reuse_port and hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (OSError, AttributeError):
                pass

        # SO_KEEPALIVE
        if self.options.keepalive and hasattr(socket, "SO_KEEPALIVE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

        # SO_BROADCAST
        if self.options.broadcast:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # SO_RCVBUF
        if self.options.recv_buffer > 0:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_RCVBUF, self.options.recv_buffer
            )

        # SO_SNDBUF
        if self.options.send_buffer > 0:
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_SNDBUF, self.options.send_buffer
            )

        # TTL (IPv4 only)
        if self.config.ttl > 0 and self.af == socket.AF_INET:
            sock.setsockopt(
                socket.IPPROTO_IP, socket.IP_TTL, self.config.ttl
            )

        # TTL (IPv6)
        if self.config.ttl > 0 and self.af == socket.AF_INET6:
            sock.setsockopt(
                socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, self.config.ttl
            )

    def set_ttl(self, ttl: int) -> None:
        """Change the TTL on an open socket.

        Args:
            ttl: New TTL value (1-255).

        Raises:
            RuntimeError: If the socket is not open.
            ValueError: If TTL is out of range.
        """
        if not self.is_open or self._transport is None:
            raise RuntimeError("Socket is not open")

        if not (1 <= ttl <= 255):
            raise ValueError(f"TTL must be 1-255, got {ttl}")

        sock = self._transport.get_extra_info("socket")
        if sock is not None:
            if self.af == socket.AF_INET:
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            elif self.af == socket.AF_INET6:
                sock.setsockopt(
                    socket.IPPROTO_IPV6, socket.IPV6_UNICAST_HOPS, ttl
                )
            logger.debug("TTL set to %d", ttl)

    def set_socket_option(
        self, level: int, option: int, value: int
    ) -> None:
        """Set an arbitrary socket option on the underlying socket.

        Args:
            level: Socket option level (e.g. ``socket.SOL_SOCKET``).
            option: Option name (e.g. ``socket.SO_RCVBUF``).
            value: Option value.

        Raises:
            RuntimeError: If the socket is not open.
        """
        if not self.is_open or self._transport is None:
            raise RuntimeError("Socket is not open")

        sock = self._transport.get_extra_info("socket")
        if sock is not None:
            sock.setsockopt(level, option, value)
            logger.debug(
                "Socket option set: level=%d, option=%d, value=%d",
                level, option, value,
            )

    async def send(self, data: bytes, addr: tuple[str, int]) -> PacketInfo:
        """Send a UDP datagram without waiting for a response.

        Args:
            data: Data to send.
            addr: Destination address (host, port).

        Returns:
            PacketInfo with send timestamp and metadata.

        Raises:
            RuntimeError: If the socket is not open.
            OSError: If the send fails.
        """
        if not self.is_open or self._transport is None or self._protocol is None:
            raise RuntimeError("Socket is not open")

        seq = self._next_sequence()
        sent_time = time.monotonic()

        try:
            self._transport.sendto(data, addr)
            self.stats.record_send(len(data))

            return PacketInfo(
                sequence=seq,
                sent_time=sent_time,
                data=data,
                dest=addr,
                source=self.local_addr,
                send_result=SendResult.SUCCESS,
                packet_size=len(data),
                ttl=self.config.ttl,
            )

        except OSError as exc:
            self.stats.record_send_error()
            error_msg = str(exc).lower()
            if "connection refused" in error_msg:
                result = SendResult.CONNECTION_REFUSED
            elif "unreachable" in error_msg or "network" in error_msg:
                result = SendResult.NETWORK_UNREACHABLE
            else:
                result = SendResult.ERROR

            return PacketInfo(
                sequence=seq,
                sent_time=sent_time,
                data=data,
                dest=addr,
                source=self.local_addr,
                send_result=result,
                packet_size=len(data),
                ttl=self.config.ttl,
            )

    async def receive(
        self, timeout: float | None = None
    ) -> tuple[bytes, tuple[str, int]]:
        """Receive a single UDP datagram.

        Args:
            timeout: Maximum time to wait in seconds. Uses config
                timeout if None.

        Returns:
            Tuple of (data, source_address).

        Raises:
            asyncio.TimeoutError: If no data received within timeout.
            RuntimeError: If the socket is not open.
        """
        if not self.is_open or self._protocol is None:
            raise RuntimeError("Socket is not open")

        effective_timeout = timeout if timeout is not None else self.config.timeout
        data, addr = await self._protocol.receive(effective_timeout)
        self.stats.record_receive(len(data))
        return data, addr

    async def send_receive(
        self,
        data: bytes,
        addr: tuple[str, int],
        timeout: float | None = None,
        ttl: int | None = None,
    ) -> PacketInfo:
        """Send a datagram and wait for the response.

        Measures RTT using monotonic timestamps. Handles timeout,
        connection refused, and network unreachable errors.

        Args:
            data: Data to send.
            addr: Destination address (host, port).
            timeout: Response timeout in seconds. Uses config if None.
            ttl: TTL override for this packet. Uses config if None.

        Returns:
            PacketInfo with RTT, timestamps, and response data.
        """
        if not self.is_open or self._transport is None or self._protocol is None:
            raise RuntimeError("Socket is not open")

        seq = self._next_sequence()
        sent_time = time.monotonic()

        # Override TTL if requested
        if ttl is not None and ttl != self.config.ttl:
            self.set_ttl(ttl)

        effective_ttl = ttl if ttl is not None else self.config.ttl
        effective_timeout = timeout if timeout is not None else self.config.timeout

        try:
            self._transport.sendto(data, addr)
            self.stats.record_send(len(data))

            # Wait for response
            try:
                recv_data, recv_addr = await self._protocol.receive(
                    effective_timeout
                )
                recv_time = time.monotonic()
                self.stats.record_receive(len(recv_data))
                rtt_ms = (recv_time - sent_time) * 1000.0

                return PacketInfo(
                    sequence=seq,
                    sent_time=sent_time,
                    recv_time=recv_time,
                    rtt_ms=rtt_ms,
                    data=recv_data,
                    source=recv_addr,
                    dest=addr,
                    send_result=SendResult.SUCCESS,
                    packet_size=len(data),
                    response_size=len(recv_data),
                    ttl=effective_ttl,
                )

            except TimeoutError:
                return PacketInfo(
                    sequence=seq,
                    sent_time=sent_time,
                    data=data,
                    dest=addr,
                    source=self.local_addr,
                    send_result=SendResult.TIMEOUT,
                    packet_size=len(data),
                    ttl=effective_ttl,
                )

        except OSError as exc:
            self.stats.record_send_error()
            error_msg = str(exc).lower()
            if "connection refused" in error_msg:
                result = SendResult.CONNECTION_REFUSED
            elif "unreachable" in error_msg or "network" in error_msg:
                result = SendResult.NETWORK_UNREACHABLE
            else:
                result = SendResult.ERROR

            return PacketInfo(
                sequence=seq,
                sent_time=sent_time,
                data=data,
                dest=addr,
                source=self.local_addr,
                send_result=result,
                packet_size=len(data),
                ttl=effective_ttl,
            )

    async def send_receive_with_retry(
        self,
        data: bytes,
        addr: tuple[str, int],
        timeout: float | None = None,
        max_retries: int = 3,
        retry_delay: float = 0.5,
        backoff: float = 2.0,
        ttl: int | None = None,
    ) -> PacketInfo:
        """Send with automatic retry on timeout/failure.

        Retries on timeout, connection refused, and network unreachable
        errors. Uses exponential backoff between retries.

        Args:
            data: Data to send.
            addr: Destination address.
            timeout: Response timeout per attempt.
            max_retries: Maximum number of retry attempts.
            retry_delay: Initial delay between retries in seconds.
            backoff: Backoff multiplier for each retry.
            ttl: TTL override.

        Returns:
            PacketInfo from the last attempt (successful or not).
        """
        last_result: PacketInfo | None = None
        current_delay = retry_delay

        for attempt in range(max_retries + 1):
            result = await self.send_receive(
                data, addr, timeout=timeout, ttl=ttl
            )

            if result.is_success:
                return result

            last_result = result

            if attempt < max_retries:
                logger.debug(
                    "Retry %d/%d for %s:%d after %.1fs (result=%s)",
                    attempt + 1,
                    max_retries,
                    addr[0],
                    addr[1],
                    current_delay,
                    result.send_result.value,
                )
                await asyncio.sleep(current_delay)
                current_delay *= backoff

        return last_result  # type: ignore[return-value]

    def get_statistics(self) -> dict[str, Any]:
        """Get a snapshot of current statistics.

        Returns:
            Dictionary with traffic stats and protocol metadata.
        """
        return {
            "bytes_sent": self.stats.bytes_sent,
            "bytes_received": self.stats.bytes_received,
            "packets_sent": self.stats.packets_sent,
            "packets_received": self.stats.packets_received,
            "errors": self.stats.errors,
            "loss_rate": round(
                (
                    self.stats.packets_sent - self.stats.packets_received
                )
                / max(1, self.stats.packets_sent),
                4,
            ),
            "local_addr": list(self.local_addr),
            "state": self.state.value,
            "af": "IPv6" if self.af == socket.AF_INET6 else "IPv4",
        }

    def reset_statistics(self) -> None:
        """Reset all traffic statistics to zero."""
        self.stats.reset()
        self._sequence = 0


# ---------------------------------------------------------------------------
# Convenience: send one packet
# ---------------------------------------------------------------------------

async def udp_send_receive(
    data: bytes,
    addr: tuple[str, int],
    *,
    timeout: float = DEFAULT_SOCKET_TIMEOUT,
    ttl: int = DEFAULT_TTL,
    bind_host: str = "0.0.0.0",
    bind_port: int = 0,
    max_retries: int = 0,
    retry_delay: float = 0.5,
) -> PacketInfo:
    """Send a single UDP packet and receive the response.

    Convenience function that creates a socket, sends/receives, and
    closes the socket in one call.

    Args:
        data: Data to send.
        addr: Destination (host, port).
        timeout: Response timeout.
        ttl: IP TTL.
        bind_host: Local bind address.
        bind_port: Local bind port (0 = ephemeral).
        max_retries: Number of retries on failure.
        retry_delay: Delay between retries.

    Returns:
        PacketInfo with RTT and response data.
    """
    config = SocketConfig(
        host=bind_host,
        port=bind_port,
        timeout=timeout,
        ttl=ttl,
    )

    async with AsyncUDPSocket(config) as sock:
        if max_retries > 0:
            return await sock.send_receive_with_retry(
                data, addr, timeout=timeout, max_retries=max_retries,
                retry_delay=retry_delay,
            )
        return await sock.send_receive(data, addr, timeout=timeout)
