"""Tests for uni.app.constants module."""

from __future__ import annotations

import pytest

from uni.app.constants import (
    A2S_HEADER_SIZE,
    DEFAULT_PROBE_COUNT,
    DEFAULT_SOURCE_PORT,
    DEFAULT_TTL,
    ICMPType,
    NetworkTarget,
    ProbeDefaults,
    ProbeProtocol,
    QualityGrade,
    ServerType,
)


class TestEnums:
    """Tests for enum definitions."""

    def test_probe_protocol_values(self) -> None:
        assert ProbeProtocol.UDP.value == "udp"
        assert ProbeProtocol.TCP.value == "tcp"
        assert ProbeProtocol.ICMP.value == "icmp"

    def test_server_type_values(self) -> None:
        assert ServerType.CS2.value == "cs2"
        assert ServerType.CUSTOM.value == "custom"

    def test_quality_grade_values(self) -> None:
        assert QualityGrade.A_PLUS.value == "A+"
        assert QualityGrade.F.value == "F"

    def test_icmp_type_values(self) -> None:
        assert ICMPType.ECHO_REPLY.value == 0
        assert ICMPType.TIME_EXCEEDED.value == 11


class TestConstants:
    """Tests for constant values."""

    def test_default_source_port(self) -> None:
        assert DEFAULT_SOURCE_PORT == 27015

    def test_a2s_header_size(self) -> None:
        assert A2S_HEADER_SIZE == 4

    def test_default_ttl(self) -> None:
        assert DEFAULT_TTL == 64

    def test_default_probe_count(self) -> None:
        assert DEFAULT_PROBE_COUNT == 50


class TestNetworkTarget:
    """Tests for NetworkTarget dataclass."""

    def test_str(self) -> None:
        target = NetworkTarget(host="1.2.3.4", port=27015)
        assert str(target) == "1.2.3.4:27015"

    def test_frozen(self) -> None:
        target = NetworkTarget(host="1.2.3.4", port=27015)
        with pytest.raises(AttributeError):
            target.host = "5.6.7.8"  # type: ignore[misc]


class TestProbeDefaults:
    """Tests for ProbeDefaults dataclass."""

    def test_defaults(self) -> None:
        defaults = ProbeDefaults()
        assert defaults.count == 50
        assert defaults.interval == 1.0
        assert defaults.protocol == ProbeProtocol.UDP

    def test_custom(self) -> None:
        defaults = ProbeDefaults(count=100, interval=0.5)
        assert defaults.count == 100
        assert defaults.interval == 0.5
