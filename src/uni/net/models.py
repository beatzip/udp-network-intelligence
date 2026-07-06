"""Network layer data models — socket configuration and interface statistics.

Defines the data structures for network socket configuration, interface
information, and traffic statistics.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Self

from uni.app.constants import (
    DEFAULT_RECV_BUFFER_SIZE,
    DEFAULT_SEND_BUFFER_SIZE,
    DEFAULT_SOCKET_TIMEOUT,
    DEFAULT_TTL,
)


class SocketType(Enum):
    """Socket type classification."""

    UDP = "udp"
    TCP = "tcp"
    RAW = "raw"
    ICMP = "icmp"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Socket type string.

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid socket type.
        """
        return cls(value)


class SocketState(Enum):
    """Socket lifecycle state."""

    CREATED = "created"
    BOUND = "bound"
    CONNECTED = "connected"
    CLOSED = "closed"
    ERROR = "error"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: State string.

        Returns:
            Corresponding enum member.
        """
        return cls(value)


@dataclass(frozen=True, slots=True)
class SocketConfig:
    """Configuration for a network socket.

    Defines all parameters needed to create and configure a UDP/TCP socket
    for probe or query operations.

    Attributes:
        host: Local bind address (``"0.0.0.0"`` for all interfaces).
        port: Local bind port (0 for OS-assigned ephemeral port).
        timeout: Socket timeout in seconds.
        buffer_size: Receive buffer size in bytes.
        ttl: IP Time-To-Live value.
        socket_type: Type of socket (UDP, TCP, RAW, ICMP).
        non_blocking: Whether to use non-blocking mode.
        reuse_address: Whether to set SO_REUSEADDR.
        send_buffer_size: Send buffer size in bytes.

    Example::

        >>> config = SocketConfig(host="0.0.0.0", port=0, timeout=5.0)
        >>> config.is_ephemeral
        True
    """

    host: str = "0.0.0.0"
    port: int = 0
    timeout: float = DEFAULT_SOCKET_TIMEOUT
    buffer_size: int = DEFAULT_RECV_BUFFER_SIZE
    ttl: int = DEFAULT_TTL
    socket_type: SocketType = SocketType.UDP
    non_blocking: bool = False
    reuse_address: bool = True
    send_buffer_size: int = DEFAULT_SEND_BUFFER_SIZE

    def __post_init__(self) -> None:
        """Validate socket configuration."""
        if not self.host:
            raise ValueError("SocketConfig.host must not be empty")
        if not (0 <= self.port <= 65535):
            raise ValueError(
                f"SocketConfig.port must be 0-65535, got {self.port}"
            )
        if self.timeout <= 0:
            raise ValueError(
                f"SocketConfig.timeout must be > 0, got {self.timeout}"
            )
        if self.buffer_size < 256:
            raise ValueError(
                f"SocketConfig.buffer_size must be >= 256, got {self.buffer_size}"
            )
        if not (0 <= self.ttl <= 255):
            raise ValueError(
                f"SocketConfig.ttl must be 0-255, got {self.ttl}"
            )
        if self.send_buffer_size < 256:
            raise ValueError(
                f"SocketConfig.send_buffer_size must be >= 256, "
                f"got {self.send_buffer_size}"
            )

    @property
    def is_ephemeral(self) -> bool:
        """True if port is OS-assigned (0)."""
        return self.port == 0

    @property
    def is_bound(self) -> bool:
        """True if a specific port is configured."""
        return self.port > 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all socket configuration fields.
        """
        return {
            "host": self.host,
            "port": self.port,
            "timeout": self.timeout,
            "buffer_size": self.buffer_size,
            "ttl": self.ttl,
            "socket_type": self.socket_type.value,
            "non_blocking": self.non_blocking,
            "reuse_address": self.reuse_address,
            "send_buffer_size": self.send_buffer_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with socket configuration fields.

        Returns:
            SocketConfig instance.
        """
        return cls(
            host=str(data.get("host", "0.0.0.0")),
            port=int(data.get("port", 0)),
            timeout=float(data.get("timeout", DEFAULT_SOCKET_TIMEOUT)),
            buffer_size=int(data.get("buffer_size", DEFAULT_RECV_BUFFER_SIZE)),
            ttl=int(data.get("ttl", DEFAULT_TTL)),
            socket_type=SocketType(data.get("socket_type", "udp")),
            non_blocking=bool(data.get("non_blocking", False)),
            reuse_address=bool(data.get("reuse_address", True)),
            send_buffer_size=int(
                data.get("send_buffer_size", DEFAULT_SEND_BUFFER_SIZE)
            ),
        )


@dataclass
class NetworkStats:
    """Network interface traffic statistics.

    Tracks bytes and packets sent/received, plus error counts.
    Can be used to monitor cumulative traffic or per-session stats.

    Attributes:
        bytes_sent: Total bytes transmitted.
        bytes_received: Total bytes received.
        packets_sent: Total packets transmitted.
        packets_received: Total packets received.
        errors: Total error count.
        send_errors: Errors during send operations.
        recv_errors: Errors during receive operations.

    Example::

        >>> stats = NetworkStats()
        >>> stats.record_send(1024)
        >>> stats.bytes_sent
        1024
    """

    bytes_sent: int = 0
    bytes_received: int = 0
    packets_sent: int = 0
    packets_received: int = 0
    errors: int = 0
    send_errors: int = 0
    recv_errors: int = 0

    def record_send(self, size: int) -> None:
        """Record a sent packet.

        Args:
            size: Number of bytes sent.
        """
        self.bytes_sent += size
        self.packets_sent += 1

    def record_receive(self, size: int) -> None:
        """Record a received packet.

        Args:
            size: Number of bytes received.
        """
        self.bytes_received += size
        self.packets_received += 1

    def record_send_error(self) -> None:
        """Record a send error."""
        self.send_errors += 1
        self.errors += 1

    def record_recv_error(self) -> None:
        """Record a receive error."""
        self.recv_errors += 1
        self.errors += 1

    @property
    def total_bytes(self) -> int:
        """Total bytes transferred (sent + received)."""
        return self.bytes_sent + self.bytes_received

    @property
    def total_packets(self) -> int:
        """Total packets transferred (sent + received)."""
        return self.packets_sent + self.packets_received

    @property
    def error_rate(self) -> float:
        """Error rate as a fraction of total packets."""
        total = self.total_packets
        if total == 0:
            return 0.0
        return self.errors / total

    @property
    def send_recv_ratio(self) -> float:
        """Ratio of bytes sent to bytes received.

        Useful for detecting asymmetric traffic patterns.
        """
        if self.bytes_received == 0:
            return float("inf") if self.bytes_sent > 0 else 0.0
        return self.bytes_sent / self.bytes_received

    def reset(self) -> None:
        """Reset all counters to zero."""
        self.bytes_sent = 0
        self.bytes_received = 0
        self.packets_sent = 0
        self.packets_received = 0
        self.errors = 0
        self.send_errors = 0
        self.recv_errors = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all statistics fields.
        """
        return {
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "errors": self.errors,
            "send_errors": self.send_errors,
            "recv_errors": self.recv_errors,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with statistics fields.

        Returns:
            NetworkStats instance.
        """
        return cls(
            bytes_sent=int(data.get("bytes_sent", 0)),
            bytes_received=int(data.get("bytes_received", 0)),
            packets_sent=int(data.get("packets_sent", 0)),
            packets_received=int(data.get("packets_received", 0)),
            errors=int(data.get("errors", 0)),
            send_errors=int(data.get("send_errors", 0)),
            recv_errors=int(data.get("recv_errors", 0)),
        )
