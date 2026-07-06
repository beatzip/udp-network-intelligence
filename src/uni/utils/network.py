"""Network utilities — local IP, DNS resolve, interface enumeration."""

from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NetworkInterface:
    """Represents a local network interface."""
    name: str
    address: str
    netmask: str = ""
    is_up: bool = True


def get_local_ip() -> str:
    """Get the local IP address (non-loopback).

    Returns:
        Local IP address string, or "127.0.0.1" as fallback.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
        finally:
            sock.close()
    except OSError:
        return "127.0.0.1"


async def resolve_dns(host: str) -> list[str]:
    """Resolve a hostname to IP addresses.

    Args:
        host: Hostname to resolve.

    Returns:
        List of IP address strings.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, family=socket.AF_INET)
        return list({info[4][0] for info in infos})
    except (socket.gaierror, OSError):
        return []


def list_interfaces() -> list[NetworkInterface]:
    """List local network interfaces.

    Returns:
        List of NetworkInterface objects.
    """
    interfaces: list[NetworkInterface] = []
    try:
        hostname = socket.gethostname()
        addrs = socket.getaddrinfo(hostname, None, socket.AF_INET)
        seen: set[str] = set()
        for info in addrs:
            addr = str(info[4][0])
            if addr not in seen and addr != "127.0.0.1":
                seen.add(addr)
                interfaces.append(NetworkInterface(name=hostname, address=addr))
    except (socket.gaierror, OSError):
        pass

    if not interfaces:
        interfaces.append(
            NetworkInterface(name="loopback", address="127.0.0.1", is_up=True)
        )

    return interfaces


def is_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a UDP port is reachable (best-effort).

    Args:
        host: Target host.
        port: Target port.
        timeout: Connection timeout in seconds.

    Returns:
        True if the port responded.
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        try:
            sock.sendto(b"\x00", (host, port))
            sock.recvfrom(1024)
            return True
        except (TimeoutError, OSError):
            return False
        finally:
            sock.close()
    except OSError:
        return False
