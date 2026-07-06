"""Protocol constants, magic numbers, enums, and shared data models.

This module defines all application-wide enumerations, numeric constants,
and reusable data structures (NetworkTarget, ProbeDefaults, TracerouteDefaults).

Enums support JSON serialization via their ``.value`` attribute.
Dataclasses support ``to_dict()`` / ``from_dict()`` round-tripping.
"""

from __future__ import annotations

import enum
import ipaddress
from dataclasses import dataclass
from typing import Any, Self

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProbeProtocol(enum.Enum):
    """Supported probe protocols for network measurement."""

    UDP = "udp"
    TCP = "tcp"
    ICMP = "icmp"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Protocol string (e.g. ``"udp"``).

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid protocol.
        """
        return cls(value)


class ServerType(enum.Enum):
    """Game server types for categorizing discovered servers."""

    CS2 = "cs2"
    CSGO = "csgo"
    TF2 = "tf2"
    L4D2 = "l4d2"
    CUSTOM = "custom"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Server type string (e.g. ``"cs2"``).

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid server type.
        """
        return cls(value)


class QualityGrade(enum.Enum):
    """Connection quality grades from A+ (best) to F (worst).

    Used by :class:`~uni.core.analysis.quality.QualityScorer` to rate
    overall connection quality based on latency, packet loss, and jitter.
    """

    A_PLUS = "A+"
    A = "A"
    B_PLUS = "B+"
    B = "B"
    C_PLUS = "C+"
    C = "C"
    D = "D"
    F = "F"

    @property
    def numeric_value(self) -> int:
        """Numeric score (8 = A+ down to 1 = F) for sorting and averaging."""
        order = {
            "A+": 8,
            "A": 7,
            "B+": 6,
            "B": 5,
            "C+": 4,
            "C": 3,
            "D": 2,
            "F": 1,
        }
        return order[self.value]

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Grade string (e.g. ``"A+"``, ``"B"``).

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid grade.
        """
        return cls(value)


class ICMPType(enum.Enum):
    """ICMPv4 message types (RFC 792, RFC 1122)."""

    ECHO_REPLY = 0
    DEST_UNREACHABLE = 3
    SOURCE_QUENCH = 4
    REDIRECT = 5
    ECHO_REQUEST = 8
    TIME_EXCEEDED = 11
    PARAMETER_PROBLEM = 12
    TIMESTAMP = 13
    TIMESTAMP_REPLY = 14

    def to_dict(self) -> int:
        """Serialize to JSON-compatible integer."""
        return self.value

    @classmethod
    def from_dict(cls, value: int) -> Self:
        """Deserialize from an integer value.

        Args:
            value: ICMP type number (e.g. ``11`` for Time Exceeded).

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a recognized ICMP type.
        """
        return cls(value)


class ICMPCode(enum.Enum):
    """ICMP Destination Unreachable codes (RFC 792, RFC 1122)."""

    NET_UNREACHABLE = 0
    HOST_UNREACHABLE = 1
    PROTOCOL_UNREACHABLE = 2
    PORT_UNREACHABLE = 3
    FRAGMENTATION_NEEDED = 4
    SOURCE_ROUTE_FAILED = 5
    DEST_NETWORK_UNKNOWN = 6
    DEST_HOST_UNKNOWN = 7
    SOURCE_HOST_ISOLATED = 8
    DEST_NETWORK_ADMIN_PROHIBITED = 10
    DEST_HOST_ADMIN_PROHIBITED = 11
    NETWORK_UNREACHABLE_FOR_TOS = 12
    HOST_UNREACHABLE_FOR_TOS = 13
    COMM_ADMIN_PROHIBITED = 13

    def to_dict(self) -> int:
        """Serialize to JSON-compatible integer."""
        return self.value

    @classmethod
    def from_dict(cls, value: int) -> Self:
        """Deserialize from an integer value.

        Args:
            value: ICMP code number.

        Returns:
            Corresponding enum member, or the value itself if not recognized.
        """
        try:
            return cls(value)
        except ValueError:
            return value  # type: ignore[return-value]


class AnomalyType(enum.Enum):
    """Types of network anomalies detected during probe analysis."""

    LATENCY_SPIKE = "latency_spike"
    PACKET_LOSS_BURST = "packet_loss_burst"
    JITTER_SPIKE = "jitter_spike"
    UNSTABLE_CONNECTION = "unstable_connection"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Anomaly type string.

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid anomaly type.
        """
        return cls(value)


