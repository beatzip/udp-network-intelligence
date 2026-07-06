"""Valve Source Query Protocol — A2S_INFO, A2S_PLAYER, A2S_RULES.

Implements the full Valve Source Query wire protocol used by
Source Engine, Source 2, and CS2 game servers.

Protocol Overview
-----------------

All A2S packets begin with a 4-byte header ``FF FF FF FF`` followed
by a single-byte type discriminator:

- ``0x54`` (``T``) — INFO request
- ``0x55`` (``U``) — PLAYER request
- ``0x56`` (``V``) — RULES request
- ``0x41`` (``A``) — Challenge response (server rejects first query)

Challenge Handshake
-------------------

Some servers require a two-step handshake:

1. Client sends request with challenge ``FFFFFFFF``.
2. Server responds with challenge response ``0x41`` + challenge number.
3. Client re-sends the request with the received challenge number.

A2S_INFO Response Formats
-------------------------

**Standard Source (``0x49``):**

``network_version``, ``name\0``, ``map\0``, ``folder\0``,
``game\0``, ``app_id(H)``, ``players(B)``, ``max_players(B)``,
``bots(B)``, ``server_type(B)``, ``platform(B)``,
``password_protected(B)``, ``vac_secured(B)``, ``version\0``

Optional trailing data controlled by EDF (Extra Data Flags):

- ``0x80``: GameID (Q, 8 bytes)
- ``0x40``: SteamID (Q, 8 bytes)
- ``0x20``: Keywords\0
- ``0x10``: Spectator: port(H) + name\0
- ``0x08``: Game port (H)
- ``0x04``: Source TV port (H)
- ``0x02``: Source TV name\0

**GoldSource (``0x6D``):**

``address\0``, ``name\0``, ``map\0``, ``game\0``,
``players(B)``, ``max_players(B)``, ``protocol(B)``,
``server_type(B)``, ``platform(B)``, ``password_protected(B)``,
``mod(B)``, ``secure(B)``,
``game_version\0`` (+ optional mod data if mod=1).

A2S_PLAYER Response
-------------------

``0x44`` + ``player_count(B)`` + for each player:
``index(B)``, ``name\0``, ``score(I)``, ``duration(f)``

A2S_RULES Response
------------------

``0x45`` + ``rule_count(H)`` + for each rule:
``key\0``, ``value\0``

Source 2 / CS2
--------------

CS2 (AppID 730) uses the same protocol with:

- Extended A2S_INFO with EDF flags for GameID, SteamID, Keywords.
- AppID = 730 (shared with CS:GO legacy).
- ``protocol`` byte may differ (usually 17).
- Additional ``server_type`` byte values for Source 2 matchmaking.

References
----------

- https://developer.valvesoftware.com/wiki/Server_browser_protocol
- https://developer.valvesoftware.com/wiki/A2S_INFO
- https://developer.valvesoftware.com/wiki/A2S_PLAYER
- https://developer.valvesoftware.com/wiki/A2S_RULES
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from uni.core.discovery.models import PlayerInfo, ServerInfo, ServerRules
from uni.protocol.base import (
    BaseProtocol,
    ProtocolValidationError,
)

# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------

HEADER_BYTES = b"\xff\xff\xff\xff"

# Request type bytes
REQ_INFO = 0x54  # 'T'
REQ_PLAYER = 0x55  # 'U'
REQ_RULES = 0x56  # 'V'

# Response type bytes
RESP_INFO = 0x49  # 'I' — Source Engine info
RESP_PLAYER = 0x44  # 'D'
RESP_RULES = 0x45  # 'E'
RESP_CHALLENGE = 0x41  # 'A'
RESP_GOLDSOURCE_INFO = 0x6D  # 'm'

# GoldSource server type bytes
GOLD_TYPE_DEDICATED = ord("d")
GOLD_TYPE_LOCAL = ord("l")
GOLD_TYPE_TV = ord("p")

# Platform bytes
PLATFORM_WINDOWS = ord("w")
PLATFORM_LINUX = ord("l")
PLATFORM_MAC = ord("m")

# EDF (Extra Data Flags) for extended A2S_INFO
EDF_GAMEID = 0x80
EDF_STEAMID = 0x40
EDF_KEYWORDS = 0x20
EDF_SPECTATOR = 0x10
EDF_GAME_PORT = 0x08
EDF_SOURCETV_PORT = 0x04
EDF_SOURCETV_NAME = 0x02

# Known AppIDs
KNOWN_APPIDS: dict[int, str] = {
    730: "Counter-Strike 2",
    740: "Counter-Strike: Global Offensive",
    440: "Team Fortress 2",
    550: "Left 4 Dead 2",
    570: "Dota 2",
    4000: "Garry's Mod",
    240: "Counter-Strike: Source",
    220: "Half-Life 2: Deathmatch",
    300: "Day of Defeat: Source",
    320: "Half-Life 2: Deathmatch",
    340: "Half-Life 2: Survivor",
    360: "Half-Life 2: Episode One",
    380: "Half-Life 2: Episode Two",
    420: "Half-Life 2: Lost Coast",
    500: "Alien Swarm",
    620: "Portal 2",
    630: "Alien Swarm: Reactive Drop",
    17700: "WarmupServer",
    27020: "CS2 Legacy",
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ServerType(Enum):
    """Server type byte from A2S_INFO response."""

    DEDICATED = "d"
    LOCAL = "l"
    TV = "p"
    SOURCE_TV = "p"

    @classmethod
    def from_byte(cls, b: int) -> ServerType:
        """Convert a raw byte to ServerType."""
        for member in cls:
            if member.value.encode() == bytes([b]):
                return member
        return cls.DEDICATED


class Platform(Enum):
    """Server platform byte from A2S_INFO response."""

    WINDOWS = "w"
    LINUX = "l"
    MAC = "m"

    @classmethod
    def from_byte(cls, b: int) -> Platform:
        """Convert a raw byte to Platform."""
        for member in cls:
            if member.value.encode() == bytes([b]):
                return member
        return cls.WINDOWS


# ---------------------------------------------------------------------------
# Protocol result types
# ---------------------------------------------------------------------------

class QueryStatus(Enum):
    """Status of an A2S query exchange."""

    SUCCESS = "success"
    CHALLENGE_REQUIRED = "challenge_required"
    CHALLENGE_RECEIVED = "challenge_received"
    TIMEOUT = "timeout"
    CONNECTION_REFUSED = "connection_refused"
    ERROR = "error"
    INVALID_RESPONSE = "invalid_response"
    UNSUPPORTED_ENGINE = "unsupported_engine"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value


# ---------------------------------------------------------------------------
# Wire packet structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class WireRequest:
    """An A2S request packet ready to send on the wire.

    Attributes:
        type_byte: Request type discriminator (``0x54``, ``0x55``, ``0x56``).
        challenge: Challenge number (``-1`` = no challenge).
        payload: Additional payload bytes.
    """

    type_byte: int
    challenge: int = -1
    payload: bytes = b""

    def encode(self) -> bytes:
        """Encode to wire bytes.

        Returns:
            Complete packet bytes including header.
        """
        parts = [HEADER_BYTES, bytes([self.type_byte])]
        if self.challenge >= 0:
            parts.append(struct.pack("<i", self.challenge))
        if self.payload:
            parts.append(self.payload)
        return b"".join(parts)


@dataclass(frozen=True, slots=True)
class WireResponse:
    """A parsed A2S response packet from the wire.

    Attributes:
        header: First 4 bytes (should be ``FF FF FF FF``).
        type_byte: Response type discriminator.
        payload: Remaining payload bytes.
        source_addr: Address the response came from.
        raw: Complete raw packet bytes.
        received_at: Monotonic timestamp.
    """

    header: bytes
    type_byte: int
    payload: bytes
    source_addr: tuple[str, int] = ("", 0)
    raw: bytes = b""
    received_at: float = 0.0

    @property
    def is_info(self) -> bool:
        """True if this is an A2S_INFO response."""
        return self.type_byte == RESP_INFO

    @property
    def is_player(self) -> bool:
        """True if this is an A2S_PLAYER response."""
        return self.type_byte == RESP_PLAYER

    @property
    def is_rules(self) -> bool:
        """True if this is an A2S_RULES response."""
        return self.type_byte == RESP_RULES

    @property
    def is_challenge(self) -> bool:
        """True if this is a challenge response."""
        return self.type_byte == RESP_CHALLENGE

    @property
    def is_goldsource_info(self) -> bool:
        """True if this is a GoldSource INFO response."""
        return self.type_byte == RESP_GOLDSOURCE_INFO

    @property
    def challenge_number(self) -> int:
        """Extract challenge number from challenge response payload."""
        if len(self.payload) >= 4:
            return struct.unpack("<i", self.payload[:4])[0]
        return -1


# ---------------------------------------------------------------------------
# String reader helper
# ---------------------------------------------------------------------------

class _ByteReader:
    """Sequential byte reader for parsing binary protocol data.

    Wraps a bytes object and maintains a read position, providing
    methods to read null-terminated strings, integers, and floats
    in little-endian byte order.
    """

    __slots__ = ("_data", "_pos")

    def __init__(self, data: bytes) -> None:
        """Initialize the reader.

        Args:
            data: Raw bytes to read from.
        """
        self._data = data
        self._pos = 0

    @property
    def remaining(self) -> int:
        """Bytes remaining to read."""
        return len(self._data) - self._pos

    @property
    def position(self) -> int:
        """Current read position."""
        return self._pos

    @property
    def is_exhausted(self) -> bool:
        """True if all bytes have been read."""
        return self._pos >= len(self._data)

    def read_bytes(self, count: int) -> bytes:
        """Read raw bytes.

        Args:
            count: Number of bytes to read.

        Returns:
            Read bytes.

        Raises:
            ProtocolValidationError: If not enough data.
        """
        if self._pos + count > len(self._data):
            raise ProtocolValidationError(
                f"Read overflow: need {count} bytes at pos {self._pos}, "
                f"have {self.remaining}"
            )
        result = self._data[self._pos : self._pos + count]
        self._pos += count
        return result

    def read_byte(self) -> int:
        """Read a single byte.

        Returns:
            Byte value (0-255).
        """
        return self.read_bytes(1)[0]

    def read_uint16(self) -> int:
        """Read a little-endian unsigned 16-bit integer.

        Returns:
            Integer value.
        """
        return struct.unpack("<H", self.read_bytes(2))[0]

    def read_int32(self) -> int:
        """Read a little-endian signed 32-bit integer.

        Returns:
            Integer value.
        """
        return struct.unpack("<i", self.read_bytes(4))[0]

    def read_uint32(self) -> int:
        """Read a little-endian unsigned 32-bit integer.

        Returns:
            Integer value.
        """
        return struct.unpack("<I", self.read_bytes(4))[0]

    def read_int64(self) -> int:
        """Read a little-endian signed 64-bit integer.

        Returns:
            Integer value.
        """
        return struct.unpack("<q", self.read_bytes(8))[0]

    def read_float32(self) -> float:
        """Read a little-endian 32-bit float.

        Returns:
            Float value.
        """
        return struct.unpack("<f", self.read_bytes(4))[0]

    def read_null_terminated_string(self) -> str:
        """Read a null-terminated string.

        Reads bytes until a ``0x00`` byte is encountered.

        Returns:
            Decoded string.
        """
        start = self._pos
        while self._pos < len(self._data) and self._data[self._pos] != 0:
            self._pos += 1
        result = self._data[start : self._pos]
        if self._pos < len(self._data):
            self._pos += 1  # skip null terminator
        return result.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# A2S_INFO Decoder
# ---------------------------------------------------------------------------

class A2SInfoDecoder:
    """Decoder for A2S_INFO response packets.

    Handles both standard Source Engine (``0x49``) and GoldSource
    (``0x6D``) response formats. Supports extended fields via
    EDF (Extra Data Flags) for Source 2 / CS2.

    Example::

        decoder = A2SInfoDecoder()
        server_info = decoder.decode(response_payload)
        print(server_info.name, server_info.map_name)
    """

    def decode(self, data: bytes) -> ServerInfo:
        """Decode A2S_INFO response payload into ServerInfo.

        Args:
            data: Response payload after the type byte.

        Returns:
            Parsed ServerInfo instance.

        Raises:
            ProtocolValidationError: If the payload is malformed.
        """
        reader = _ByteReader(data)

        try:
            type_byte = reader.read_byte()
        except ProtocolValidationError as exc:
            raise ProtocolValidationError(
                "A2S_INFO response too short for type byte"
            ) from exc

        if type_byte == RESP_INFO:
            return self._decode_source(reader)
        elif type_byte == RESP_GOLDSOURCE_INFO:
            return self._decode_goldsource(reader)
        else:
            raise ProtocolValidationError(
                f"Unexpected INFO response type: 0x{type_byte:02X}"
            )

    def _decode_source(self, r: _ByteReader) -> ServerInfo:
        """Decode a Source Engine A2S_INFO response.

        Args:
            r: Byte reader positioned after the type byte.

        Returns:
            Parsed ServerInfo.
        """
        network_version = r.read_byte()
        name = r.read_null_terminated_string()
        map_name = r.read_null_terminated_string()
        folder = r.read_null_terminated_string()
        game = r.read_null_terminated_string()
        app_id = r.read_uint16()
        player_count = r.read_byte()
        max_players = r.read_byte()
        bot_count = r.read_byte()
        server_type = r.read_byte()
        platform = r.read_byte()
        password_protected = r.read_byte()
        vac_secured = r.read_byte()
        version = r.read_null_terminated_string()

        # Optional extended data (EDF)
        edf = 0
        steam_id = 0
        game_id = 0
        keywords = ""
        spectator_port = 0
        spectator_name = ""
        game_port = 0
        sourcetv_port = 0
        sourcetv_name = ""

        if not r.is_exhausted:
            edf = r.read_byte()

            if edf & EDF_GAMEID:
                game_id = r.read_int64()
            if edf & EDF_STEAMID:
                steam_id = r.read_int64()
            if edf & EDF_KEYWORDS:
                keywords = r.read_null_terminated_string()
            if edf & EDF_SPECTATOR:
                spectator_port = r.read_uint16()
                spectator_name = r.read_null_terminated_string()
            if edf & EDF_GAME_PORT:
                game_port = r.read_uint16()
            if edf & EDF_SOURCETV_PORT:
                sourcetv_port = r.read_uint16()
            if edf & EDF_SOURCETV_NAME:
                sourcetv_name = r.read_null_terminated_string()

        return ServerInfo(
            name=name,
            map_name=map_name,
            game=game,
            app_id=app_id,
            player_count=player_count,
            max_players=max_players,
            bot_count=bot_count,
            version=version,
            protocol=network_version,
            folder=folder,
            steam_id=steam_id,
            keywords=keywords,
            game_port=game_port if game_port else 0,
        )

    def _decode_goldsource(self, r: _ByteReader) -> ServerInfo:
        """Decode a GoldSource engine A2S_INFO response.

        Args:
            r: Byte reader positioned after the type byte.

        Returns:
            Parsed ServerInfo.
        """
        address = r.read_null_terminated_string()
        name = r.read_null_terminated_string()
        map_name = r.read_null_terminated_string()
        game = r.read_null_terminated_string()
        player_count = r.read_byte()
        max_players = r.read_byte()
        protocol = r.read_byte()
        server_type = r.read_byte()
        platform = r.read_byte()
        password_protected = r.read_byte()
        mod = r.read_byte()
        secure = r.read_byte()
        game_version = r.read_null_terminated_string()

        return ServerInfo(
            name=name,
            map_name=map_name,
            game=game,
            app_id=0,  # GoldSource doesn't reliably report app_id
            player_count=player_count,
            max_players=max_players,
            bot_count=0,
            version=game_version,
            protocol=protocol,
            folder=game,
            steam_id=0,
            keywords="",
            game_port=0,
        )


# ---------------------------------------------------------------------------
# A2S_PLAYER Decoder
# ---------------------------------------------------------------------------

class A2SPlayerDecoder:
    """Decoder for A2S_PLAYER response packets.

    Parses the ``0x44`` response containing the server's player list.

    Example::

        decoder = A2SPlayerDecoder()
        players = decoder.decode(response_payload)
        for p in players:
            print(f"{p.name}: {p.score}")
    """

    def decode(self, data: bytes) -> list[PlayerInfo]:
        """Decode A2S_PLAYER response payload.

        Args:
            data: Response payload after the type byte.

        Returns:
            List of PlayerInfo instances.

        Raises:
            ProtocolValidationError: If the payload is malformed.
        """
        reader = _ByteReader(data)

        try:
            type_byte = reader.read_byte()
        except ProtocolValidationError as exc:
            raise ProtocolValidationError(
                "A2S_PLAYER response too short"
            ) from exc

        if type_byte != RESP_PLAYER:
            raise ProtocolValidationError(
                f"Expected A2S_PLAYER (0x44), got 0x{type_byte:02X}"
            )

        player_count = reader.read_byte()
        players: list[PlayerInfo] = []

        for _ in range(player_count):
            index = reader.read_byte()
            name = reader.read_null_terminated_string()
            score = reader.read_int32()
            duration = reader.read_float32()
            players.append(
                PlayerInfo(index=index, name=name, score=score, duration=duration)
            )

        return players


# ---------------------------------------------------------------------------
# A2S_RULES Decoder
# ---------------------------------------------------------------------------

class A2SRulesDecoder:
    """Decoder for A2S_RULES response packets.

    Parses the ``0x45`` response containing server configuration
    key-value pairs.

    Example::

        decoder = A2SRulesDecoder()
        rules = decoder.decode(response_payload)
        print(rules.get("mp_friendlyfire"))
    """

    def decode(self, data: bytes) -> ServerRules:
        """Decode A2S_RULES response payload.

        Args:
            data: Response payload after the type byte.

        Returns:
            ServerRules with all parsed key-value pairs.

        Raises:
            ProtocolValidationError: If the payload is malformed.
        """
        reader = _ByteReader(data)

        try:
            type_byte = reader.read_byte()
        except ProtocolValidationError as exc:
            raise ProtocolValidationError(
                "A2S_RULES response too short"
            ) from exc

        if type_byte != RESP_RULES:
            raise ProtocolValidationError(
                f"Expected A2S_RULES (0x45), got 0x{type_byte:02X}"
            )

        rule_count = reader.read_uint16()
        rules: dict[str, str] = {}

        for _ in range(rule_count):
            key = reader.read_null_terminated_string()
            value = reader.read_null_terminated_string()
            rules[key] = value

        return ServerRules(rules=rules)


# ---------------------------------------------------------------------------
# A2S Query Protocol (full encoder + decoder)
# ---------------------------------------------------------------------------

class A2SQueryProtocol(BaseProtocol):
    """Full A2S (Source Query) protocol implementation.

    Encodes request packets and decodes response packets for
    A2S_INFO, A2S_PLAYER, and A2S_RULES queries. Handles the
    challenge-response handshake automatically.

    Supports:
    - Source Engine (standard ``0x49`` responses)
    - GoldSource Engine (``0x6D`` responses)
    - Source 2 / CS2 (extended EDF fields)
    - Challenge handshake (``0x41`` responses)

    Example::

        protocol = A2SQueryProtocol()

        # Build INFO request
        request = protocol.encode_info_request()
        raw = request.encode()  # bytes to send

        # Decode response
        server_info = protocol.decode_info_response(response_bytes)

        # Challenge flow
        if protocol.is_challenge_response(response_bytes):
            challenge = protocol.extract_challenge(response_bytes)
            request = protocol.encode_info_request(challenge=challenge)
    """

    HEADER = HEADER_BYTES
    TIMEOUT = 5.0

    def __init__(self) -> None:
        """Initialize the protocol with all decoders."""
        self._info_decoder = A2SInfoDecoder()
        self._player_decoder = A2SPlayerDecoder()
        self._rules_decoder = A2SRulesDecoder()

    # ------------------------------------------------------------------
    # Encode methods
    # ------------------------------------------------------------------

    def encode_request(self, **kwargs: Any) -> WireRequest:
        """Encode a generic A2S request.

        Args:
            **kwargs: Forwarded to ``encode_info_request``.

        Returns:
            WireRequest ready for sending.
        """
        return self.encode_info_request(**kwargs)

    def encode_info_request(self, challenge: int = -1) -> WireRequest:
        """Build an A2S_INFO request packet.

        Args:
            challenge: Challenge number. Use ``-1`` for the initial
                unchallenged request, or a positive value from a
                previous challenge response.

        Returns:
            WireRequest with type ``0x54``.
        """
        return WireRequest(type_byte=REQ_INFO, challenge=challenge)

    def encode_player_request(self, challenge: int = -1) -> WireRequest:
        """Build an A2S_PLAYER request packet.

        Args:
            challenge: Challenge number (``-1`` for initial request).

        Returns:
            WireRequest with type ``0x55``.
        """
        return WireRequest(type_byte=REQ_PLAYER, challenge=challenge)

    def encode_rules_request(self, challenge: int = -1) -> WireRequest:
        """Build an A2S_RULES request packet.

        Args:
            challenge: Challenge number (``-1`` for initial request).

        Returns:
            WireRequest with type ``0x56``.
        """
        return WireRequest(type_byte=REQ_RULES, challenge=challenge)

    # ------------------------------------------------------------------
    # Decode methods
    # ------------------------------------------------------------------

    def decode_response(self, data: bytes) -> WireResponse:
        """Parse any A2S response into a WireResponse.

        Args:
            data: Raw response bytes.

        Returns:
            Parsed WireResponse.

        Raises:
            ProtocolValidationError: If the packet header is wrong.
        """
        if len(data) < 5:
            raise ProtocolValidationError(
                f"A2S response too short: {len(data)} bytes"
            )
        if data[:4] != HEADER_BYTES:
            raise ProtocolValidationError(
                f"Invalid A2S header: {data[:4]!r}"
            )

        return WireResponse(
            header=data[:4],
            type_byte=data[4],
            payload=data[5:],
            raw=data,
            received_at=time.monotonic(),
        )

    def decode_info_response(self, data: bytes) -> ServerInfo:
        """Decode an A2S_INFO response.

        Args:
            data: Raw response bytes (including ``FF FF FF FF`` header).

        Returns:
            Parsed ServerInfo.

        Raises:
            ProtocolValidationError: If the response is malformed.
        """
        wr = self.decode_response(data)
        full = bytes([wr.type_byte]) + wr.payload
        return self._info_decoder.decode(full)

    def decode_player_response(self, data: bytes) -> list[PlayerInfo]:
        """Decode an A2S_PLAYER response.

        Args:
            data: Raw response bytes.

        Returns:
            List of PlayerInfo instances.

        Raises:
            ProtocolValidationError: If the response is malformed.
        """
        wr = self.decode_response(data)
        full = bytes([wr.type_byte]) + wr.payload
        return self._player_decoder.decode(full)

    def decode_rules_response(self, data: bytes) -> ServerRules:
        """Decode an A2S_RULES response.

        Args:
            data: Raw response bytes.

        Returns:
            ServerRules with parsed key-value pairs.

        Raises:
            ProtocolValidationError: If the response is malformed.
        """
        wr = self.decode_response(data)
        full = bytes([wr.type_byte]) + wr.payload
        return self._rules_decoder.decode(full)

    # ------------------------------------------------------------------
    # Query type detection
    # ------------------------------------------------------------------

    def is_challenge_response(self, data: bytes) -> bool:
        """Check if a response is a challenge request (``0x41``).

        Args:
            data: Raw response bytes.

        Returns:
            True if the server is requesting a challenge.
        """
        if len(data) < 5:
            return False
        return data[:4] == HEADER_BYTES and data[4] == RESP_CHALLENGE

    def extract_challenge(self, data: bytes) -> int:
        """Extract the challenge number from a challenge response.

        Args:
            data: Raw challenge response bytes.

        Returns:
            Challenge number, or ``-1`` on failure.
        """
        if not self.is_challenge_response(data):
            return -1
        if len(data) >= 9:
            return struct.unpack("<i", data[5:9])[0]
        return -1

    def get_response_type_name(self, data: bytes) -> str:
        """Get a human-readable name for the response type.

        Args:
            data: Raw response bytes.

        Returns:
            Type name string (e.g. ``"A2S_INFO"``).
        """
        if len(data) < 5:
            return "UNKNOWN"
        if data[:4] != HEADER_BYTES:
            return "INVALID"
        type_map = {
            0x49: "A2S_INFO",
            0x44: "A2S_PLAYER",
            0x45: "A2S_RULES",
            0x41: "CHALLENGE",
            0x6D: "GOLDSOURCE_INFO",
        }
        return type_map.get(data[4], f"UNKNOWN_0x{data[4]:02X}")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, data: bytes) -> bool:
        """Validate an A2S packet.

        Args:
            data: Raw packet bytes.

        Returns:
            True if the packet has a valid A2S header and type byte.
        """
        if len(data) < 5:
            return False
        if data[:4] != HEADER_BYTES:
            return False
        valid_types = {
            RESP_INFO,
            RESP_PLAYER,
            RESP_RULES,
            RESP_CHALLENGE,
            RESP_GOLDSOURCE_INFO,
        }
        return data[4] in valid_types

    def detect_engine(self, info: ServerInfo) -> str:
        """Detect the server engine from ServerInfo fields.

        Uses app_id, protocol version, and folder name to determine
        whether the server runs Source Engine, Source 2, GoldSource,
        or CS2.

        Args:
            info: Parsed ServerInfo from A2S_INFO.

        Returns:
            Engine name string.
        """
        if info.app_id == 730:
            if info.version and info.version.startswith("csgo"):
                return "CS:GO Legacy"
            return "Counter-Strike 2 (Source 2)"
        if info.app_id == 740:
            return "CS:GO"
        if info.app_id in (440, 550, 570):
            known = KNOWN_APPIDS.get(info.app_id, "Source Engine")
            return known
        if info.protocol == 47:
            return "Source Engine"
        if info.app_id == 0 and info.protocol == 15:
            return "GoldSource"
        known = KNOWN_APPIDS.get(info.app_id)
        if known:
            return f"Source Engine ({known})"
        if info.folder in ("csgo", "cs2"):
            return "Source 2"
        return "Unknown Engine"
