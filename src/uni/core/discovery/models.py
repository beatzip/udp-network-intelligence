"""Game server discovery data models — A2S query results and server info.

Defines the data structures for game server information retrieved via
the A2S (Source Engine) query protocol: server info, player lists,
server rules, and combined query results.

All dataclasses support JSON round-tripping via ``to_dict()`` / ``from_dict()``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from uni.app.constants import ServerType


@dataclass(frozen=True, slots=True)
class ServerInfo:
    """Game server information from A2S_INFO response.

    Contains the core metadata about a game server: name, map,
    player counts, and engine version information.

    Attributes:
        name: Server name (may contain color codes like ``^1``).
        map_name: Current map name (e.g. ``"de_dust2"``).
        game: Game folder name (e.g. ``"csgo"``, ``"cs2"``).
        app_id: Steam Application ID (e.g. 730 for CS2).
        player_count: Current number of human players.
        max_players: Maximum player capacity.
        bot_count: Number of bot players.
        version: Server version string.
        protocol: Source engine protocol version.
        folder: Game folder name.
        steam_id: Server Steam ID (64-bit).
        keywords: Server keywords/tags.
        game_port: Game-specific port (usually same as query port).

    Example::

        >>> info = ServerInfo(name="My Server", map_name="de_dust2", app_id=730)
        >>> info.is_full
        False
    """

    name: str = ""
    map_name: str = ""
    game: str = ""
    app_id: int = 0
    player_count: int = 0
    max_players: int = 0
    bot_count: int = 0
    version: str = ""
    protocol: int = 0
    folder: str = ""
    steam_id: int = 0
    keywords: str = ""
    game_port: int = 0

    def __post_init__(self) -> None:
        """Validate server info fields."""
        if self.app_id < 0:
            raise ValueError(f"ServerInfo.app_id must be >= 0, got {self.app_id}")
        if self.player_count < 0:
            raise ValueError(
                f"ServerInfo.player_count must be >= 0, got {self.player_count}"
            )
        if self.max_players < 0:
            raise ValueError(
                f"ServerInfo.max_players must be >= 0, got {self.max_players}"
            )
        if self.bot_count < 0:
            raise ValueError(f"ServerInfo.bot_count must be >= 0, got {self.bot_count}")
        if self.player_count > self.max_players and self.max_players > 0:
            raise ValueError(
                f"ServerInfo.player_count ({self.player_count}) > "
                f"max_players ({self.max_players})"
            )

    @property
    def is_full(self) -> bool:
        """True if the server is at maximum capacity."""
        if self.max_players <= 0:
            return False
        return self.player_count >= self.max_players

    @property
    def free_slots(self) -> int:
        """Number of available player slots."""
        if self.max_players <= 0:
            return 0
        return max(0, self.max_players - self.player_count)

    @property
    def human_count(self) -> int:
        """Number of human players (total minus bots)."""
        return max(0, self.player_count - self.bot_count)

    @property
    def server_type(self) -> ServerType:
        """Infer the server type from app_id."""
        type_map = {
            730: ServerType.CS2,
            740: ServerType.CSGO,
            440: ServerType.TF2,
            550: ServerType.L4D2,
        }
        return type_map.get(self.app_id, ServerType.CUSTOM)

    @property
    def display_name(self) -> str:
        """Clean server name (without source engine color codes)."""
        # Strip ^[0-9] color codes
        import re

        return re.sub(r"\^\d", "", self.name).strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all server info fields.
        """
        return {
            "name": self.name,
            "map_name": self.map_name,
            "game": self.game,
            "app_id": self.app_id,
            "player_count": self.player_count,
            "max_players": self.max_players,
            "bot_count": self.bot_count,
            "version": self.version,
            "protocol": self.protocol,
            "folder": self.folder,
            "steam_id": self.steam_id,
            "keywords": self.keywords,
            "game_port": self.game_port,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with server info fields.

        Returns:
            ServerInfo instance.
        """
        return cls(
            name=str(data.get("name", "")),
            map_name=str(data.get("map_name", "")),
            game=str(data.get("game", "")),
            app_id=int(data.get("app_id", 0)),
            player_count=int(data.get("player_count", 0)),
            max_players=int(data.get("max_players", 0)),
            bot_count=int(data.get("bot_count", 0)),
            version=str(data.get("version", "")),
            protocol=int(data.get("protocol", 0)),
            folder=str(data.get("folder", "")),
            steam_id=int(data.get("steam_id", 0)),
            keywords=str(data.get("keywords", "")),
            game_port=int(data.get("game_port", 0)),
        )


@dataclass(frozen=True, slots=True)
class PlayerInfo:
    """Player information from A2S_PLAYER response.

    Represents a single player on the server with their score
    and connection duration.

    Attributes:
        index: Player index (0-based).
        name: Player name (may contain color codes).
        score: Player score (kills - deaths or similar).
        duration: Connection duration in seconds.

    Example::

        >>> player = PlayerInfo(name="ProPlayer", score=25, duration=1800.0)
        >>> player.duration_minutes
        30.0
    """

    index: int = 0
    name: str = ""
    score: int = 0
    duration: float = 0.0

    def __post_init__(self) -> None:
        """Validate player info fields."""
        if self.index < 0:
            raise ValueError(f"PlayerInfo.index must be >= 0, got {self.index}")
        if self.duration < 0:
            raise ValueError(f"PlayerInfo.duration must be >= 0, got {self.duration}")

    @property
    def duration_minutes(self) -> float:
        """Connection duration in minutes."""
        return self.duration / 60.0

    @property
    def duration_hours(self) -> float:
        """Connection duration in hours."""
        return self.duration / 3600.0

    @property
    def display_name(self) -> str:
        """Clean player name (without color codes)."""
        import re

        return re.sub(r"\^\d", "", self.name).strip()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all player info fields.
        """
        return {
            "index": self.index,
            "name": self.name,
            "score": self.score,
            "duration": round(self.duration, 1),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with player info fields.

        Returns:
            PlayerInfo instance.
        """
        return cls(
            index=int(data.get("index", 0)),
            name=str(data.get("name", "")),
            score=int(data.get("score", 0)),
            duration=float(data.get("duration", 0.0)),
        )


@dataclass
class ServerRules:
    """Server rules from A2S_RULES response.

    Contains key-value pairs representing server configuration rules
    (e.g. ``mp_friendlyfire``, ``sv_password``).

    Attributes:
        rules: Dictionary of rule name-value pairs.

    Example::

        >>> rules = ServerRules(rules={"mp_friendlyfire": "1", "sv_maxspeed": "320"})
        >>> rules.get("mp_friendlyfire")
        '1'
        >>> rules.get("missing_key", "default")
        'default'
    """

    rules: dict[str, str] = field(default_factory=dict)

    def get(self, key: str, default: str = "") -> str:
        """Get a rule value by key.

        Args:
            key: Rule name.
            default: Value to return if key is not found.

        Returns:
            Rule value, or default if not found.
        """
        return self.rules.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get a rule value as an integer.

        Args:
            key: Rule name.
            default: Value to return if key is not found or conversion fails.

        Returns:
            Rule value as int, or default.
        """
        try:
            return int(self.rules.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a rule value as a float.

        Args:
            key: Rule name.
            default: Value to return if key is not found or conversion fails.

        Returns:
            Rule value as float, or default.
        """
        try:
            return float(self.rules.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a rule value as a boolean.

        Recognizes ``"1"``, ``"true"``, ``"yes"`` as True.

        Args:
            key: Rule name.
            default: Value to return if key is not found.

        Returns:
            Rule value as bool, or default.
        """
        val = self.rules.get(key, "").lower()
        if val in ("1", "true", "yes"):
            return True
        if val in ("0", "false", "no", ""):
            return False
        return default

    @property
    def rule_count(self) -> int:
        """Number of rules stored."""
        return len(self.rules)

    @property
    def is_empty(self) -> bool:
        """True if no rules are stored."""
        return len(self.rules) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with the ``rules`` key containing all rule pairs.
        """
        return {"rules": dict(self.rules)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with a ``rules`` key, or flat rule pairs.

        Returns:
            ServerRules instance.
        """
        raw = data.get("rules", data)
        if isinstance(raw, dict):
            return cls(rules={str(k): str(v) for k, v in raw.items()})
        return cls(rules={})

    def __getitem__(self, key: str) -> str:
        """Allow dictionary-style access: ``rules["key"]``."""
        return self.rules[key]

    def __contains__(self, key: str) -> bool:
        """Allow ``in`` operator: ``"key" in rules``."""
        return key in self.rules

    def __len__(self) -> int:
        """Number of rules."""
        return len(self.rules)


@dataclass(frozen=True, slots=True)
class QueryResult:
    """Combined result of a game server A2S query.

    Aggregates server info, player list, and rules from a single
    query session, along with timing and error information.

    Attributes:
        host: Server IP address or hostname.
        port: Server query port.
        server_info: Server metadata from A2S_INFO (None if query failed).
        players: Player list from A2S_PLAYER.
        rules: Server rules from A2S_RULES (None if not queried).
        rtt_ms: Round-trip time of the query in milliseconds.
        error: Error message if the query failed, None otherwise.
        query_time: Unix timestamp of the query.

    Example::

        >>> result = QueryResult(host="1.2.3.4", port=27015, rtt_ms=45.2)
        >>> result.is_success
        False  # server_info is None
    """

    host: str = ""
    port: int = 0
    server_info: ServerInfo | None = None
    players: list[PlayerInfo] = field(default_factory=list)
    rules: ServerRules | None = None
    rtt_ms: float = 0.0
    error: str | None = None
    query_time: float = 0.0

    def __post_init__(self) -> None:
        """Validate query result fields."""
        if self.port < 0 or self.port > 65535:
            raise ValueError(f"QueryResult.port must be 0-65535, got {self.port}")
        if self.rtt_ms < 0:
            raise ValueError(f"QueryResult.rtt_ms must be >= 0, got {self.rtt_ms}")

    @property
    def is_success(self) -> bool:
        """True if the query returned valid server info."""
        return self.error is None and self.server_info is not None

    @property
    def player_count(self) -> int:
        """Number of players in the query result."""
        return len(self.players)

    @property
    def target(self) -> str:
        """Target as ``host:port`` string."""
        return f"{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-compatible dictionary.

        Returns:
            Dictionary with all query result fields.
        """
        return {
            "host": self.host,
            "port": self.port,
            "server_info": self.server_info.to_dict() if self.server_info else None,
            "players": [p.to_dict() for p in self.players],
            "rules": self.rules.to_dict() if self.rules else None,
            "rtt_ms": self.rtt_ms,
            "error": self.error,
            "query_time": self.query_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Args:
            data: Dictionary with query result fields.

        Returns:
            QueryResult instance.
        """
        si_data = data.get("server_info")
        rules_data = data.get("rules")
        players_data = data.get("players", [])
        return cls(
            host=str(data.get("host", "")),
            port=int(data.get("port", 0)),
            server_info=ServerInfo.from_dict(si_data) if si_data else None,
            players=[PlayerInfo.from_dict(p) for p in players_data],
            rules=ServerRules.from_dict(rules_data) if rules_data else None,
            rtt_ms=float(data.get("rtt_ms", 0.0)),
            error=data.get("error"),
            query_time=float(data.get("query_time", 0.0)),
        )
