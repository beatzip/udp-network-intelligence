"""Tests for the Valve Source Query Protocol implementation."""

from __future__ import annotations

import struct

import pytest

from uni.core.discovery.models import ServerInfo
from uni.protocol.a2s_protocol import (
    EDF_GAME_PORT,
    EDF_GAMEID,
    EDF_KEYWORDS,
    EDF_STEAMID,
    HEADER_BYTES,
    KNOWN_APPIDS,
    REQ_INFO,
    REQ_PLAYER,
    REQ_RULES,
    RESP_CHALLENGE,
    RESP_GOLDSOURCE_INFO,
    RESP_INFO,
    RESP_PLAYER,
    RESP_RULES,
    A2SInfoDecoder,
    A2SPlayerDecoder,
    A2SQueryProtocol,
    A2SRulesDecoder,
    WireRequest,
    WireResponse,
    _ByteReader,
)
from uni.protocol.base import (
    ProtocolValidationError,
)
from uni.protocol.source_query import (
    QueryConfig,
    SourceQuery,
)

# ---------------------------------------------------------------------------
# _ByteReader
# ---------------------------------------------------------------------------


class TestByteReader:
    """Tests for _ByteReader."""

    def test_read_byte(self) -> None:
        r = _ByteReader(b"\x42")
        assert r.read_byte() == 0x42

    def test_read_uint16(self) -> None:
        r = _ByteReader(struct.pack("<H", 27015))
        assert r.read_uint16() == 27015

    def test_read_int32(self) -> None:
        r = _ByteReader(struct.pack("<i", -1))
        assert r.read_int32() == -1

    def test_read_uint32(self) -> None:
        r = _ByteReader(struct.pack("<I", 0xDEADBEEF))
        assert r.read_uint32() == 0xDEADBEEF

    def test_read_int64(self) -> None:
        r = _ByteReader(struct.pack("<q", 123456789012345))
        assert r.read_int64() == 123456789012345

    def test_read_float32(self) -> None:
        r = _ByteReader(struct.pack("<f", 3.14))
        val = r.read_float32()
        assert abs(val - 3.14) < 0.01

    def test_read_null_terminated_string(self) -> None:
        r = _ByteReader(b"hello\x00")
        assert r.read_null_terminated_string() == "hello"

    def test_read_string_with_padding(self) -> None:
        r = _ByteReader(b"test\x00rest")
        assert r.read_null_terminated_string() == "test"
        assert r.read_bytes(4) == b"rest"

    def test_read_overflow_raises(self) -> None:
        r = _ByteReader(b"\x01")
        with pytest.raises(ProtocolValidationError, match="overflow"):
            r.read_bytes(5)

    def test_position_tracking(self) -> None:
        r = _ByteReader(b"\x01\x02\x03")
        assert r.position == 0
        r.read_byte()
        assert r.position == 1
        r.read_uint16()
        assert r.position == 3
        assert r.is_exhausted

    def test_remaining(self) -> None:
        r = _ByteReader(b"\x01\x02\x03")
        assert r.remaining == 3
        r.read_byte()
        assert r.remaining == 2


# ---------------------------------------------------------------------------
# WireRequest
# ---------------------------------------------------------------------------


class TestWireRequest:
    """Tests for WireRequest."""

    def test_encode_no_challenge(self) -> None:
        req = WireRequest(type_byte=0x54)
        data = req.encode()
        assert data[:4] == HEADER_BYTES
        assert data[4] == 0x54

    def test_encode_with_challenge(self) -> None:
        req = WireRequest(type_byte=0x54, challenge=42)
        data = req.encode()
        assert data[:4] == HEADER_BYTES
        assert data[4] == 0x54
        challenge_val = struct.unpack("<i", data[5:9])[0]
        assert challenge_val == 42

    def test_encode_with_payload(self) -> None:
        req = WireRequest(type_byte=0x55, payload=b"\x01\x02")
        data = req.encode()
        assert data[5:7] == b"\x01\x02"


