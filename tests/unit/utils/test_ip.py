"""Tests for uni.utils.ip module."""

from __future__ import annotations

import pytest

from uni.utils.ip import (
    InvalidTargetError,
    is_private_ip,
    is_valid_ip,
    is_valid_ipv4,
    is_valid_port,
    normalize_host,
    parse_target,
)


class TestParseTarget:
    """Tests for parse_target()."""

    def test_ipv4_with_port(self) -> None:
        host, port = parse_target("192.168.1.1:27015")
        assert host == "192.168.1.1"
        assert port == 27015

    def test_hostname_with_port(self) -> None:
        host, port = parse_target("example.com:8080")
        assert host == "example.com"
        assert port == 8080

    def test_loopback(self) -> None:
        host, port = parse_target("127.0.0.1:27015")
        assert host == "127.0.0.1"
        assert port == 27015

    def test_invalid_no_port(self) -> None:
        with pytest.raises(InvalidTargetError):
            parse_target("192.168.1.1")

    def test_invalid_port_zero(self) -> None:
        with pytest.raises(InvalidTargetError):
            parse_target("192.168.1.1:0")

    def test_invalid_port_too_high(self) -> None:
        with pytest.raises(InvalidTargetError):
            parse_target("192.168.1.1:70000")

    def test_invalid_empty(self) -> None:
        with pytest.raises(InvalidTargetError):
            parse_target("")

    def test_whitespace_handling(self) -> None:
        host, port = parse_target("  192.168.1.1:27015  ")
        assert host == "192.168.1.1"
        assert port == 27015


class TestIsValidIp:
    """Tests for is_valid_ip()."""

    def test_valid_ipv4(self) -> None:
        assert is_valid_ip("192.168.1.1") is True

    def test_valid_ipv6(self) -> None:
        assert is_valid_ip("::1") is True

    def test_invalid(self) -> None:
        assert is_valid_ip("not-an-ip") is False

    def test_empty(self) -> None:
        assert is_valid_ip("") is False


class TestIsValidIpv4:
    """Tests for is_valid_ipv4()."""

    def test_valid(self) -> None:
        assert is_valid_ipv4("10.0.0.1") is True

    def test_broadcast(self) -> None:
        assert is_valid_ipv4("255.255.255.255") is True

    def test_invalid_octet(self) -> None:
        assert is_valid_ipv4("256.0.0.1") is False

    def test_ipv6_rejected(self) -> None:
        assert is_valid_ipv4("::1") is False


class TestIsValidPort:
    """Tests for is_valid_port()."""

    def test_valid_port(self) -> None:
        assert is_valid_port(80) is True

    def test_max_port(self) -> None:
        assert is_valid_port(65535) is True

    def test_zero_port(self) -> None:
        assert is_valid_port(0) is False

    def test_negative(self) -> None:
        assert is_valid_port(-1) is False

    def test_string_port(self) -> None:
        assert is_valid_port("80") is True

    def test_invalid_string(self) -> None:
        assert is_valid_port("abc") is False


class TestIsPrivateIp:
    """Tests for is_private_ip()."""

    def test_loopback(self) -> None:
        assert is_private_ip("127.0.0.1") is True

    def test_private_10(self) -> None:
        assert is_private_ip("10.0.0.1") is True

    def test_private_192(self) -> None:
        assert is_private_ip("192.168.1.1") is True

    def test_public(self) -> None:
        assert is_private_ip("8.8.8.8") is False

    def test_invalid(self) -> None:
        assert is_private_ip("not-an-ip") is False


class TestNormalizeHost:
    """Tests for normalize_host()."""

    def test_lowercase(self) -> None:
        assert normalize_host("EXAMPLE.COM") == "example.com"

    def test_strip(self) -> None:
        assert normalize_host("  192.168.1.1  ") == "192.168.1.1"
