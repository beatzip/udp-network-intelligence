"""Windows Firewall helper — manage firewall rules for the application.

Provides :class:`FirewallHelper` for adding/removing Windows Firewall
rules that allow the application to send and receive UDP traffic.
Uses ``netsh`` commands for firewall management.

On non-Windows platforms, this is a no-op.

Example::

    helper = FirewallHelper()
    helper.add_rule("UNI UDP Out", direction="out", port=27015)
    helper.remove_rule("UNI UDP Out")
"""

from __future__ import annotations

import logging
import platform
import subprocess
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class FirewallDirection(Enum):
    """Firewall rule direction."""

    IN = "in"
    OUT = "out"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> FirewallDirection:
        """Deserialize from string."""
        return cls(value)


class FirewallProtocol(Enum):
    """Firewall rule protocol."""

    UDP = "udp"
    TCP = "tcp"
    ANY = "any"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> FirewallProtocol:
        """Deserialize from string."""
        return cls(value)


@dataclass(frozen=True, slots=True)
class FirewallRule:
    """A firewall rule definition.

    Attributes:
        name: Rule name.
        direction: In or out.
        protocol: UDP, TCP, or any.
        port: Port number (0 = any).
        action: Allow or block.
        program: Path to the program (empty = any).
        enabled: Whether the rule is enabled.
        group: Rule group for organization.
    """

    name: str
    direction: FirewallDirection = FirewallDirection.OUT
    protocol: FirewallProtocol = FirewallProtocol.UDP
    port: int = 0
    action: str = "allow"
    program: str = ""
    enabled: bool = True
    group: str = "UDP Network Intelligence"


class FirewallHelper:
    """Windows Firewall rule manager.

    Uses ``netsh advfirewall`` commands to add, remove, and query
    firewall rules. On non-Windows platforms, operations are no-ops.

    Attributes:
        is_windows: Whether running on Windows.

    Example::

        helper = FirewallHelper()
        if helper.is_windows:
            helper.add_rule("UNI Probe", port=0, protocol="udp")
            rules = helper.list_rules("UNI")
            helper.remove_rule("UNI Probe")
    """

    def __init__(self) -> None:
        """Initialize the firewall helper."""
        self.is_windows = platform.system() == "Windows"

    def add_rule(
        self,
        name: str,
        *,
        direction: str = "out",
        protocol: str = "udp",
        port: int = 0,
        action: str = "allow",
        program: str = "",
        enabled: bool = True,
    ) -> bool:
        """Add a firewall rule.

        Args:
            name: Rule name.
            direction: ``"in"`` or ``"out"``.
            protocol: ``"udp"``, ``"tcp"``, or ``"any"``.
            port: Port number (0 = any).
            action: ``"allow"`` or ``"block"``.
            program: Path to the program executable.
            enabled: Whether the rule is active.

        Returns:
            True if the rule was added successfully.
        """
        if not self.is_windows:
            logger.debug("Firewall: skipping (not Windows)")
            return True

        cmd = [
            "netsh", "advfirewall", "firewall", "add", "rule",
            f"name={name}",
            f"dir={direction}",
            f"action={action}",
            f"protocol={protocol}",
            f"enable={'yes' if enabled else 'no'}",
        ]

        if port > 0:
            cmd.append(f"localport={port}")
        if program:
            cmd.append(f"program={program}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Firewall rule added: %s", name)
                return True
            else:
                logger.warning(
                    "Firewall rule failed: %s — %s",
                    name,
                    result.stderr.strip(),
                )
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Firewall command failed: %s", exc)
            return False

    def remove_rule(self, name: str) -> bool:
        """Remove a firewall rule by name.

        Args:
            name: Rule name to remove.

        Returns:
            True if the rule was removed successfully.
        """
        if not self.is_windows:
            return True

        cmd = [
            "netsh", "advfirewall", "firewall", "delete", "rule",
            f"name={name}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info("Firewall rule removed: %s", name)
                return True
            else:
                logger.debug(
                    "Firewall remove result: %s",
                    result.stderr.strip(),
                )
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            logger.warning("Firewall remove failed: %s", exc)
            return False

    def list_rules(self, name_filter: str = "") -> list[dict[str, str]]:
        """List firewall rules matching a name filter.

        Args:
            name_filter: Optional name prefix to filter by.

        Returns:
            List of rule dictionaries.
        """
        if not self.is_windows:
            return []

        cmd = [
            "netsh", "advfirewall", "firewall", "show", "rule",
            f"name={name_filter}" if name_filter else "all",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return self._parse_rules(result.stdout)
            return []
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            return []

    def rule_exists(self, name: str) -> bool:
        """Check if a firewall rule exists.

        Args:
            name: Rule name to check.

        Returns:
            True if the rule exists.
        """
        rules = self.list_rules(name_filter=name)
        return any(r.get("Rule Name", "") == name for r in rules)

    @staticmethod
    def _parse_rules(output: str) -> list[dict[str, str]]:
        """Parse netsh output into rule dictionaries.

        Args:
            output: Raw netsh output.

        Returns:
            List of parsed rules.
        """
        rules: list[dict[str, str]] = []
        current: dict[str, str] = {}

        for line in output.splitlines():
            line = line.strip()
            if not line:
                if current:
                    rules.append(current)
                    current = {}
                continue

            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip()
                if key.startswith("Rule Name"):
                    current["Rule Name"] = value
                elif key == "Enabled":
                    current["Enabled"] = value
                elif key == "Direction":
                    current["Direction"] = value
                elif key == "Action":
                    current["Action"] = value
                elif key == "Protocol":
                    current["Protocol"] = value
                elif key == "LocalPort":
                    current["LocalPort"] = value

        if current:
            rules.append(current)

        return rules

    def add_application_rule(
        self,
        name: str,
        program_path: str,
        *,
        direction: str = "out",
        protocol: str = "udp",
        action: str = "allow",
    ) -> bool:
        """Add a firewall rule for a specific application.

        Args:
            name: Rule name.
            program_path: Full path to the executable.
            direction: ``"in"`` or ``"out"``.
            protocol: ``"udp"`` or ``"tcp"``.
            action: ``"allow"`` or ``"block"``.

        Returns:
            True if the rule was added.
        """
        return self.add_rule(
            name,
            direction=direction,
            protocol=protocol,
            action=action,
            program=program_path,
        )

    def cleanup_app_rules(self, name_prefix: str = "UNI") -> int:
        """Remove all rules matching a name prefix.

        Args:
            name_prefix: Name prefix to match.

        Returns:
            Number of rules removed.
        """
        rules = self.list_rules(name_filter=name_prefix)
        removed = 0
        for rule in rules:
            name = rule.get("Rule Name", "")
            if name.startswith(name_prefix):
                if self.remove_rule(name):
                    removed += 1
        return removed