# ---------------------------------------------------------------------------
# WireResponse
# ---------------------------------------------------------------------------


class TestWireResponse:
    """Tests for WireResponse."""

    def test_is_info(self) -> None:
        wr = WireResponse(header=HEADER_BYTES, type_byte=0x49, payload=b"")
        assert wr.is_info is True

    def test_is_challenge(self) -> None:
        wr = WireResponse(header=HEADER_BYTES, type_byte=0x41, payload=b"")
        assert wr.is_challenge is True

    def test_challenge_number(self) -> None:
        payload = struct.pack("<i", 12345)
        wr = WireResponse(header=HEADER_BYTES, type_byte=0x41, payload=payload)
        assert wr.challenge_number == 12345


# ---------------------------------------------------------------------------
# A2SInfoDecoder — Source Engine
# ---------------------------------------------------------------------------


class TestA2SInfoDecoderSource:
    """Tests for A2SInfoDecoder with Source Engine responses."""

    def _build_source_info_response(
        self,
        name: str = "Test Server",
        map_name: str = "de_dust2",
        folder: str = "csgo",
        game: str = "Counter-Strike",
        app_id: int = 730,
        players: int = 5,
        max_players: int = 10,
        bots: int = 0,
        version: str = "1.0.0.0",
        edf: int = 0,
    ) -> bytes:
        """Build a Source Engine A2S_INFO response."""
        parts = [
            bytes([RESP_INFO]),
            bytes([47]),  # network version
            name.encode("utf-8") + b"\x00",
            map_name.encode("utf-8") + b"\x00",
            folder.encode("utf-8") + b"\x00",
            game.encode("utf-8") + b"\x00",
            struct.pack("<H", app_id),
            bytes([players]),
            bytes([max_players]),
            bytes([bots]),
            bytes([ord("d")]),  # dedicated
            bytes([ord("w")]),  # windows
            bytes([0]),  # not password protected
            bytes([1]),  # vac secured
            version.encode("utf-8") + b"\x00",
        ]
        if edf:
            parts.append(bytes([edf]))
        return b"".join(parts)

    def test_basic_info(self) -> None:
        data = self._build_source_info_response()
        decoder = A2SInfoDecoder()
        info = decoder.decode(data)

        assert info.name == "Test Server"
        assert info.map_name == "de_dust2"
        assert info.folder == "csgo"
        assert info.game == "Counter-Strike"
        assert info.app_id == 730
        assert info.player_count == 5
        assert info.max_players == 10
        assert info.bot_count == 0
        assert info.version == "1.0.0.0"

    def test_extended_steam_id(self) -> None:
        steam_id = 12345678901234567
        data = self._build_source_info_response(edf=EDF_STEAMID)
        # Append steam ID after EDF
        data += struct.pack("<q", steam_id)

        decoder = A2SInfoDecoder()
        info = decoder.decode(data)
        assert info.steam_id == steam_id

    def test_extended_keywords(self) -> None:
        data = self._build_source_info_response(edf=EDF_KEYWORDS)
        data += b"dm,fun,24/7\x00"

        decoder = A2SInfoDecoder()
        info = decoder.decode(data)
        assert info.keywords == "dm,fun,24/7"

    def test_extended_game_id(self) -> None:
        game_id = 730
        data = self._build_source_info_response(edf=EDF_GAMEID)
        data += struct.pack("<q", game_id)

        decoder = A2SInfoDecoder()
        info = decoder.decode(data)
        assert info.app_id == 730

    def test_extended_game_port(self) -> None:
        data = self._build_source_info_response(edf=EDF_GAME_PORT)
        data += struct.pack("<H", 27015)

        decoder = A2SInfoDecoder()
        info = decoder.decode(data)
        assert info.game_port == 27015

    def test_multiple_edf_flags(self) -> None:
        edf = EDF_STEAMID | EDF_KEYWORDS | EDF_GAME_PORT
        data = self._build_source_info_response(edf=edf)
        data += struct.pack("<q", 999)  # steam id
        data += b"competitive\x00"  # keywords
        data += struct.pack("<H", 27015)  # game port

        decoder = A2SInfoDecoder()
        info = decoder.decode(data)
        assert info.steam_id == 999
        assert info.keywords == "competitive"
        assert info.game_port == 27015

    def test_invalid_type_byte(self) -> None:
        data = HEADER_BYTES + bytes([0xFF])
        decoder = A2SInfoDecoder()
        with pytest.raises(ProtocolValidationError, match="Unexpected"):
            decoder.decode(data)

    def test_empty_payload(self) -> None:
        decoder = A2SInfoDecoder()
        with pytest.raises(ProtocolValidationError, match="too short"):
            decoder.decode(b"")


