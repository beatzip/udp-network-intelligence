"""History Repository — SQLite persistence for measurements, servers, rankings, errors.

Provides :class:`HistoryRepository` for full CRUD operations on four
history tables: measurements, servers, rankings, and errors.

Database is created automatically on first use with all required
tables and indexes.

Example::

    async with HistoryRepository("data/history.db") as repo:
        await repo.save_measurement(record)
        measurements = await repo.get_measurements(host="1.2.3.4")
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# SQL Statements
# ---------------------------------------------------------------------------

_CREATE_MEASUREMENTS = """
CREATE TABLE IF NOT EXISTS measurements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_host TEXT NOT NULL,
    target_port INTEGER NOT NULL DEFAULT 27015,
    timestamp REAL NOT NULL,
    mode TEXT NOT NULL DEFAULT 'normal',
    sent INTEGER NOT NULL DEFAULT 0,
    received INTEGER NOT NULL DEFAULT 0,
    lost INTEGER NOT NULL DEFAULT 0,
    min_rtt REAL NOT NULL DEFAULT 0.0,
    max_rtt REAL NOT NULL DEFAULT 0.0,
    avg_rtt REAL NOT NULL DEFAULT 0.0,
    jitter REAL NOT NULL DEFAULT 0.0,
    quality_grade TEXT NOT NULL DEFAULT '',
    quality_score REAL NOT NULL DEFAULT 0.0,
    duration_seconds REAL NOT NULL DEFAULT 0.0,
    payload_size INTEGER NOT NULL DEFAULT 64,
    protocol TEXT NOT NULL DEFAULT 'udp',
    metadata TEXT NOT NULL DEFAULT '{}'
);
"""

_CREATE_SERVERS = """
CREATE TABLE IF NOT EXISTS servers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 27015,
    first_seen REAL NOT NULL,
    last_seen REAL NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    map_name TEXT NOT NULL DEFAULT '',
    game TEXT NOT NULL DEFAULT '',
    app_id INTEGER NOT NULL DEFAULT 0,
    player_count INTEGER NOT NULL DEFAULT 0,
    max_players INTEGER NOT NULL DEFAULT 0,
    version TEXT NOT NULL DEFAULT '',
    country_code TEXT NOT NULL DEFAULT '',
    keywords TEXT NOT NULL DEFAULT '',
    metadata TEXT NOT NULL DEFAULT '{}',
    UNIQUE(host, port)
);
"""

_CREATE_RANKINGS = """
CREATE TABLE IF NOT EXISTS rankings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 27015,
    timestamp REAL NOT NULL,
    rtt_score REAL NOT NULL DEFAULT 0.0,
    loss_score REAL NOT NULL DEFAULT 0.0,
    jitter_score REAL NOT NULL DEFAULT 0.0,
    success_score REAL NOT NULL DEFAULT 0.0,
    history_score REAL NOT NULL DEFAULT 0.0,
    composite_score REAL NOT NULL DEFAULT 0.0,
    confidence REAL NOT NULL DEFAULT 0.0,
    final_score REAL NOT NULL DEFAULT 0.0,
    rank INTEGER NOT NULL DEFAULT 0,
    total_servers INTEGER NOT NULL DEFAULT 0,
    metadata TEXT NOT NULL DEFAULT '{}'
);
"""

_CREATE_ERRORS = """
CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp REAL NOT NULL,
    host TEXT NOT NULL DEFAULT '',
    port INTEGER NOT NULL DEFAULT 0,
    error_type TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    context TEXT NOT NULL DEFAULT '{}',
    resolved INTEGER NOT NULL DEFAULT 0
);
"""

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_measurements_host ON measurements(target_host, target_port);
CREATE INDEX IF NOT EXISTS idx_measurements_ts ON measurements(timestamp);
CREATE INDEX IF NOT EXISTS idx_measurements_mode ON measurements(mode);

CREATE INDEX IF NOT EXISTS idx_servers_host ON servers(host, port);
CREATE INDEX IF NOT EXISTS idx_servers_last ON servers(last_seen);

CREATE INDEX IF NOT EXISTS idx_rankings_host ON rankings(host, port);
CREATE INDEX IF NOT EXISTS idx_rankings_ts ON rankings(timestamp);
CREATE INDEX IF NOT EXISTS idx_rankings_score ON rankings(final_score);

CREATE INDEX IF NOT EXISTS idx_errors_ts ON errors(timestamp);
CREATE INDEX IF NOT EXISTS idx_errors_type ON errors(error_type);
CREATE INDEX IF NOT EXISTS idx_errors_host ON errors(host, port);
CREATE INDEX IF NOT EXISTS idx_errors_resolved ON errors(resolved);
"""

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class MeasurementRecord:
    """Record of a completed probe measurement campaign.

    Attributes:
        id: Database row ID (auto-assigned).
        target_host: Target IP or hostname.
        target_port: Target port.
        timestamp: Unix timestamp of measurement.
        mode: Test mode used (normal/deep/aggressive).
        sent: Total probes sent.
        received: Total probes received.
        lost: Total probes lost.
        min_rtt: Minimum RTT in ms.
        max_rtt: Maximum RTT in ms.
        avg_rtt: Average RTT in ms.
        jitter: RFC 3550 jitter in ms.
        quality_grade: Quality grade (A+, A, B+, etc.).
        quality_score: Numeric quality score (0.0-1.0).
        duration_seconds: Campaign duration in seconds.
        payload_size: UDP payload size.
        protocol: Protocol used.
        metadata: Additional JSON metadata.
    """

    id: int | None = None
    target_host: str = ""
    target_port: int = 27015
    timestamp: float = 0.0
    mode: str = "normal"
    sent: int = 0
    received: int = 0
    lost: int = 0
    min_rtt: float = 0.0
    max_rtt: float = 0.0
    avg_rtt: float = 0.0
    jitter: float = 0.0
    quality_grade: str = ""
    quality_score: float = 0.0
    duration_seconds: float = 0.0
    payload_size: int = 64
    protocol: str = "udp"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def loss_rate(self) -> float:
        """Packet loss rate (0.0-1.0)."""
        if self.sent == 0:
            return 0.0
        return self.lost / self.sent

    @property
    def loss_percent(self) -> float:
        """Packet loss percentage."""
        return self.loss_rate * 100.0

    @property
    def success_rate(self) -> float:
        """Success rate (0.0-1.0)."""
        return 1.0 - self.loss_rate

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "sent": self.sent,
            "received": self.received,
            "lost": self.lost,
            "min_rtt": self.min_rtt,
            "max_rtt": self.max_rtt,
            "avg_rtt": self.avg_rtt,
            "jitter": self.jitter,
            "quality_grade": self.quality_grade,
            "quality_score": self.quality_score,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


