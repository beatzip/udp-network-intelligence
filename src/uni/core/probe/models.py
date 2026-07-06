"""UDP Probe data models — measurement results, statistics, and configuration.

This module defines the core data structures for UDP probe campaigns:
individual probe results, aggregated session statistics, and probe
campaign configuration.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Self

from uni.app.constants import ProbeProtocol


class ProbeStatus(Enum):
    """Status of an individual probe measurement.

    Attributes:
        SUCCESS: Probe received a valid response.
        TIMEOUT: No response received within the timeout window.
        UNREACHABLE: ICMP Destination Unreachable received.
        ERROR: An unexpected error occurred during the probe.
    """

    SUCCESS = "success"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    ERROR = "error"

    def to_dict(self) -> str:
        """Serialize to JSON-compatible string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from a string value.

        Args:
            value: Status string (e.g. ``"success"``).

        Returns:
            Corresponding enum member.

        Raises:
            ValueError: If the value is not a valid status.
        """
        return cls(value)


@dataclass(frozen=True, slots=True)
class ProbeResult:
    """Single probe measurement result.

    Represents the outcome of one UDP probe packet sent to a target.
    Each result captures the round-trip time (if successful), the
    sequence number for ordering, and the status of the probe.

    Attributes:
        sequence: Probe sequence number (0-indexed).
        rtt_ms: Round-trip time in milliseconds, or None on timeout/error.
        status: Probe outcome status.
        response_size: Size of the response payload in bytes.
        timestamp: Unix timestamp when the probe was sent.
        ttl: IP Time-To-Live used for this probe.
        source_ip: IP address of the responding host.
        source_port: Port of the responding host.

    Example::

        >>> result = ProbeResult(
        ...     sequence=0,
        ...     rtt_ms=42.5,
        ...     status=ProbeStatus.SUCCESS,
        ...     response_size=48,
        ... )
        >>> result.rtt_ms
        42.5
    """

    sequence: int
    rtt_ms: float | None
    status: ProbeStatus
    response_size: int = 0
    timestamp: float = field(default_factory=time.time)
    ttl: int = 0
    source_ip: str = ""
    source_port: int = 0

    def __post_init__(self) -> None:
        """Validate probe result fields."""
        if self.sequence < 0:
            raise ValueError(
                f"ProbeResult.sequence must be >= 0, got {self.sequence}"
            )
        if self.status == ProbeStatus.SUCCESS and self.rtt_ms is None:
            raise ValueError(
                "ProbeResult.rtt_ms must not be None when status is SUCCESS"
            )
        if self.rtt_ms is not None and self.rtt_ms < 0:
            raise ValueError(
                f"ProbeResult.rtt_ms must be >= 0, got {self.rtt_ms}"
            )
        if self.response_size < 0:
            raise ValueError(
                f"ProbeResult.response_size must be >= 0, got {self.response_size}"
            )

    @property
    def is_success(self) -> bool:
        """True if the probe received a valid response."""
        return self.status == ProbeStatus.SUCCESS

    @property
    def is_loss(self) -> bool:
        """True if the probe was lost (timeout or unreachable)."""
        return self.status in (ProbeStatus.TIMEOUT, ProbeStatus.UNREACHABLE)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all probe result fields.
        """
        return {
            "sequence": self.sequence,
            "rtt_ms": self.rtt_ms,
            "status": self.status.value,
            "response_size": self.response_size,
            "timestamp": self.timestamp,
            "ttl": self.ttl,
            "source_ip": self.source_ip,
            "source_port": self.source_port,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with probe result fields.

        Returns:
            ProbeResult instance.

        Raises:
            KeyError: If required fields are missing.
            ValueError: If validation fails.
        """
        return cls(
            sequence=int(data["sequence"]),
            rtt_ms=data["rtt_ms"] if data["rtt_ms"] is not None else None,
            status=ProbeStatus(data["status"]),
            response_size=int(data.get("response_size", 0)),
            timestamp=float(data.get("timestamp", 0.0)),
            ttl=int(data.get("ttl", 0)),
            source_ip=str(data.get("source_ip", "")),
            source_port=int(data.get("source_port", 0)),
        )


@dataclass
class ProbeStats:
    """Running statistics for a probe session.

    Maintains cumulative statistics as probe results arrive. The
    ``update()`` method accepts individual results and recalculates
    min/max/avg/jitter in real time.

    Attributes:
        sent: Total probes sent.
        received: Total probes received successfully.
        lost: Total probes lost (timeout + unreachable).
        min_rtt: Minimum observed RTT in milliseconds.
        max_rtt: Maximum observed RTT in milliseconds.
        avg_rtt: Running average RTT in milliseconds.
        jitter: Inter-packet jitter (mean deviation of RTT deltas).
        last_rtt: Most recent RTT value.

    Example::

        >>> stats = ProbeStats()
        >>> r1 = ProbeResult(sequence=0, rtt_ms=42.0, status=ProbeStatus.SUCCESS)
        >>> r2 = ProbeResult(sequence=1, rtt_ms=45.0, status=ProbeStatus.SUCCESS)
        >>> stats.update(r1)
        >>> stats.update(r2)
        >>> stats.avg_rtt
        43.5
    """

    sent: int = 0
    received: int = 0
    lost: int = 0
    min_rtt: float = 0.0
    max_rtt: float = 0.0
    avg_rtt: float = 0.0
    jitter: float = 0.0
    last_rtt: float | None = None

    # Internal running state (not serialized)
    _rtt_sum: float = field(default=0.0, repr=False, compare=False)
    _rtt_count: int = field(default=0, repr=False, compare=False)
    _prev_rtt: float | None = field(default=None, repr=False, compare=False)
    _jitter_sum: float = field(default=0.0, repr=False, compare=False)
    _jitter_count: int = field(default=0, repr=False, compare=False)

    @property
    def loss_rate(self) -> float:
        """Packet loss rate as a fraction (0.0 to 1.0).

        Returns 0.0 if no probes have been sent.
        """
        if self.sent == 0:
            return 0.0
        return self.lost / self.sent

    @property
    def loss_percent(self) -> float:
        """Packet loss as a percentage (0.0 to 100.0)."""
        return self.loss_rate * 100.0

    @property
    def success_rate(self) -> float:
        """Success rate as a fraction (0.0 to 1.0)."""
        return 1.0 - self.loss_rate

    @property
    def success_percent(self) -> float:
        """Success rate as a percentage."""
        return self.success_rate * 100.0

    def update(self, result: ProbeResult) -> None:
        """Update statistics with a new probe result.

        Args:
            result: The probe result to incorporate.
        """
        self.sent += 1

        if result.is_success and result.rtt_ms is not None:
            self.received += 1
            rtt = result.rtt_ms
            self.last_rtt = rtt

            # Min/Max
            if self.received == 1:
                self.min_rtt = rtt
                self.max_rtt = rtt
            else:
                self.min_rtt = min(self.min_rtt, rtt)
                self.max_rtt = max(self.max_rtt, rtt)

            # Running average (Welford-style incremental)
            self._rtt_sum += rtt
            self._rtt_count += 1
            self.avg_rtt = self._rtt_sum / self._rtt_count

            # Jitter (RFC 3550: interarrival jitter estimate)
            if self._prev_rtt is not None:
                delta = abs(rtt - self._prev_rtt)
                self._jitter_sum += delta
                self._jitter_count += 1
                if self._jitter_count > 0:
                    self.jitter = self._jitter_sum / self._jitter_count
            self._prev_rtt = rtt
        else:
            self.lost += 1

    def reset(self) -> None:
        """Reset all statistics to zero."""
        self.sent = 0
        self.received = 0
        self.lost = 0
        self.min_rtt = 0.0
        self.max_rtt = 0.0
        self.avg_rtt = 0.0
        self.jitter = 0.0
        self.last_rtt = None
        self._rtt_sum = 0.0
        self._rtt_count = 0
        self._prev_rtt = None
        self._jitter_sum = 0.0
        self._jitter_count = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Internal running state (``_rtt_sum``, ``_jitter_count``, etc.)
        is excluded — only the observable statistics are serialized.

        Returns:
            Dictionary with public statistics fields.
        """
        return {
            "sent": self.sent,
            "received": self.received,
            "lost": self.lost,
            "min_rtt": self.min_rtt,
            "max_rtt": self.max_rtt,
            "avg_rtt": round(self.avg_rtt, 3),
            "jitter": round(self.jitter, 3),
            "last_rtt": self.last_rtt,
            "loss_rate": round(self.loss_rate, 4),
            "loss_percent": round(self.loss_percent, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Internal running state is not restored (starts fresh).
        This is suitable for displaying historical statistics.

        Args:
            data: Dictionary with statistics fields.

        Returns:
            ProbeStats instance.
        """
        stats = cls()
        stats.sent = int(data.get("sent", 0))
        stats.received = int(data.get("received", 0))
        stats.lost = int(data.get("lost", 0))
        stats.min_rtt = float(data.get("min_rtt", 0.0))
        stats.max_rtt = float(data.get("max_rtt", 0.0))
        stats.avg_rtt = float(data.get("avg_rtt", 0.0))
        stats.jitter = float(data.get("jitter", 0.0))
        stats.last_rtt = data.get("last_rtt")
        # Restore internal state for correct further updates
        stats._rtt_sum = stats.avg_rtt * stats.received
        stats._rtt_count = stats.received
        return stats


@dataclass(frozen=True, slots=True)
class ProbeConfig:
    """Configuration for a probe campaign.

    Defines all parameters needed to run a UDP probe session against
    a single target.

    Attributes:
        host: Target IP address or hostname.
        port: Target UDP port number.
        count: Number of probe packets to send.
        interval: Seconds between consecutive probes.
        timeout: Seconds to wait for a response before marking as lost.
        payload_size: Size of the UDP payload in bytes.
        protocol: Probe protocol to use.
        ttl: IP Time-To-Live (0 = system default).

    Example::

        >>> config = ProbeConfig(host="1.2.3.4", port=27015, count=100)
        >>> config.interval
        1.0
    """

    host: str
    port: int = 27015
    count: int = 50
    interval: float = 1.0
    timeout: float = 3.0
    payload_size: int = 64
    protocol: ProbeProtocol = ProbeProtocol.UDP
    ttl: int = 0

    def __post_init__(self) -> None:
        """Validate probe configuration."""
        if not self.host or not self.host.strip():
            raise ValueError("ProbeConfig.host must not be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(
                f"ProbeConfig.port must be 1-65535, got {self.port}"
            )
        if self.count < 1:
            raise ValueError(f"ProbeConfig.count must be >= 1, got {self.count}")
        if self.interval < 0.01:
            raise ValueError(
                f"ProbeConfig.interval must be >= 0.01, got {self.interval}"
            )
        if self.timeout <= 0:
            raise ValueError(
                f"ProbeConfig.timeout must be > 0, got {self.timeout}"
            )
        if not (1 <= self.payload_size <= 1400):
            raise ValueError(
                f"ProbeConfig.payload_size must be 1-1400, got {self.payload_size}"
            )
        if self.ttl < 0 or self.ttl > 255:
            raise ValueError(
                f"ProbeConfig.ttl must be 0-255, got {self.ttl}"
            )

    @property
    def target(self) -> str:
        """Target as ``host:port`` string."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all configuration fields.
        """
        return {
            "host": self.host,
            "port": self.port,
            "count": self.count,
            "interval": self.interval,
            "timeout": self.timeout,
            "payload_size": self.payload_size,
            "protocol": self.protocol.value,
            "ttl": self.ttl,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with configuration fields.

        Returns:
            ProbeConfig instance.

        Raises:
            KeyError: If ``host`` is missing.
            ValueError: If validation fails.
        """
        return cls(
            host=str(data["host"]),
            port=int(data.get("port", 27015)),
            count=int(data.get("count", 50)),
            interval=float(data.get("interval", 1.0)),
            timeout=float(data.get("timeout", 3.0)),
            payload_size=int(data.get("payload_size", 64)),
            protocol=ProbeProtocol(data.get("protocol", "udp")),
            ttl=int(data.get("ttl", 0)),
        )