# ---------------------------------------------------------------------------
# A2SInfoDecoder — GoldSource
# ---------------------------------------------------------------------------


class TestA2SInfoDecoderGoldSource:
    """Tests for A2SInfoDecoder with GoldSource responses."""

    def _build_goldsource_response(
        self,
        name: str = "GoldServer",
        map_name: str = "de_test",
    ) -> bytes:
        parts = [
            bytes([RESP_GOLDSOURCE_INFO]),
            b"10.0.0.1\x00",
            name.encode("utf-8") + b"\x00",
            map_name.encode("utf-8") + b"\x00",
            b"valve\x00",
            bytes([8]),  # players
            bytes([16]),  # max
            bytes([47]),  # protocol
            bytes([ord("d")]),  # type
            bytes([ord("w")]),  # platform
            bytes([0]),  # password
            bytes([1]),  # mod
            bytes([0]),  # secure
            b"1.0.0\x00",
        ]
        return b"".join(parts)

    def test_goldsource_info(self) -> None:
        data = self._build_goldsource_response()
        decoder = A2SInfoDecoder()
        info = decoder.decode(data)

        assert info.name == "GoldServer"
        assert info.map_name == "de_test"
        assert info.game == "valve"
        assert info.player_count == 8
        assert info.max_players == 16
        assert info.protocol == 47


# ---------------------------------------------------------------------------
# A2SPlayerDecoder
# ---------------------------------------------------------------------------


class TestA2SPlayerDecoder:
    """Tests for A2SPlayerDecoder."""

    def _build_player_response(self, count: int = 2) -> bytes:
        parts = [
            bytes([RESP_PLAYER]),
            bytes([count]),
        ]
        for i in range(count):
            name = f"Player{i}"
            parts.append(bytes([i]))  # index
            parts.append(name.encode("utf-8") + b"\x00")
            parts.append(struct.pack("<i", 100 - i * 10))  # score
            parts.append(struct.pack("<f", 600.0 + i * 60.0))  # duration
        return b"".join(parts)

    def test_basic_player_list(self) -> None:
        data = self._build_player_response(2)
        decoder = A2SPlayerDecoder()
        players = decoder.decode(data)

        assert len(players) == 2
        assert players[0].name == "Player0"
        assert players[0].score == 100
        assert players[0].duration == pytest.approx(600.0)
        assert players[1].name == "Player1"
        assert players[1].score == 90

    def test_empty_player_list(self) -> None:
        data = bytes([RESP_PLAYER, 0])
        decoder = A2SPlayerDecoder()
        players = decoder.decode(data)
        assert len(players) == 0

    def test_wrong_type_byte(self) -> None:
        data = bytes([0xFF, 0])
        decoder = A2SPlayerDecoder()
        with pytest.raises(ProtocolValidationError, match="Expected"):
            decoder.decode(data)


# ---------------------------------------------------------------------------
# A2SRulesDecoder
# ---------------------------------------------------------------------------


