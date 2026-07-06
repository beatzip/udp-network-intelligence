"""Traceroute ViewModel — manages UDP traceroute execution."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Signal

from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class TracerouteViewModel(BaseViewModel):
    """Manages traceroute execution and hop display.

    Signals:
        traceroute_started: Emitted with target.
        hop_resolved: Emitted with hop dict (ttl, ip, rtt, hostname).
        traceroute_completed: Emitted with result dict.
    """

    traceroute_started = Signal(str)
    hop_resolved = Signal(dict)
    traceroute_completed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self._running = False
        self._hops: list[dict] = []

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def hops(self) -> list[dict]:
        return list(self._hops)

    async def run_traceroute(
        self, host: str, port: int = 27015, max_hops: int = 30
    ) -> None:
        """Run a UDP traceroute.

        Args:
            host: Target host.
            port: Target port.
            max_hops: Maximum hops to trace.
        """
        if self._running:
            self.emit_error("Traceroute already running")
            return

        self._running = True
        self._hops.clear()
        self.traceroute_started.emit(host)
        self.emit_status(f"Tracerouting {host}:{port}...")

        try:
            import socket
            import struct

            from uni.net.icmp_socket import AsyncICMPSocket
            from uni.net.udp_socket import AsyncUDPSocket, SocketConfig

            target_ip = socket.gethostbyname(host)

            # Try ICMP socket for responses
            icmp_sock = AsyncICMPSocket()
            try:
                await icmp_sock.open()
            except (PermissionError, OSError):
                logger.warning("ICMP socket unavailable, traceroute limited")

            udp_config = SocketConfig(host="0.0.0.0", port=0, timeout=2.0)

            async with AsyncUDPSocket(udp_config) as sock:
                for ttl in range(1, max_hops + 1):
                    sock.set_ttl(ttl)
                    payload = struct.pack("!HH", ttl, ttl) + b"\x00" * 32

                    pkt = await sock.send_receive(
                        payload, (target_ip, port), timeout=2.0
                    )

                    hop: dict[str, Any] = {
                        "ttl": ttl,
                        "ip": pkt.source[0] if pkt.is_success else "*",
                        "rtt_ms": pkt.rtt_ms if pkt.rtt_ms else None,
                        "is_timeout": not pkt.is_success,
                    }

                    self._hops.append(hop)
                    self.hop_resolved.emit(hop)

                    # Check if we reached the destination
                    if pkt.is_success and pkt.source[0] == target_ip:
                        break

            self.traceroute_completed.emit({
                "target": host,
                "hops": self._hops,
                "resolved": len([h for h in self._hops if not h["is_timeout"]]),
                "total": len(self._hops),
            })
            self.emit_status(
                f"Traceroute complete: {self.hop_count} hops resolved"
            )

        except Exception as exc:
            self.emit_error(f"Traceroute failed: {exc}")
        finally:
            self._running = False

    @property
    def hop_count(self) -> int:
        """Number of resolved hops."""
        return len([h for h in self._hops if not h["is_timeout"]])