@dataclass
class ServerRecord:
    """Record of a known game server.

    Attributes:
        id: Database row ID.
        host: Server IP/hostname.
        port: Server port.
        first_seen: Unix timestamp when first seen.
        last_seen: Unix timestamp when last seen.
        name: Server name.
        map_name: Current map.
        game: Game folder.
        app_id: Steam AppID.
        player_count: Current player count.
        max_players: Max player slots.
        version: Server version.
        country_code: GeoIP country code.
        keywords: Server keywords/tags.
        metadata: Additional JSON data.
    """

    id: int | None = None
    host: str = ""
    port: int = 27015
    first_seen: float = 0.0
    last_seen: float = 0.0
    name: str = ""
    map_name: str = ""
    game: str = ""
    app_id: int = 0
    player_count: int = 0
    max_players: int = 0
    version: str = ""
    country_code: str = ""
    keywords: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def target(self) -> str:
        """Target as ``host:port``."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "name": self.name,
            "map_name": self.map_name,
            "game": self.game,
            "app_id": self.app_id,
            "player_count": self.player_count,
            "max_players": self.max_players,
            "version": self.version,
            "country_code": self.country_code,
            "keywords": self.keywords,
        }


@dataclass
class RankingRecord:
    """Record of a server ranking snapshot.

    Attributes:
        id: Database row ID.
        host: Server host.
        port: Server port.
        timestamp: Unix timestamp of ranking.
        rtt_score: Normalized RTT score.
        loss_score: Normalized loss score.
        jitter_score: Normalized jitter score.
        success_score: Normalized success rate.
        history_score: Normalized history score.
        composite_score: Weighted composite score.
        confidence: Confidence multiplier.
        final_score: Final ranking score.
        rank: Position in ranking.
        total_servers: Total servers ranked.
        metadata: Additional JSON data.
    """

    id: int | None = None
    host: str = ""
    port: int = 27015
    timestamp: float = 0.0
    rtt_score: float = 0.0
    loss_score: float = 0.0
    jitter_score: float = 0.0
    success_score: float = 0.0
    history_score: float = 0.0
    composite_score: float = 0.0
    confidence: float = 0.0
    final_score: float = 0.0
    rank: int = 0
    total_servers: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "host": self.host,
            "port": self.port,
            "timestamp": self.timestamp,
            "final_score": self.final_score,
            "rank": self.rank,
            "total_servers": self.total_servers,
        }


@dataclass
class ErrorRecord:
    """Record of an error event.

    Attributes:
        id: Database row ID.
        timestamp: Unix timestamp.
        host: Target host (if applicable).
        port: Target port (if applicable).
        error_type: Error category (timeout, connection_refused, etc.).
        error_message: Human-readable error message.
        context: Additional JSON context.
        resolved: Whether the error has been resolved.
    """

    id: int | None = None
    timestamp: float = 0.0
    host: str = ""
    port: int = 0
    error_type: str = ""
    error_message: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "host": self.host,
            "port": self.port,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "resolved": self.resolved,
        }


# ---------------------------------------------------------------------------
# Query filters
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class MeasurementFilter:
    """Filter criteria for querying measurements."""
    host: str | None = None
    port: int | None = None
    mode: str | None = None
    start_time: float | None = None
    end_time: float | None = None
    min_quality: float | None = None
    limit: int = 100
    offset: int = 0
    order_desc: bool = True


@dataclass(frozen=True, slots=True)
class ErrorFilter:
    """Filter criteria for querying errors."""
    host: str | None = None
    port: int | None = None
    error_type: str | None = None
    resolved: bool | None = None
    start_time: float | None = None
    end_time: float | None = None
    limit: int = 100
    offset: int = 0


# ---------------------------------------------------------------------------
# History Repository
# ---------------------------------------------------------------------------

class HistoryRepository:
    """SQLite-based history repository.

    Manages four tables: measurements, servers, rankings, errors.
    Database is created automatically on first use.

    Thread-safe: all DB operations go through an asyncio lock.

    Example::

        repo = HistoryRepository("data/history.db")
        await repo.initialize()
        await repo.save_measurement(record)
        results = await repo.get_measurements(host="1.2.3.4")
        await repo.close()
    """

    def __init__(self, db_path: str = "data/history.db") -> None:
        """Initialize the repository.

        Args:
            db_path: Path to the SQLite database file.
        """
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    @property
    def db_path(self) -> str:
        """Database file path."""
        return self._db_path

    @property
    def is_initialized(self) -> bool:
        """Whether the database has been initialized."""
        return self._initialized

    async def initialize(self) -> None:
        """Create the database and all tables if they don't exist.

        Safe to call multiple times.
        """
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            # Ensure directory exists
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

            # Connect and create tables
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")

            # Create all tables
            for stmt in [
                _CREATE_MEASUREMENTS,
                _CREATE_SERVERS,
                _CREATE_RANKINGS,
                _CREATE_ERRORS,
                _CREATE_META,
                _CREATE_INDEXES,
            ]:
                self._conn.executescript(stmt)

            # Set schema version
            self._set_meta("schema_version", str(SCHEMA_VERSION))
            self._conn.commit()

            self._initialized = True
            logger.info("Database initialized: %s", self._db_path)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        """Get the database connection.

        Raises:
            RuntimeError: If the database is not initialized.
        """
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    def _get_meta(self, key: str) -> str | None:
        """Get a metadata value."""
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        """Set a metadata value."""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    # ------------------------------------------------------------------
    # Measurements CRUD
    # ------------------------------------------------------------------

    async def save_measurement(self, record: MeasurementRecord) -> int:
        """Save a measurement record.

        Args:
            record: MeasurementRecord to save.

        Returns:
            Database row ID.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                """INSERT INTO measurements
                (target_host, target_port, timestamp, mode, sent, received,
                 lost, min_rtt, max_rtt, avg_rtt, jitter, quality_grade,
                 quality_score, duration_seconds, payload_size, protocol, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.target_host,
                    record.target_port,
                    record.timestamp,
                    record.mode,
                    record.sent,
                    record.received,
                    record.lost,
                    record.min_rtt,
                    record.max_rtt,
                    record.avg_rtt,
                    record.jitter,
                    record.quality_grade,
                    record.quality_score,
                    record.duration_seconds,
                    record.payload_size,
                    record.protocol,
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    async def get_measurement(self, measurement_id: int) -> MeasurementRecord | None:
        """Get a measurement by ID.

        Args:
            measurement_id: Database row ID.

        Returns:
            MeasurementRecord or None if not found.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
            ).fetchone()
            if row is None:
                return None
            return self._row_to_measurement(row)

    async def get_measurements(
        self,
        host: str | None = None,
        port: int | None = None,
        mode: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
        offset: int = 0,
        order_desc: bool = True,
    ) -> list[MeasurementRecord]:
        """Query measurements with filters.

        Args:
            host: Filter by target host.
            port: Filter by target port.
            mode: Filter by test mode.
            start_time: Only records after this timestamp.
            end_time: Only records before this timestamp.
            limit: Maximum records to return.
            offset: Skip first N records.
            order_desc: Sort by timestamp descending.

        Returns:
            List of matching MeasurementRecords.
        """
        async with self._lock:
            conn = self._get_conn()
            conditions: list[str] = []
            params: list[Any] = []

            if host:
                conditions.append("target_host = ?")
                params.append(host)
            if port is not None:
                conditions.append("target_port = ?")
                params.append(port)
            if mode:
                conditions.append("mode = ?")
                params.append(mode)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            where = " AND ".join(conditions) if conditions else "1=1"
            order = "DESC" if order_desc else "ASC"

            rows = conn.execute(
                f"SELECT * FROM measurements WHERE {where} "
                f"ORDER BY timestamp {order} LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [self._row_to_measurement(r) for r in rows]

    async def count_measurements(
        self, host: str | None = None
    ) -> int:
        """Count measurement records.

        Args:
            host: Optional host filter.

        Returns:
            Count of matching records.
        """
        async with self._lock:
            conn = self._get_conn()
            if host:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM measurements WHERE target_host = ?",
                    (host,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM measurements"
                ).fetchone()
            return row["cnt"] if row else 0

    async def delete_measurements(
        self, host: str, before_timestamp: float | None = None
    ) -> int:
        """Delete measurement records.

        Args:
            host: Target host to delete.
            before_timestamp: Only delete records before this time.

        Returns:
            Number of deleted records.
        """
        async with self._lock:
            conn = self._get_conn()
            if before_timestamp is not None:
                cursor = conn.execute(
                    "DELETE FROM measurements WHERE target_host = ? AND timestamp < ?",
                    (host, before_timestamp),
                )
            else:
                cursor = conn.execute(
                    "DELETE FROM measurements WHERE target_host = ?", (host,)
                )
            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Servers CRUD
    # ------------------------------------------------------------------

    async def save_server(self, record: ServerRecord) -> int:
        """Save or update a server record.

        Uses INSERT OR UPDATE semantics: if a server with the same
        host+port exists, it is updated.

        Args:
            record: ServerRecord to save.

        Returns:
            Database row ID.
        """
        async with self._lock:
            conn = self._get_conn()
            now = time.time()
            if record.first_seen <= 0:
                record.first_seen = now
            record.last_seen = now

            cursor = conn.execute(
                """INSERT INTO servers
                (host, port, first_seen, last_seen, name, map_name,
                 game, app_id, player_count, max_players, version,
                 country_code, keywords, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, port) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    name = CASE WHEN excluded.name != '' THEN excluded.name ELSE servers.name END,
                    map_name = CASE WHEN excluded.map_name != '' THEN excluded.map_name ELSE servers.map_name END,
                    game = CASE WHEN excluded.game != '' THEN excluded.game ELSE servers.game END,
                    app_id = CASE WHEN excluded.app_id != 0 THEN excluded.app_id ELSE servers.app_id END,
                    player_count = excluded.player_count,
                    max_players = excluded.max_players,
                    version = CASE WHEN excluded.version != '' THEN excluded.version ELSE servers.version END,
                    country_code = CASE WHEN excluded.country_code != '' THEN excluded.country_code ELSE servers.country_code END,
                    keywords = CASE WHEN excluded.keywords != '' THEN excluded.keywords ELSE servers.keywords END,
                    metadata = excluded.metadata
                """,
                (
                    record.host, record.port, record.first_seen, record.last_seen,
                    record.name, record.map_name, record.game, record.app_id,
                    record.player_count, record.max_players, record.version,
                    record.country_code, record.keywords, json.dumps(record.metadata),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    async def get_server(self, host: str, port: int) -> ServerRecord | None:
        """Get a server by host+port.

        Args:
            host: Server host.
            port: Server port.

        Returns:
            ServerRecord or None.
        """
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute(
                "SELECT * FROM servers WHERE host = ? AND port = ?",
                (host, port),
            ).fetchone()
            if row is None:
                return None
            return self._row_to_server(row)

    async def get_servers(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: str = "last_seen",
        order_desc: bool = True,
    ) -> list[ServerRecord]:
        """List servers.

        Args:
            limit: Maximum records.
            offset: Skip N records.
            order_by: Column to sort by.
            order_desc: Sort direction.

        Returns:
            List of ServerRecords.
        """
        async with self._lock:
            conn = self._get_conn()
            order = "DESC" if order_desc else "ASC"
            rows = conn.execute(
                f"SELECT * FROM servers ORDER BY {order_by} {order} LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [self._row_to_server(r) for r in rows]

    async def search_servers(self, query: str, limit: int = 50) -> list[ServerRecord]:
        """Search servers by name, game, or keywords.

        Args:
            query: Search string.
            limit: Maximum results.

        Returns:
            Matching ServerRecords.
        """
        async with self._lock:
            conn = self._get_conn()
            pattern = f"%{query}%"
            rows = conn.execute(
                """SELECT * FROM servers
                WHERE name LIKE ? OR game LIKE ? OR keywords LIKE ? OR host LIKE ?
                LIMIT ?""",
                (pattern, pattern, pattern, pattern, limit),
            ).fetchall()
            return [self._row_to_server(r) for r in rows]

    async def count_servers(self) -> int:
        """Count total known servers."""
        async with self._lock:
            conn = self._get_conn()
            row = conn.execute("SELECT COUNT(*) as cnt FROM servers").fetchone()
            return row["cnt"] if row else 0

    async def delete_server(self, host: str, port: int) -> bool:
        """Delete a server record.

        Args:
            host: Server host.
            port: Server port.

        Returns:
            True if deleted.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM servers WHERE host = ? AND port = ?",
                (host, port),
            )
            conn.commit()
            return cursor.rowcount > 0

    # ------------------------------------------------------------------
    # Rankings CRUD
    # ------------------------------------------------------------------

    async def save_ranking(self, record: RankingRecord) -> int:
        """Save a ranking record.

        Args:
            record: RankingRecord to save.

        Returns:
            Database row ID.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                """INSERT INTO rankings
                (host, port, timestamp, rtt_score, loss_score, jitter_score,
                 success_score, history_score, composite_score, confidence,
                 final_score, rank, total_servers, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.host, record.port, record.timestamp,
                    record.rtt_score, record.loss_score, record.jitter_score,
                    record.success_score, record.history_score,
                    record.composite_score, record.confidence,
                    record.final_score, record.rank, record.total_servers,
                    json.dumps(record.metadata),
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    async def get_rankings(
        self,
        host: str | None = None,
        start_time: float | None = None,
        end_time: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RankingRecord]:
        """Query ranking records.

        Args:
            host: Filter by host.
            start_time: Filter by start time.
            end_time: Filter by end time.
            limit: Maximum records.
            offset: Skip N records.

        Returns:
            List of RankingRecords.
        """
        async with self._lock:
            conn = self._get_conn()
            conditions: list[str] = []
            params: list[Any] = []

            if host:
                conditions.append("host = ?")
                params.append(host)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time)
            if end_time is not None:
                conditions.append("timestamp <= ?")
                params.append(end_time)

            where = " AND ".join(conditions) if conditions else "1=1"

            rows = conn.execute(
                f"SELECT * FROM rankings WHERE {where} "
                f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [self._row_to_ranking(r) for r in rows]

    async def get_latest_rankings(self, limit: int = 20) -> list[RankingRecord]:
        """Get the most recent ranking snapshot.

        Args:
            limit: Maximum servers in ranking.

        Returns:
            List of latest RankedRecords sorted by rank.
        """
        async with self._lock:
            conn = self._get_conn()
            # Get the latest timestamp
            row = conn.execute(
                "SELECT MAX(timestamp) as max_ts FROM rankings"
            ).fetchone()
            if row is None or row["max_ts"] is None:
                return []

            max_ts = row["max_ts"]
            rows = conn.execute(
                "SELECT * FROM rankings WHERE timestamp = ? ORDER BY rank ASC LIMIT ?",
                (max_ts, limit),
            ).fetchall()
            return [self._row_to_ranking(r) for r in rows]

    async def count_rankings(self, host: str | None = None) -> int:
        """Count ranking records."""
        async with self._lock:
            conn = self._get_conn()
            if host:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM rankings WHERE host = ?", (host,)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM rankings"
                ).fetchone()
            return row["cnt"] if row else 0

    # ------------------------------------------------------------------
    # Errors CRUD
    # ------------------------------------------------------------------

    async def save_error(self, record: ErrorRecord) -> int:
        """Save an error record.

        Args:
            record: ErrorRecord to save.

        Returns:
            Database row ID.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                """INSERT INTO errors
                (timestamp, host, port, error_type, error_message, context, resolved)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.timestamp, record.host, record.port,
                    record.error_type, record.error_message,
                    json.dumps(record.context), 1 if record.resolved else 0,
                ),
            )
            conn.commit()
            return cursor.lastrowid or 0

    async def get_errors(
        self,
        host: str | None = None,
        port: int | None = None,
        error_type: str | None = None,
        resolved: bool | None = None,
        start_time: float | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ErrorRecord]:
        """Query error records.

        Args:
            host: Filter by host.
            port: Filter by port.
            error_type: Filter by error type.
            resolved: Filter by resolved status.
            start_time: Filter by start time.
            limit: Maximum records.
            offset: Skip N records.

        Returns:
            List of ErrorRecords.
        """
        async with self._lock:
            conn = self._get_conn()
            conditions: list[str] = []
            params: list[Any] = []

            if host:
                conditions.append("host = ?")
                params.append(host)
            if port is not None:
                conditions.append("port = ?")
                params.append(port)
            if error_type:
                conditions.append("error_type = ?")
                params.append(error_type)
            if resolved is not None:
                conditions.append("resolved = ?")
                params.append(1 if resolved else 0)
            if start_time is not None:
                conditions.append("timestamp >= ?")
                params.append(start_time)

            where = " AND ".join(conditions) if conditions else "1=1"

            rows = conn.execute(
                f"SELECT * FROM errors WHERE {where} "
                f"ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
            return [self._row_to_error(r) for r in rows]

    async def mark_error_resolved(self, error_id: int) -> bool:
        """Mark an error as resolved.

        Args:
            error_id: Error record ID.

        Returns:
            True if updated.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "UPDATE errors SET resolved = 1 WHERE id = ?", (error_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    async def count_errors(
        self, host: str | None = None, resolved: bool | None = None
    ) -> int:
        """Count error records."""
        async with self._lock:
            conn = self._get_conn()
            conditions: list[str] = []
            params: list[Any] = []
            if host:
                conditions.append("host = ?")
                params.append(host)
            if resolved is not None:
                conditions.append("resolved = ?")
                params.append(1 if resolved else 0)
            where = " AND ".join(conditions) if conditions else "1=1"
            row = conn.execute(
                f"SELECT COUNT(*) as cnt FROM errors WHERE {where}", params
            ).fetchone()
            return row["cnt"] if row else 0

    async def delete_old_errors(self, before_timestamp: float) -> int:
        """Delete old unresolved errors.

        Args:
            before_timestamp: Only delete errors before this time.

        Returns:
            Number of deleted records.
        """
        async with self._lock:
            conn = self._get_conn()
            cursor = conn.execute(
                "DELETE FROM errors WHERE timestamp < ? AND resolved = 1",
                (before_timestamp,),
            )
            conn.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict[str, Any]:
        """Get aggregate statistics across all tables.

        Returns:
            Dictionary with counts and summary statistics.
        """
        async with self._lock:
            conn = self._get_conn()

            measurements = conn.execute(
                "SELECT COUNT(*) as cnt, AVG(avg_rtt) as avg_rtt, "
                "AVG(quality_score) as avg_quality FROM measurements"
            ).fetchone()

            servers = conn.execute(
                "SELECT COUNT(*) as cnt FROM servers"
            ).fetchone()

            errors = conn.execute(
                "SELECT COUNT(*) as cnt, SUM(CASE WHEN resolved=1 THEN 1 ELSE 0 END) as resolved "
                "FROM errors"
            ).fetchone()

            return {
                "measurements_total": measurements["cnt"] if measurements else 0,
                "measurements_avg_rtt": round(measurements["avg_rtt"] or 0, 2) if measurements else 0,
                "measurements_avg_quality": round(measurements["avg_quality"] or 0, 4) if measurements else 0,
                "servers_total": servers["cnt"] if servers else 0,
                "errors_total": errors["cnt"] if errors else 0,
                "errors_resolved": errors["resolved"] or 0 if errors else 0,
            }

    # ------------------------------------------------------------------
    # Row mappers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_measurement(row: sqlite3.Row) -> MeasurementRecord:
        """Convert a database row to MeasurementRecord."""
        metadata_str = row["metadata"]
        metadata = json.loads(metadata_str) if metadata_str else {}
        return MeasurementRecord(
            id=row["id"],
            target_host=row["target_host"],
            target_port=row["target_port"],
            timestamp=row["timestamp"],
            mode=row["mode"],
            sent=row["sent"],
            received=row["received"],
            lost=row["lost"],
            min_rtt=row["min_rtt"],
            max_rtt=row["max_rtt"],
            avg_rtt=row["avg_rtt"],
            jitter=row["jitter"],
            quality_grade=row["quality_grade"],
            quality_score=row["quality_score"],
            duration_seconds=row["duration_seconds"],
            payload_size=row["payload_size"],
            protocol=row["protocol"],
            metadata=metadata,
        )

    @staticmethod
    def _row_to_server(row: sqlite3.Row) -> ServerRecord:
        """Convert a database row to ServerRecord."""
        metadata_str = row["metadata"]
        metadata = json.loads(metadata_str) if metadata_str else {}
        return ServerRecord(
            id=row["id"],
            host=row["host"],
            port=row["port"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            name=row["name"],
            map_name=row["map_name"],
            game=row["game"],
            app_id=row["app_id"],
            player_count=row["player_count"],
            max_players=row["max_players"],
            version=row["version"],
            country_code=row["country_code"],
            keywords=row["keywords"],
            metadata=metadata,
        )

    @staticmethod
    def _row_to_ranking(row: sqlite3.Row) -> RankingRecord:
        """Convert a database row to RankingRecord."""
        metadata_str = row["metadata"]
        metadata = json.loads(metadata_str) if metadata_str else {}
        return RankingRecord(
            id=row["id"],
            host=row["host"],
            port=row["port"],
            timestamp=row["timestamp"],
            rtt_score=row["rtt_score"],
            loss_score=row["loss_score"],
            jitter_score=row["jitter_score"],
            success_score=row["success_score"],
            history_score=row["history_score"],
            composite_score=row["composite_score"],
            confidence=row["confidence"],
            final_score=row["final_score"],
            rank=row["rank"],
            total_servers=row["total_servers"],
            metadata=metadata,
        )

    @staticmethod
    def _row_to_error(row: sqlite3.Row) -> ErrorRecord:
        """Convert a database row to ErrorRecord."""
        context_str = row["context"]
        context = json.loads(context_str) if context_str else {}
        return ErrorRecord(
            id=row["id"],
            timestamp=row["timestamp"],
            host=row["host"],
            port=row["port"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            context=context,
            resolved=bool(row["resolved"]),
        )