class TestA2SRulesDecoder:
    """Tests for A2SRulesDecoder."""

    def _build_rules_response(self, rules: dict[str, str]) -> bytes:
        parts = [
            bytes([RESP_RULES]),
            struct.pack("<H", len(rules)),
        ]
        for key, val in rules.items():
            parts.append(key.encode("utf-8") + b"\x00")
            parts.append(val.encode("utf-8") + b"\x00")
        return b"".join(parts)

    def test_basic_rules(self) -> None:
        data = self._build_rules_response(
            {
                "mp_friendlyfire": "1",
                "sv_gravity": "800",
            }
        )
        decoder = A2SRulesDecoder()
        rules = decoder.decode(data)

        assert rules.get("mp_friendlyfire") == "1"
        assert rules.get("sv_gravity") == "800"
        assert rules.rule_count == 2

    def test_empty_rules(self) -> None:
        data = bytes([RESP_RULES]) + struct.pack("<H", 0)
        decoder = A2SRulesDecoder()
        rules = decoder.decode(data)
        assert rules.is_empty


# ---------------------------------------------------------------------------
# A2SQueryProtocol
# ---------------------------------------------------------------------------


class TestA2SQueryProtocol:
    """Tests for A2SQueryProtocol."""

    def test_encode_info_request(self) -> None:
        proto = A2SQueryProtocol()
        req = proto.encode_info_request()
        data = req.encode()
        assert data[:4] == HEADER_BYTES
        assert data[4] == REQ_INFO

    def test_encode_info_request_with_challenge(self) -> None:
        proto = A2SQueryProtocol()
        req = proto.encode_info_request(challenge=42)
        data = req.encode()
        challenge_val = struct.unpack("<i", data[5:9])[0]
        assert challenge_val == 42

    def test_encode_player_request(self) -> None:
        proto = A2SQueryProtocol()
        req = proto.encode_player_request()
        assert req.type_byte == REQ_PLAYER

    def test_encode_rules_request(self) -> None:
        proto = A2SQueryProtocol()
        req = proto.encode_rules_request()
        assert req.type_byte == REQ_RULES

    def test_decode_response(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_INFO]) + b"\x00"
        wr = proto.decode_response(data)
        assert wr.is_info
        assert wr.payload == b"\x00"

    def test_decode_short_response_raises(self) -> None:
        proto = A2SQueryProtocol()
        with pytest.raises(ProtocolValidationError, match="too short"):
            proto.decode_response(b"\xff\xff")

    def test_decode_bad_header_raises(self) -> None:
        proto = A2SQueryProtocol()
        with pytest.raises(ProtocolValidationError, match="Invalid"):
            proto.decode_response(b"\x00\x00\x00\x00\x49")

    def test_is_challenge_response(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_CHALLENGE]) + struct.pack("<i", 123)
        assert proto.is_challenge_response(data) is True

    def test_extract_challenge(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_CHALLENGE]) + struct.pack("<i", 42)
        assert proto.extract_challenge(data) == 42

    def test_extract_challenge_from_wrong_type(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_INFO])
        assert proto.extract_challenge(data) == -1

    def test_get_response_type_name(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_INFO])
        assert proto.get_response_type_name(data) == "A2S_INFO"

    def test_validate_valid(self) -> None:
        proto = A2SQueryProtocol()
        data = HEADER_BYTES + bytes([RESP_INFO])
        assert proto.validate(data) is True

    def test_validate_invalid_header(self) -> None:
        proto = A2SQueryProtocol()
        assert proto.validate(b"\x00\x00\x00\x00\x49") is False

    def test_validate_invalid_type(self) -> None:
        proto = A2SQueryProtocol()
        assert proto.validate(HEADER_BYTES + bytes([0xFF])) is False

    def test_validate_short(self) -> None:
        proto = A2SQueryProtocol()
        assert proto.validate(b"\xff") is False

    def test_detect_engine_cs2(self) -> None:
        proto = A2SQueryProtocol()
        info = ServerInfo(app_id=730, version="1.39.3.0", folder="cs2")
        engine = proto.detect_engine(info)
        assert "Counter-Strike 2" in engine

    def test_detect_engine_csgo(self) -> None:
        proto = A2SQueryProtocol()
        info = ServerInfo(app_id=730, version="csgo_demo")
        engine = proto.detect_engine(info)
        assert "CS:GO Legacy" in engine

    def test_detect_engine_tf2(self) -> None:
        proto = A2SQueryProtocol()
        info = ServerInfo(app_id=440)
        engine = proto.detect_engine(info)
        assert "Team Fortress 2" in engine

    def test_detect_engine_goldsource(self) -> None:
        proto = A2SQueryProtocol()
        info = ServerInfo(app_id=0, protocol=15)
        engine = proto.detect_engine(info)
        assert "GoldSource" in engine

    def test_detect_engine_known(self) -> None:
        proto = A2SQueryProtocol()
        info = ServerInfo(app_id=570)
        engine = proto.detect_engine(info)
        assert "Dota" in engine

    def test_full_info_roundtrip(self) -> None:
        """Encode request, build response, decode — full cycle."""
        proto = A2SQueryProtocol()

        # Encode request
        req = proto.encode_info_request()
        assert req.type_byte == REQ_INFO

        # Build a synthetic INFO response
        response_data = (
            HEADER_BYTES
            + bytes([RESP_INFO])
            + bytes([47])
            + b"Test\x00"
            + b"de_dust2\x00"
            + b"csgo\x00"
            + b"Counter-Strike\x00"
            + struct.pack("<H", 730)
            + bytes([5, 10, 0, ord("d"), ord("w"), 0, 1])
            + b"1.0.0.0\x00"
        )

        # Decode
        info = proto.decode_info_response(response_data)
        assert info.name == "Test"
        assert info.app_id == 730
        assert info.player_count == 5


