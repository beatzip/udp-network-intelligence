"""Human-readable formatters for bytes, milliseconds, duration, etc."""

from __future__ import annotations


def format_ms(value: float, decimals: int = 1) -> str:
    """Format milliseconds with unit.

    Args:
        value: Milliseconds.
        decimals: Decimal places.

    Returns:
        Formatted string, e.g. "42.3 ms".
    """
    if value < 1.0:
        return f"{value * 1000:.0f} us"
    if value >= 1000.0:
        return f"{value / 1000:.{decimals}f} s"
    return f"{value:.{decimals}f} ms"


def format_bytes(value: int | float, decimals: int = 1) -> str:
    """Format byte count with human-readable unit.

    Args:
        value: Byte count.
        decimals: Decimal places.

    Returns:
        Formatted string, e.g. "1.5 KB".
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024.0:
            return f"{value:.{decimals}f} {unit}"
        value /= 1024.0
    return f"{value:.{decimals}f} PB"


def format_bitrate(bits_per_second: float, decimals: int = 1) -> str:
    """Format bitrate with human-readable unit.

    Args:
        bits_per_second: Bitrate in bits per second.
        decimals: Decimal places.

    Returns:
        Formatted string, e.g. "1.5 Mbps".
    """
    value = bits_per_second
    for unit in ("bps", "Kbps", "Mbps", "Gbps", "Tbps"):
        if abs(value) < 1000.0:
            return f"{value:.{decimals}f} {unit}"
        value /= 1000.0
    return f"{value:.{decimals}f} Pbps"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds.

    Returns:
        Formatted string, e.g. "2h 15m 30s" or "45.2s".
    """
    if seconds < 60:
        return f"{seconds:.1f}s"

    minutes = int(seconds // 60)
    secs = int(seconds % 60)

    if minutes < 60:
        return f"{minutes}m {secs:02d}s"

    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins:02d}m {secs:02d}s"


def format_percentage(value: float, decimals: int = 1) -> str:
    """Format a percentage value.

    Args:
        value: Percentage (0-100).
        decimals: Decimal places.

    Returns:
        Formatted string, e.g. "2.5%".
    """
    return f"{value:.{decimals}f}%"


def format_loss_rate(loss_rate: float) -> str:
    """Format packet loss rate (0.0-1.0) as percentage.

    Args:
        loss_rate: Loss rate from 0.0 to 1.0.

    Returns:
        Formatted string, e.g. "2.5%".
    """
    return format_percentage(loss_rate * 100.0)
