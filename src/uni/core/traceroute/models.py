"""UDP Traceroute data models — hop information and result aggregation.

Defines the data structures for UDP traceroute results: individual hop
information (IP, hostname, RTT) and the aggregated result across all hops.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(frozen=True, slots=True)
class TracerouteHop:
    """Single hop in a UDP traceroute result.

    Represents the response (or lack thereof) for a specific TTL value.
    Each hop captures the intermediate router that responded with an
    ICMP Time Exceeded message, or marks the hop as timed out.

    Attributes:
        ttl: The TTL value that triggered this hop.
        ip: IP address of the responding router (None if timed out).
        hostname: Reverse-DNS hostname of the router (None if unavailable).
        rtt_ms: Round-trip time in milliseconds (None if timed out).
        is_timeout: True if no ICMP response was received.
        icmp_type: ICMP message type received (e.g. 11 = Time Exceeded).
        icmp_code: ICMP code received (e.g. 0 = TTL exceeded in transit).
        packet_size: Size of the ICMP response packet in bytes.

    Example::

        >>> hop = TracerouteHop(ttl=5, ip="10.0.0.1", rtt_ms=12.3, is_timeout=False)
        >>> hop.is_resolved
        True
    """

    ttl: int
    ip: str | None = None
    hostname: str | None = None
    rtt_ms: float | None = None
    is_timeout: bool = True
    icmp_type: int = 0
    icmp_code: int = 0
    packet_size: int = 0

    def __post_init__(self) -> None:
        """Validate hop fields."""
        if not (1 <= self.ttl <= 255):
            raise ValueError(f"TracerouteHop.ttl must be 1-255, got {self.ttl}")
        if self.rtt_ms is not None and self.rtt_ms < 0:
            raise ValueError(f"TracerouteHop.rtt_ms must be >= 0, got {self.rtt_ms}")
        if not self.is_timeout and self.ip is None:
            raise ValueError(
                "TracerouteHop.ip must not be None when is_timeout is False"
            )

    @property
    def is_resolved(self) -> bool:
        """True if this hop responded with an ICMP message."""
        return not self.is_timeout and self.ip is not None

    @property
    def is_destination(self) -> bool:
        """True if this hop is the final destination (ICMP Dest Unreachable type 3)."""
        return self.is_resolved and self.icmp_type == 3

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all hop fields.
        """
        return {
            "ttl": self.ttl,
            "ip": self.ip,
            "hostname": self.hostname,
            "rtt_ms": self.rtt_ms,
            "is_timeout": self.is_timeout,
            "icmp_type": self.icmp_type,
            "icmp_code": self.icmp_code,
            "packet_size": self.packet_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with hop fields.

        Returns:
            TracerouteHop instance.

        Raises:
            KeyError: If ``ttl`` is missing.
            ValueError: If validation fails.
        """
        return cls(
            ttl=int(data["ttl"]),
            ip=data.get("ip"),
            hostname=data.get("hostname"),
            rtt_ms=data["rtt_ms"] if data.get("rtt_ms") is not None else None,
            is_timeout=bool(data.get("is_timeout", True)),
            icmp_type=int(data.get("icmp_type", 0)),
            icmp_code=int(data.get("icmp_code", 0)),
            packet_size=int(data.get("packet_size", 0)),
        )


@dataclass
class TracerouteResult:
    """Complete UDP traceroute result.

    Aggregates all hop responses into a single result, providing
    convenience properties for analysis (resolved hops, total path
    latency, unique routers).

    Attributes:
        target: Target host:port string.
        hops: Ordered list of all hops (including timeouts).
        start_time: Unix timestamp when the traceroute began.
        end_time: Unix timestamp when the traceroute completed.
        error: Error message if the traceroute failed, None otherwise.

    Example::

        >>> result = TracerouteResult(target="8.8.8.8:27015")
        >>> hop = TracerouteHop(ttl=1, ip="10.0.0.1", rtt_ms=5.2, is_timeout=False)
        >>> result.hops.append(hop)
        >>> result.hop_count
        1
    """

    target: str
    hops: list[TracerouteHop] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0
    error: str | None = None

    @property
    def resolved_hops(self) -> list[TracerouteHop]:
        """Hops that responded (not timed out)."""
        return [h for h in self.hops if h.is_resolved]

    @property
    def timed_out_hops(self) -> list[TracerouteHop]:
        """Hops that did not respond (timed out)."""
        return [h for h in self.hops if h.is_timeout]

    @property
    def hop_count(self) -> int:
        """Number of resolved hops."""
        return len(self.resolved_hops)

    @property
    def total_hops(self) -> int:
        """Total number of hops attempted (including timeouts)."""
        return len(self.hops)

    @property
    def max_ttl_reached(self) -> int:
        """Highest TTL value in the hop list."""
        if not self.hops:
            return 0
        return max(h.ttl for h in self.hops)

    @property
    def destination_reached(self) -> bool:
        """True if the final destination responded."""
        return any(h.is_destination for h in self.hops)

    @property
    def total_rtt_ms(self) -> float | None:
        """Sum of RTT across all resolved hops, or None if no resolved hops."""
        resolved = self.resolved_hops
        if not resolved:
            return None
        return sum(h.rtt_ms for h in resolved if h.rtt_ms is not None)

    @property
    def avg_rtt_ms(self) -> float | None:
        """Average RTT per resolved hop, or None if no resolved hops."""
        resolved = self.resolved_hops
        if not resolved:
            return None
        rtts = [h.rtt_ms for h in resolved if h.rtt_ms is not None]
        return sum(rtts) / len(rtts) if rtts else None

    @property
    def unique_routers(self) -> list[str]:
        """Deduplicated list of router IPs (preserving order)."""
        seen: set[str] = set()
        result: list[str] = []
        for h in self.resolved_hops:
            if h.ip and h.ip not in seen:
                seen.add(h.ip)
                result.append(h.ip)
        return result

    @property
    def duration_seconds(self) -> float:
        """Elapsed time of the traceroute in seconds."""
        if self.end_time <= 0:
            return 0.0
        return self.end_time - self.start_time

    @property
    def is_success(self) -> bool:
        """True if the traceroute completed without error."""
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all result fields including hops.
        """
        return {
            "target": self.target,
            "hops": [h.to_dict() for h in self.hops],
            "start_time": self.start_time,
            "end_time": self.end_time,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with traceroute result fields.

        Returns:
            TracerouteResult instance.

        Raises:
            KeyError: If ``target`` is missing.
        """
        hops_data = data.get("hops", [])
        return cls(
            target=str(data["target"]),
            hops=[TracerouteHop.from_dict(h) for h in hops_data],
            start_time=float(data.get("start_time", 0.0)),
            end_time=float(data.get("end_time", 0.0)),
            error=data.get("error"),
        )