# ---------------------------------------------------------------------------
# SourceQuery
# ---------------------------------------------------------------------------


class TestSourceQuery:
    """Tests for SourceQuery."""

    def test_config_defaults(self) -> None:
        cfg = QueryConfig()
        assert cfg.timeout == 5.0
        assert cfg.max_retries == 2
        assert cfg.retry_delay == 0.5

    def test_protocol_initialization(self) -> None:
        query = SourceQuery()
        assert isinstance(query.protocol, A2SQueryProtocol)
        assert query.config.timeout == 5.0

    def test_custom_config(self) -> None:
        cfg = QueryConfig(timeout=10.0, max_retries=5)
        query = SourceQuery(cfg)
        assert query.config.timeout == 10.0
        assert query.config.max_retries == 5

    @pytest.mark.asyncio
    async def test_query_info_timeout(self) -> None:
        """Test that query_info returns error on unreachable host."""
        query = SourceQuery(QueryConfig(timeout=0.1, max_retries=0))
        result = await query.query_info("192.0.2.1", 9999)
        assert not result.is_success
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_query_all_timeout(self) -> None:
        """Test that query_all returns error on unreachable host."""
        query = SourceQuery(QueryConfig(timeout=0.1, max_retries=0))
        result = await query.query_all("192.0.2.1", 9999)
        assert not result.is_success


# ---------------------------------------------------------------------------
# Protocol constants
# ---------------------------------------------------------------------------


class TestProtocolConstants:
    """Tests for protocol constants."""

    def test_header_bytes(self) -> None:
        assert HEADER_BYTES == b"\xff\xff\xff\xff"

    def test_request_types(self) -> None:
        assert REQ_INFO == 0x54
        assert REQ_PLAYER == 0x55
        assert REQ_RULES == 0x56

    def test_response_types(self) -> None:
        assert RESP_INFO == 0x49
        assert RESP_PLAYER == 0x44
        assert RESP_RULES == 0x45
        assert RESP_CHALLENGE == 0x41
        assert RESP_GOLDSOURCE_INFO == 0x6D

    def test_edf_flags(self) -> None:
        assert EDF_GAMEID == 0x80
        assert EDF_STEAMID == 0x40
        assert EDF_KEYWORDS == 0x20
        assert EDF_GAME_PORT == 0x08

    def test_known_appids_contain_cs2(self) -> None:
        assert 730 in KNOWN_APPIDS
        assert "Counter-Strike 2" in KNOWN_APPIDS[730]
