"""IP address validation, parsing, and port extraction."""

from __future__ import annotations

import ipaddress
import re

# Pattern for IP:Port or [IPv6]:Port
_TARGET_PATTERN = re.compile(
    r"^(?P<host>"
    r"(?:\d{1,3}\.){3}\d{1,3}"  # IPv4
    r"|(?:[0-9a-fA-F:]+:+)+[0-9a-fA-F]+"  # IPv6
    r"|[\w.-]+"  # hostname
    r")"
    r":(?P<port>\d{1,5})$"
)

_IPV4_PATTERN = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)$"
)


class InvalidTargetError(Exception):
    """Raised when a target string is invalid."""


def parse_target(target: str) -> tuple[str, int]:
    """Parse a target string into (host, port).

    Supports formats:
    - "1.2.3.4:27015"
    - "[::1]:27015"
    - "hostname:27015"

    Args:
        target: Target string.

    Returns:
        Tuple of (host, port).

    Raises:
        InvalidTargetError: If the target format is invalid.
    """
    match = _TARGET_PATTERN.match(target.strip())
    if not match:
        raise InvalidTargetError(f"Invalid target: {target!r}")

    host = match.group("host")
    port = int(match.group("port"))

    if not (1 <= port <= 65535):
        raise InvalidTargetError(f"Port out of range: {port}")

    return host, port


def is_valid_ip(value: str) -> bool:
    """Check if a string is a valid IPv4 or IPv6 address.

    Args:
        value: String to validate.

    Returns:
        True if valid IP address.
    """
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def is_valid_ipv4(value: str) -> bool:
    """Check if a string is a valid IPv4 address.

    Args:
        value: String to validate.

    Returns:
        True if valid IPv4.
    """
    return bool(_IPV4_PATTERN.match(value))


def is_valid_port(port: int | str) -> bool:
    """Check if a port number is valid.

    Args:
        port: Port number (int or string).

    Returns:
        True if 1 <= port <= 65535.
    """
    try:
        p = int(port)
        return 1 <= p <= 65535
    except (ValueError, TypeError):
        return False


def is_private_ip(value: str) -> bool:
    """Check if an IP address is in a private/reserved range.

    Args:
        value: IP address string.

    Returns:
        True if the IP is private (RFC 1918, loopback, link-local, etc.).
    """
    try:
        addr = ipaddress.ip_address(value)
        return addr.is_private or addr.is_loopback or addr.is_link_local
    except ValueError:
        return False


def normalize_host(host: str) -> str:
    """Normalize a host string (strip whitespace, lowercase).

    Args:
        host: Host string.

    Returns:
        Normalized host.
    """
    return host.strip().lower()
