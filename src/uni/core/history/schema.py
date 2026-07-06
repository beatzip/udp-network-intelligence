"""History persistence data models — SQLite schema and record structures.

Defines the data structures for storing probe results in the local
SQLite database: table schemas, record types, and query result models.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Self


@dataclass
class ProbeRecord:
    """Database record for a stored probe result.

    Maps to the ``probe_results`` SQLite table. Each record captures
    the aggregated statistics from a completed probe campaign against
    a single target.

    Attributes:
        id: Auto-generated primary key (None before insertion).
        target_host: Target IP or hostname.
        target_port: Target port number.
        timestamp: When the probe campaign completed (UTC).
        sent: Total probes sent.
        received: Total probes received successfully.
        lost: Total probes lost.
        min_rtt: Minimum RTT in milliseconds.
        max_rtt: Maximum RTT in milliseconds.
        avg_rtt: Average RTT in milliseconds.
        jitter: Inter-packet jitter in milliseconds.
        quality_grade: Quality grade string (e.g. ``"A"``).
        duration_seconds: Campaign duration in seconds.
        protocol: Probe protocol used (e.g. ``"udp"``).
        payload_size: Probe payload size in bytes.

    Example::

        >>> record = ProbeRecord(
        ...     target_host="1.2.3.4",
        ...     target_port=27015,
        ...     timestamp=datetime.now(timezone.utc),
        ...     sent=50,
        ...     received=49,
        ...     lost=1,
        ...     min_rtt=12.5,
        ...     max_rtt=45.2,
        ...     avg_rtt=18.3,
        ...     jitter=5.1,
        ...     quality_grade="A",
        ... )
        >>> record.loss_rate
        0.02
    """

    id: int | None = None
    target_host: str = ""
    target_port: int = 0
    timestamp: datetime | None = None
    sent: int = 0
    received: int = 0
    lost: int = 0
    min_rtt: float = 0.0
    max_rtt: float = 0.0
    avg_rtt: float = 0.0
    jitter: float = 0.0
    quality_grade: str = ""
    duration_seconds: float = 0.0
    protocol: str = "udp"
    payload_size: int = 64

    def __post_init__(self) -> None:
        """Validate record fields."""
        if self.target_host and not self.target_host.strip():
            raise ValueError("ProbeRecord.target_host must not be blank")
        if self.target_port < 0 or self.target_port > 65535:
            raise ValueError(
                f"ProbeRecord.target_port must be 0-65535, got {self.target_port}"
            )
        if self.sent < 0:
            raise ValueError(f"ProbeRecord.sent must be >= 0, got {self.sent}")
        if self.received < 0:
            raise ValueError(
                f"ProbeRecord.received must be >= 0, got {self.received}"
            )
        if self.lost < 0:
            raise ValueError(f"ProbeRecord.lost must be >= 0, got {self.lost}")
        if self.min_rtt < 0:
            raise ValueError(
                f"ProbeRecord.min_rtt must be >= 0, got {self.min_rtt}"
            )
        if self.max_rtt < self.min_rtt and self.sent > 0:
            raise ValueError(
                f"ProbeRecord.max_rtt ({self.max_rtt}) < min_rtt ({self.min_rtt})"
            )

    @property
    def loss_rate(self) -> float:
        """Packet loss rate as a fraction (0.0 to 1.0)."""
        if self.sent == 0:
            return 0.0
        return self.lost / self.sent

    @property
    def loss_percent(self) -> float:
        """Packet loss as a percentage."""
        return self.loss_rate * 100.0

    @property
    def target(self) -> str:
        """Target as ``host:port`` string."""
        return f"{self.target_host}:{self.target_port}"

    @property
    def timestamp_iso(self) -> str:
        """ISO 8601 formatted timestamp string."""
        if self.timestamp is None:
            return ""
        return self.timestamp.isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Datetime is serialized to ISO 8601 format.

        Returns:
            Dictionary with all record fields.
        """
        return {
            "id": self.id,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "timestamp": self.timestamp_iso,
            "sent": self.sent,
            "received": self.received,
            "lost": self.lost,
            "min_rtt": self.min_rtt,
            "max_rtt": self.max_rtt,
            "avg_rtt": self.avg_rtt,
            "jitter": self.jitter,
            "quality_grade": self.quality_grade,
            "duration_seconds": self.duration_seconds,
            "protocol": self.protocol,
            "payload_size": self.payload_size,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with record fields.

        Returns:
            ProbeRecord instance.
        """
        ts_raw = data.get("timestamp", "")
        timestamp: datetime | None = None
        if isinstance(ts_raw, str) and ts_raw:
            try:
                timestamp = datetime.fromisoformat(ts_raw)
            except ValueError:
                timestamp = None
        elif isinstance(ts_raw, datetime):
            timestamp = ts_raw

        return cls(
            id=data.get("id"),
            target_host=str(data.get("target_host", "")),
            target_port=int(data.get("target_port", 0)),
            timestamp=timestamp,
            sent=int(data.get("sent", 0)),
            received=int(data.get("received", 0)),
            lost=int(data.get("lost", 0)),
            min_rtt=float(data.get("min_rtt", 0.0)),
            max_rtt=float(data.get("max_rtt", 0.0)),
            avg_rtt=float(data.get("avg_rtt", 0.0)),
            jitter=float(data.get("jitter", 0.0)),
            quality_grade=str(data.get("quality_grade", "")),
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            protocol=str(data.get("protocol", "udp")),
            payload_size=int(data.get("payload_size", 64)),
        )

    @classmethod
    def from_row(cls, row: tuple[Any, ...]) -> Self:
        """Deserialize from a SQLite row tuple.

        Column order must match the ``probe_results`` table schema:
        id, target_host, target_port, timestamp, sent, received, lost,
        min_rtt, max_rtt, avg_rtt, jitter, quality_grade,
        duration_seconds, protocol, payload_size.

        Args:
            row: SQLite row as a tuple.

        Returns:
            ProbeRecord instance.
        """
        ts_raw = row[3]
        timestamp: datetime | None = None
        if isinstance(ts_raw, str) and ts_raw:
            try:
                timestamp = datetime.fromisoformat(ts_raw)
            except ValueError:
                timestamp = None
        elif isinstance(ts_raw, datetime):
            timestamp = ts_raw

        return cls(
            id=row[0],
            target_host=str(row[1]),
            target_port=int(row[2]),
            timestamp=timestamp,
            sent=int(row[4]),
            received=int(row[5]),
            lost=int(row[6]),
            min_rtt=float(row[7]),
            max_rtt=float(row[8]),
            avg_rtt=float(row[9]),
            jitter=float(row[10]),
            quality_grade=str(row[11]),
            duration_seconds=float(row[12]) if row[12] is not None else 0.0,
            protocol=str(row[13]) if row[13] is not None else "udp",
            payload_size=int(row[14]) if row[14] is not None else 64,
        )

    def to_row(self) -> tuple[Any, ...]:
        """Serialize to a SQLite row tuple.

        Returns:
            Tuple matching the ``probe_results`` table column order.
        """
        return (
            self.id,
            self.target_host,
            self.target_port,
            self.timestamp_iso,
            self.sent,
            self.received,
            self.lost,
            self.min_rtt,
            self.max_rtt,
            self.avg_rtt,
            self.jitter,
            self.quality_grade,
            self.duration_seconds,
            self.protocol,
            self.payload_size,
        )


# SQL schema for the probe_results table
SCHEMA_VERSION = 1

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS probe_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_host TEXT NOT NULL,
    target_port INTEGER NOT NULL,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent INTEGER NOT NULL DEFAULT 0,
    received INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    min_rtt REAL NOT NULL DEFAULT 0.0,
    max_rtt REAL NOT NULL DEFAULT 0.0,
    avg_rtt REAL NOT NULL DEFAULT 0.0,
    jitter REAL NOT NULL DEFAULT 0.0,
    quality_grade TEXT NOT NULL DEFAULT '',
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    protocol TEXT NOT NULL DEFAULT 'udp',
    payload_size INTEGER NOT NULL DEFAULT 64
);

CREATE INDEX IF NOT EXISTS idx_probe_target
    ON probe_results(target_host, target_port);

CREATE INDEX IF NOT EXISTS idx_probe_timestamp
    ON probe_results(timestamp);

CREATE INDEX IF NOT EXISTS idx_probe_quality
    ON probe_results(quality_grade);
"""


@dataclass(frozen=True, slots=True)
class HistoryFilter:
    """Filter criteria for querying probe history.

    Attributes:
        target_host: Filter by target host (partial match).
        target_port: Filter by target port (exact match).
        quality_grade: Filter by quality grade.
        start_time: Only records after this datetime.
        end_time: Only records before this datetime.
        limit: Maximum number of records to return.
        offset: Number of records to skip (for pagination).
        order_desc: True for newest-first, False for oldest-first.

    Example::

        >>> f = HistoryFilter(target_host="1.2.3.4", limit=10)
        >>> f.to_dict()["limit"]
        10
    """

    target_host: str | None = None
    target_port: int | None = None
    quality_grade: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = 100
    offset: int = 0
    order_desc: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary."""
        return {
            "target_host": self.target_host,
            "target_port": self.target_port,
            "quality_grade": self.quality_grade,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "limit": self.limit,
            "offset": self.offset,
            "order_desc": self.order_desc,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with filter fields.

        Returns:
            HistoryFilter instance.
        """
        start_raw = data.get("start_time")
        end_raw = data.get("end_time")
        start_time: datetime | None = None
        end_time: datetime | None = None
        if isinstance(start_raw, str) and start_raw:
            with contextlib.suppress(ValueError):
                start_time = datetime.fromisoformat(start_raw)
        if isinstance(end_raw, str) and end_raw:
            with contextlib.suppress(ValueError):
                end_time = datetime.fromisoformat(end_raw)

        return cls(
            target_host=data.get("target_host"),
            target_port=data.get("target_port"),
            quality_grade=data.get("quality_grade"),
            start_time=start_time,
            end_time=end_time,
            limit=int(data.get("limit", 100)),
            offset=int(data.get("offset", 0)),
            order_desc=bool(data.get("order_desc", True)),
        )
