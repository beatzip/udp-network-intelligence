"""Tests for uni.utils.format module."""

from __future__ import annotations

from uni.utils.format import (
    format_bitrate,
    format_bytes,
    format_duration,
    format_loss_rate,
    format_ms,
    format_percentage,
)


class TestFormatMs:
    """Tests for format_ms()."""

    def test_microseconds(self) -> None:
        assert format_ms(0.5) == "500 us"

    def test_milliseconds(self) -> None:
        assert format_ms(42.3) == "42.3 ms"

    def test_seconds(self) -> None:
        assert format_ms(1500.0) == "1.5 s"

    def test_zero(self) -> None:
        assert format_ms(0.0) == "0 us"


class TestFormatBytes:
    """Tests for format_bytes()."""

    def test_bytes(self) -> None:
        assert format_bytes(512) == "512.0 B"

    def test_kilobytes(self) -> None:
        assert format_bytes(1536) == "1.5 KB"

    def test_megabytes(self) -> None:
        assert format_bytes(1048576) == "1.0 MB"

    def test_zero(self) -> None:
        assert format_bytes(0) == "0.0 B"


class TestFormatBitrate:
    """Tests for format_bitrate()."""

    def test_bps(self) -> None:
        assert format_bitrate(500) == "500.0 bps"

    def test_kbps(self) -> None:
        assert format_bitrate(1500) == "1.5 Kbps"

    def test_mbps(self) -> None:
        assert format_bitrate(1_500_000) == "1.5 Mbps"


class TestFormatDuration:
    """Tests for format_duration()."""

    def test_seconds(self) -> None:
        assert format_duration(45.2) == "45.2s"

    def test_minutes(self) -> None:
        assert format_duration(125) == "2m 05s"

    def test_hours(self) -> None:
        assert format_duration(3725) == "1h 02m 05s"


class TestFormatPercentage:
    """Tests for format_percentage()."""

    def test_basic(self) -> None:
        assert format_percentage(2.5) == "2.5%"

    def test_zero(self) -> None:
        assert format_percentage(0.0) == "0.0%"


class TestFormatLossRate:
    """Tests for format_loss_rate()."""

    def test_zero_loss(self) -> None:
        assert format_loss_rate(0.0) == "0.0%"

    def test_ten_percent(self) -> None:
        assert format_loss_rate(0.1) == "10.0%"

    def test_full_loss(self) -> None:
        assert format_loss_rate(1.0) == "100.0%"