class PluginState(enum.Enum):
    """Plugin lifecycle states."""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
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

        Raises:
            ValueError: If the value is not a valid state.
        """
        return cls(value)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_NAME = "UDP Network Intelligence"
APP_VERSION = "6.0.0"
APP_SHORT_NAME = "uni"

# Default ports
DEFAULT_SOURCE_PORT = 27015
DEFAULT_A2S_PORT = 27015
DEFAULT_STEAM_QUERY_PORT = 27015

# Network constants
MAX_UDP_PAYLOAD = 1400
DEFAULT_TTL = 64
MAX_TTL = 255
IP_HEADER_MIN_LENGTH = 20
ICMP_HEADER_MIN_LENGTH = 8
ICMP_TIMEOUT_HEADER_LENGTH = 28

# Timeouts (seconds)
DEFAULT_SOCKET_TIMEOUT = 3.0
DEFAULT_PROBE_TIMEOUT = 3.0
DEFAULT_TRACEROUTE_HOP_TIMEOUT = 2.0
DEFAULT_DISCOVERY_TIMEOUT = 5.0
DEFAULT_CHALLENGE_TIMEOUT = 3.0

# Probe defaults
DEFAULT_PROBE_COUNT = 50
DEFAULT_PROBE_INTERVAL = 1.0
DEFAULT_TRACEROUTE_MAX_HOPS = 30
DEFAULT_TRACEROUTE_PROBES_PER_HOP = 3

# Buffer sizes
DEFAULT_SEND_BUFFER_SIZE = 4096
DEFAULT_RECV_BUFFER_SIZE = 65536
DEFAULT_ICMP_RECEIVE_BUFFER = 65536

# A2S protocol
A2S_HEADER_SIZE = 4
A2S_CHALLENGE_RESPONSE = -1
A2S_INFO_RESPONSE_HEADER = 0x49  # 'I'
A2S_PLAYER_RESPONSE_HEADER = 0x44  # 'D'
A2S_RULES_RESPONSE_HEADER = 0x45  # 'E'
A2S_FAILED_RESPONSE = 0xFFFFFFFF

# Quality thresholds (milliseconds)
QUALITY_A_PLUS_THRESHOLD = 20.0
QUALITY_A_THRESHOLD = 50.0
QUALITY_B_PLUS_THRESHOLD = 80.0
QUALITY_B_THRESHOLD = 120.0
QUALITY_C_PLUS_THRESHOLD = 180.0
QUALITY_C_THRESHOLD = 250.0
QUALITY_D_THRESHOLD = 400.0

# Loss thresholds (percentage)
LOSS_A_THRESHOLD = 0.5
LOSS_B_THRESHOLD = 2.0
LOSS_C_THRESHOLD = 5.0
LOSS_D_THRESHOLD = 10.0

# Jitter thresholds (milliseconds)
JITTER_A_THRESHOLD = 5.0
JITTER_B_THRESHOLD = 15.0
JITTER_C_THRESHOLD = 30.0
JITTER_D_THRESHOLD = 50.0

# UI constants
DEFAULT_WINDOW_WIDTH = 1280
DEFAULT_WINDOW_HEIGHT = 800
DEFAULT_CHART_MAX_POINTS = 200
MIN_WINDOW_WIDTH = 800
MIN_WINDOW_HEIGHT = 600


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class NetworkTarget:
    """Represents a network target identified by host and port.

    This is the primary identifier for any remote endpoint the application
    communicates with (game servers, probe targets, traceroute destinations).

    Attributes:
        host: IP address or hostname.
        port: UDP/TCP port number (1-65535).

    Example::

        >>> target = NetworkTarget(host="192.168.1.1", port=27015)
        >>> str(target)
        '192.168.1.1:27015'
    """

    host: str
    port: int

    def __post_init__(self) -> None:
        """Validate host and port on creation."""
        if not self.host or not self.host.strip():
            raise ValueError("NetworkTarget.host must not be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(
                f"NetworkTarget.port must be between 1 and 65535, got {self.port}"
            )

    def __str__(self) -> str:
        """Human-readable representation: ``host:port``."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            ``{"host": "...", "port": ...}``
        """
        return {"host": self.host, "port": self.port}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with ``host`` and ``port`` keys.

        Returns:
            NetworkTarget instance.

        Raises:
            KeyError: If ``host`` or ``port`` is missing.
            ValueError: If validation fails.
        """
        return cls(host=str(data["host"]), port=int(data["port"]))

    @classmethod
    def from_string(cls, target: str) -> Self:
        """Parse a ``host:port`` string.

        Args:
            target: Target string (e.g. ``"192.168.1.1:27015"``).

        Returns:
            NetworkTarget instance.

        Raises:
            ValueError: If the format is invalid or port is out of range.
        """
        target = target.strip()
        # Handle IPv6 [host]:port
        if target.startswith("["):
            bracket_end = target.index("]")
            host = target[1:bracket_end]
            port_str = target[bracket_end + 2 :]  # skip ]:
            return cls(host=host, port=int(port_str))

        # Handle IPv4 or hostname:port
        last_colon = target.rfind(":")
        if last_colon == -1:
            raise ValueError(f"Invalid target format (expected host:port): {target!r}")
        host = target[:last_colon]
        port_str = target[last_colon + 1 :]
        return cls(host=host, port=int(port_str))

    @property
    def is_ip(self) -> bool:
        """True if host is an IP address (not a hostname)."""
        try:
            ipaddress.ip_address(self.host)
            return True
        except ValueError:
            return False

    @property
    def is_ipv4(self) -> bool:
        """True if host is an IPv4 address."""
        try:
            addr = ipaddress.ip_address(self.host)
            return isinstance(addr, ipaddress.IPv4Address)
        except ValueError:
            return False

    @property
    def is_ipv6(self) -> bool:
        """True if host is an IPv6 address."""
        try:
            addr = ipaddress.ip_address(self.host)
            return isinstance(addr, ipaddress.IPv6Address)
        except ValueError:
            return False

    @property
    def is_private(self) -> bool:
        """True if host is in a private/reserved IP range."""
        try:
            addr = ipaddress.ip_address(self.host)
            return addr.is_private or addr.is_loopback or addr.is_link_local
        except ValueError:
            return False


@dataclass(frozen=True, slots=True)
class ProbeDefaults:
    """Default configuration values for UDP probe campaigns.

    Attributes:
        count: Default number of probe packets to send.
        interval: Default interval between probes in seconds.
        port: Default target port.
        protocol: Default probe protocol.
        timeout: Default response timeout in seconds.
    """

    count: int = DEFAULT_PROBE_COUNT
    interval: float = DEFAULT_PROBE_INTERVAL
    port: int = DEFAULT_SOURCE_PORT
    protocol: ProbeProtocol = ProbeProtocol.UDP
    timeout: float = DEFAULT_PROBE_TIMEOUT

    def __post_init__(self) -> None:
        """Validate default values."""
        if self.count < 1:
            raise ValueError(f"ProbeDefaults.count must be >= 1, got {self.count}")
        if self.interval < 0.01:
            raise ValueError(
                f"ProbeDefaults.interval must be >= 0.01, got {self.interval}"
            )
        if not (1 <= self.port <= 65535):
            raise ValueError(f"ProbeDefaults.port must be 1-65535, got {self.port}")
        if self.timeout <= 0:
            raise ValueError(f"ProbeDefaults.timeout must be > 0, got {self.timeout}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "count": self.count,
            "interval": self.interval,
            "port": self.port,
            "protocol": self.protocol.value,
            "timeout": self.timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with optional probe default keys.

        Returns:
            ProbeDefaults instance.
        """
        return cls(
            count=int(data.get("count", DEFAULT_PROBE_COUNT)),
            interval=float(data.get("interval", DEFAULT_PROBE_INTERVAL)),
            port=int(data.get("port", DEFAULT_SOURCE_PORT)),
            protocol=ProbeProtocol(data.get("protocol", "udp")),
            timeout=float(data.get("timeout", DEFAULT_PROBE_TIMEOUT)),
        )


@dataclass(frozen=True, slots=True)
class TracerouteDefaults:
    """Default configuration values for UDP traceroute.

    Attributes:
        max_hops: Maximum number of hops to probe.
        probes_per_hop: Number of probe packets per TTL value.
        hop_timeout: Timeout waiting for ICMP response per hop.
    """

    max_hops: int = DEFAULT_TRACEROUTE_MAX_HOPS
    probes_per_hop: int = DEFAULT_TRACEROUTE_PROBES_PER_HOP
    hop_timeout: float = DEFAULT_TRACEROUTE_HOP_TIMEOUT

    def __post_init__(self) -> None:
        """Validate default values."""
        if not (1 <= self.max_hops <= 255):
            raise ValueError(
                f"TracerouteDefaults.max_hops must be 1-255, got {self.max_hops}"
            )
        if self.probes_per_hop < 1:
            raise ValueError(
                "TracerouteDefaults.probes_per_hop must be >= 1, "
                f"got {self.probes_per_hop}"
            )
        if self.hop_timeout <= 0:
            raise ValueError(
                f"TracerouteDefaults.hop_timeout must be > 0, got {self.hop_timeout}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "max_hops": self.max_hops,
            "probes_per_hop": self.probes_per_hop,
            "hop_timeout": self.hop_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with optional traceroute default keys.

        Returns:
            TracerouteDefaults instance.
        """
        return cls(
            max_hops=int(data.get("max_hops", DEFAULT_TRACEROUTE_MAX_HOPS)),
            probes_per_hop=int(
                data.get("probes_per_hop", DEFAULT_TRACEROUTE_PROBES_PER_HOP)
            ),
            hop_timeout=float(data.get("hop_timeout", DEFAULT_TRACEROUTE_HOP_TIMEOUT)),
        )
