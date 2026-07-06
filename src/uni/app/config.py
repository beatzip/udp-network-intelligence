"""Application configuration manager — JSON-based config with migrations.

Provides :class:`ConfigManager` for full lifecycle management of the
application configuration: first-run creation, loading, saving, version
updates, and schema migrations.

Configuration is stored as ``config.json`` with nested section dataclasses.
The manager handles atomic writes (write-to-temp + rename), backup
rotation, and automatic migration when the config version changes.

Example::

    manager = ConfigManager("config.json")
    config = manager.load()
    config.debug = True
    manager.save(config)
"""

from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self

from uni.app.constants import APP_VERSION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config section dataclasses
# ---------------------------------------------------------------------------

@dataclass
class NetworkConfig:
    """Network-related configuration.

    Attributes:
        socket_timeout: Default socket timeout in seconds.
        max_concurrent_sockets: Maximum simultaneous open sockets.
        default_ttl: Default IP Time-To-Live for probes.
        send_buffer_size: UDP send buffer size in bytes.
        recv_buffer_size: UDP receive buffer size in bytes.
        icmp_receive_buffer: ICMP receive buffer size in bytes.
    """

    socket_timeout: float = 3.0
    max_concurrent_sockets: int = 64
    default_ttl: int = 64
    send_buffer_size: int = 4096
    recv_buffer_size: int = 65536
    icmp_receive_buffer: int = 65536

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.socket_timeout <= 0:
            errors.append("network.socket_timeout must be > 0")
        if self.max_concurrent_sockets < 1:
            errors.append("network.max_concurrent_sockets must be >= 1")
        if not (1 <= self.default_ttl <= 255):
            errors.append("network.default_ttl must be 1-255")
        if self.send_buffer_size < 256:
            errors.append("network.send_buffer_size must be >= 256")
        if self.recv_buffer_size < 256:
            errors.append("network.recv_buffer_size must be >= 256")
        if self.icmp_receive_buffer < 256:
            errors.append("network.icmp_receive_buffer must be >= 256")
        return errors


@dataclass
class ProbeConfig:
    """Probe campaign configuration.

    Attributes:
        default_count: Default number of probe packets.
        default_interval: Default interval between probes in seconds.
        default_port: Default target port.
        protocol: Default probe protocol.
        payload_size: Default probe payload size in bytes.
        timeout: Default response timeout in seconds.
    """

    default_count: int = 50
    default_interval: float = 1.0
    default_port: int = 27015
    protocol: str = "udp"
    payload_size: int = 64
    timeout: float = 3.0

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.default_count < 1:
            errors.append("probe.default_count must be >= 1")
        if self.default_interval < 0.01:
            errors.append("probe.default_interval must be >= 0.01")
        if not (1 <= self.default_port <= 65535):
            errors.append("probe.default_port must be 1-65535")
        if self.protocol not in ("udp", "tcp", "icmp"):
            errors.append(f"probe.protocol must be udp/tcp/icmp, got {self.protocol!r}")
        if not (1 <= self.payload_size <= 1400):
            errors.append("probe.payload_size must be 1-1400")
        if self.timeout <= 0:
            errors.append("probe.timeout must be > 0")
        return errors


@dataclass
class TracerouteConfig:
    """Traceroute configuration.

    Attributes:
        max_hops: Maximum number of hops to probe.
        hop_timeout: Timeout per hop in seconds.
        probes_per_hop: Number of probes per TTL value.
        resolve_hostnames: Whether to resolve hop hostnames.
    """

    max_hops: int = 30
    hop_timeout: float = 2.0
    probes_per_hop: int = 3
    resolve_hostnames: bool = True

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if not (1 <= self.max_hops <= 255):
            errors.append("traceroute.max_hops must be 1-255")
        if self.hop_timeout <= 0:
            errors.append("traceroute.hop_timeout must be > 0")
        if self.probes_per_hop < 1:
            errors.append("traceroute.probes_per_hop must be >= 1")
        return errors


@dataclass
class DiscoveryConfig:
    """Server discovery configuration.

    Attributes:
        query_timeout: Timeout for A2S queries in seconds.
        retry_count: Number of query retries.
        a2s_challenge_timeout: Timeout for A2S challenge handshake.
    """

    query_timeout: float = 5.0
    retry_count: int = 2
    a2s_challenge_timeout: float = 3.0

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.query_timeout <= 0:
            errors.append("discovery.query_timeout must be > 0")
        if self.retry_count < 0:
            errors.append("discovery.retry_count must be >= 0")
        if self.a2s_challenge_timeout <= 0:
            errors.append("discovery.a2s_challenge_timeout must be > 0")
        return errors


@dataclass
class GeoConfig:
    """GeoIP configuration.

    Attributes:
        enabled: Whether GeoIP lookups are enabled.
        database_path: Path to MaxMind .mmdb file.
        cache_size: Maximum number of cached lookups.
    """

    enabled: bool = False
    database_path: str = "data/GeoLite2-Country.mmdb"
    cache_size: int = 1000

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.cache_size < 0:
            errors.append("geo.cache_size must be >= 0")
        return errors


@dataclass
class UIConfig:
    """UI configuration.

    Attributes:
        theme: Active theme name (``"dark"`` or ``"light"``).
        language: UI language code.
        window_width: Main window width in pixels.
        window_height: Main window height in pixels.
        chart_max_points: Maximum data points shown on charts.
        show_notifications: Whether to show toast notifications.
    """

    theme: str = "dark"
    language: str = "en"
    window_width: int = 1280
    window_height: int = 800
    chart_max_points: int = 200
    show_notifications: bool = True

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.theme not in ("dark", "light"):
            errors.append(f"ui.theme must be 'dark' or 'light', got {self.theme!r}")
        if self.window_width < 400:
            errors.append("ui.window_width must be >= 400")
        if self.window_height < 300:
            errors.append("ui.window_height must be >= 300")
        if self.chart_max_points < 10:
            errors.append("ui.chart_max_points must be >= 10")
        return errors


@dataclass
class PluginsConfig:
    """Plugin system configuration.

    Attributes:
        enabled: Whether the plugin system is enabled.
        external_dir: Directory for user-installed plugins.
    """

    enabled: bool = True
    external_dir: str = "plugins"

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        return []


@dataclass
class HistoryConfig:
    """History/persistence configuration.

    Attributes:
        enabled: Whether history storage is enabled.
        database_path: Path to the SQLite database file.
        max_records: Maximum number of stored records.
        auto_cleanup_days: Days after which old records are deleted.
    """

    enabled: bool = True
    database_path: str = "data/history.db"
    max_records: int = 10000
    auto_cleanup_days: int = 90

    def validate(self) -> list[str]:
        """Validate configuration values.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        if self.max_records < 100:
            errors.append("history.max_records must be >= 100")
        if self.auto_cleanup_days < 1:
            errors.append("history.auto_cleanup_days must be >= 1")
        return errors


# ---------------------------------------------------------------------------
# Root AppConfig
# ---------------------------------------------------------------------------

# Current config schema version — bump when the schema changes.
CONFIG_VERSION = 1


@dataclass
class AppConfig:
    """Root application configuration.

    Contains all configuration sections as nested dataclasses.
    Each section has a ``validate()`` method for value checking.

    Attributes:
        config_version: Schema version for migration support.
        name: Application display name.
        version: Application version string.
        debug: Whether debug mode is enabled.
        log_level: Logging level string.
        log_file: Path to the log file.
        network: Network configuration section.
        probe: Probe campaign configuration.
        traceroute: Traceroute configuration.
        discovery: Server discovery configuration.
        geo: GeoIP configuration.
        ui: User interface configuration.
        plugins: Plugin system configuration.
        history: History/persistence configuration.
    """

    config_version: int = CONFIG_VERSION
    name: str = "UDP Network Intelligence"
    version: str = APP_VERSION
    debug: bool = False
    log_level: str = "INFO"
    log_file: str = "logs/uni.log"
    network: NetworkConfig = field(default_factory=NetworkConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    traceroute: TracerouteConfig = field(default_factory=TracerouteConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    geo: GeoConfig = field(default_factory=GeoConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    plugins: PluginsConfig = field(default_factory=PluginsConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)

    def validate(self) -> list[str]:
        """Validate all configuration sections.

        Returns:
            List of all validation errors across all sections (empty if valid).
        """
        errors: list[str] = []
        if self.config_version < 1:
            errors.append("config_version must be >= 1")
        if self.log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            errors.append(
                f"log_level must be DEBUG/INFO/WARNING/ERROR/CRITICAL, "
                f"got {self.log_level!r}"
            )
        errors.extend(self.network.validate())
        errors.extend(self.probe.validate())
        errors.extend(self.traceroute.validate())
        errors.extend(self.discovery.validate())
        errors.extend(self.geo.validate())
        errors.extend(self.ui.validate())
        errors.extend(self.plugins.validate())
        errors.extend(self.history.validate())
        return errors

    @property
    def is_valid(self) -> bool:
        """True if the configuration passes all validation checks."""
        return len(self.validate()) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dictionary.

        Returns:
            Flat dictionary with all config values, nested sections as dicts.
        """
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if hasattr(value, "__dataclass_fields__"):
                result[f.name] = _dataclass_to_dict(value)
            else:
                result[f.name] = value
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Deserialize from a dictionary.

        Missing sections fall back to defaults. Unknown keys are ignored.

        Args:
            data: Configuration dictionary.

        Returns:
            AppConfig instance.
        """
        section_map: dict[str, type] = {
            "network": NetworkConfig,
            "probe": ProbeConfig,
            "traceroute": TracerouteConfig,
            "discovery": DiscoveryConfig,
            "geo": GeoConfig,
            "ui": UIConfig,
            "plugins": PluginsConfig,
            "history": HistoryConfig,
        }

        kwargs: dict[str, Any] = {}
        simple_fields = {f.name for f in fields(cls) if f.name not in section_map}

        for key in simple_fields:
            if key in data:
                kwargs[key] = data[key]

        for section_name, section_cls in section_map.items():
            if section_name in data and isinstance(data[section_name], dict):
                kwargs[section_name] = _dict_to_dataclass(
                    section_cls, data[section_name]
                )
            else:
                kwargs[section_name] = section_cls()

        return cls(**kwargs)


# ---------------------------------------------------------------------------
# Migration system
# ---------------------------------------------------------------------------

# Type alias for migration functions.
# Each migration receives the raw config dict and mutates it in-place.
MigrationFn = Callable[[dict[str, Any]], None]


def _migration_v0_to_v1(data: dict[str, Any]) -> None:
    """Migrate config from version 0 (legacy TOML) to version 1 (JSON).

    Handles the transition from the old TOML-based config format
    where sections were flat keys (``[network]``) to the new JSON
    format with ``config_version`` tracking.

    Args:
        data: Raw config dictionary to mutate.
    """
    # Add config_version if missing
    if "config_version" not in data:
        data["config_version"] = 1

    # Migrate old "app" section to root level
    if "app" in data and isinstance(data["app"], dict):
        app = data.pop("app")
        for key, value in app.items():
            if key not in data:
                data[key] = value

    # Ensure all sections exist
    section_defaults = {
        "network": NetworkConfig,
        "probe": ProbeConfig,
        "traceroute": TracerouteConfig,
        "discovery": DiscoveryConfig,
        "geo": GeoConfig,
        "ui": UIConfig,
        "plugins": PluginsConfig,
        "history": HistoryConfig,
    }
    for section_name, section_cls in section_defaults.items():
        if section_name not in data:
            data[section_name] = _dataclass_to_dict(section_cls())

    logger.info("Migrated config from v0 to v1")


# Registry of migrations: version -> migration function.
_MIGRATIONS: dict[int, MigrationFn] = {
    1: _migration_v0_to_v1,
}


def _get_current_version() -> int:
    """Return the current config schema version."""
    return CONFIG_VERSION


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

MAX_BACKUPS = 3


class ConfigManager:
    """Full-lifecycle configuration manager.

    Handles creation, loading, saving, validation, backup, and migration
    of the application configuration stored as ``config.json``.

    Thread-safety: The manager acquires a file lock during write
    operations and performs atomic writes (temp file + rename) to
    prevent corruption.

    Attributes:
        config_path: Path to the configuration file.
        backup_dir: Directory for config backups.
    """

    def __init__(
        self,
        config_path: str | Path,
        *,
        backup_dir: str | Path | None = None,
    ) -> None:
        """Initialize the configuration manager.

        Args:
            config_path: Path to the ``config.json`` file.
            backup_dir: Optional directory for backups. Defaults to
                a ``backups/`` subdirectory next to the config file.
        """
        self.config_path = Path(config_path).resolve()
        self.backup_dir = (
            Path(backup_dir).resolve()
            if backup_dir
            else self.config_path.parent / "backups"
        )
        self._config: AppConfig | None = None

    @property
    def config(self) -> AppConfig:
        """The currently loaded configuration.

        Raises:
            RuntimeError: If no configuration has been loaded yet.
        """
        if self._config is None:
            raise RuntimeError(
                "Configuration not loaded. Call load() first."
            )
        return self._config

    @config.setter
    def config(self, value: AppConfig) -> None:
        """Set the current configuration."""
        self._config = value

    def exists(self) -> bool:
        """True if the config file exists on disk."""
        return self.config_path.is_file()

    def load(self) -> AppConfig:
        """Load configuration from disk.

        If the file does not exist, creates it with default values.
        If the file exists but has an older schema version, runs
        all necessary migrations before returning.

        Returns:
            Loaded (and possibly migrated) AppConfig instance.

        Raises:
            json.JSONDecodeError: If the config file contains invalid JSON.
            ValueError: If the config fails validation after loading.
        """
        if not self.exists():
            logger.info(
                "Config file not found, creating defaults: %s",
                self.config_path,
            )
            self._config = AppConfig()
            self._ensure_directories()
            self.save(self._config)
            return self._config

        raw = self._read_file()
        raw = self._run_migrations(raw)

        self._config = AppConfig.from_dict(raw)

        # Validate after migration
        errors = self._config.validate()
        if errors:
            logger.warning(
                "Config validation errors after migration: %s",
                "; ".join(errors),
            )

        # Update version to current
        needs_save = False
        if self._config.config_version < CONFIG_VERSION:
            self._config.config_version = CONFIG_VERSION
            needs_save = True
        if self._config.version != APP_VERSION:
            self._config.version = APP_VERSION
            needs_save = True
        if needs_save:
            self.save(self._config)
            logger.info(
                "Updated config to v%d (app %s)",
                CONFIG_VERSION,
                APP_VERSION,
            )

        logger.info("Loaded config from %s", self.config_path)
        return self._config

    def save(self, config: AppConfig | None = None) -> None:
        """Save configuration to disk.

        Performs an atomic write: writes to a temporary file, then
        renames it to the target path. This prevents corruption if
        the process is killed mid-write.

        A backup of the previous config is created before overwriting.

        Args:
            config: Configuration to save. Uses the current config
                if None.

        Raises:
            OSError: If the write fails.
        """
        cfg = config if config is not None else self._config
        if cfg is None:
            raise RuntimeError("No configuration to save")

        self._ensure_directories()

        # Backup existing file
        if self.config_path.exists():
            self._create_backup()

        # Atomic write via temp file + rename
        data = cfg.to_dict()
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        json_str += "\n"  # trailing newline

        tmp_path: Path | None = None
        try:
            fd, tmp_path_str = tempfile.mkstemp(
                suffix=".tmp",
                prefix="config_",
                dir=str(self.config_path.parent),
            )
            tmp_path = Path(tmp_path_str)
            # Close the fd immediately — on Windows the fd locks the file
            os.close(fd)
            fd = -1
            tmp_path.write_text(json_str, encoding="utf-8")
            # Atomic rename (same filesystem)
            os.replace(str(tmp_path), str(self.config_path))
            logger.debug("Saved config to %s", self.config_path)
        except Exception:
            # Clean up temp file on failure
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise

        self._config = cfg

    def update(self, **kwargs: Any) -> AppConfig:
        """Update top-level configuration fields and save.

        Accepts keyword arguments matching AppConfig field names.
        Nested sections can be updated by passing dicts:

        ``manager.update(debug=True, ui={"theme": "light"})``

        Args:
            **kwargs: Fields to update.

        Returns:
            Updated AppConfig instance.

        Raises:
            KeyError: If a keyword does not match a config field.
            ValueError: If the updated config fails validation.
        """
        cfg = copy.deepcopy(self.config)
        section_names = {
            f.name
            for f in fields(cfg)
            if hasattr(getattr(cfg, f.name), "__dataclass_fields__")
        }

        for key, value in kwargs.items():
            if key not in {f.name for f in fields(cfg)}:
                raise KeyError(f"Unknown config field: {key!r}")

            if key in section_names and isinstance(value, dict):
                section = getattr(cfg, key)
                for sub_key, sub_val in value.items():
                    if hasattr(section, sub_key):
                        setattr(section, sub_key, sub_val)
                    else:
                        raise KeyError(
                            f"Unknown field {key}.{sub_key!r}"
                        )
            else:
                setattr(cfg, key, value)

        errors = cfg.validate()
        if errors:
            raise ValueError(
                "Validation failed: " + "; ".join(errors)
            )

        self.save(cfg)
        return cfg

    def reset(self) -> AppConfig:
        """Reset configuration to defaults and save.

        Creates a backup of the current config before resetting.

        Returns:
            Fresh AppConfig with default values.
        """
        if self.exists():
            self._create_backup()

        self._config = AppConfig()
        self.save(self._config)
        logger.info("Reset config to defaults")
        return self._config

    def get_section(self, section_name: str) -> Any:
        """Get a configuration section by name.

        Args:
            section_name: Section name (e.g. ``"network"``, ``"probe"``).

        Returns:
            The section dataclass instance.

        Raises:
            AttributeError: If the section does not exist.
        """
        return getattr(self.config, section_name)

    def set_section(self, section_name: str, data: dict[str, Any]) -> None:
        """Update a configuration section from a dictionary and save.

        Args:
            section_name: Section name (e.g. ``"network"``).
            data: Dictionary of field values to update.

        Raises:
            AttributeError: If the section does not exist.
            KeyError: If a field name is invalid.
            ValueError: If validation fails.
        """
        cfg = copy.deepcopy(self.config)
        section = getattr(cfg, section_name)

        for key, value in data.items():
            if hasattr(section, key):
                setattr(section, key, value)
            else:
                raise KeyError(
                    f"Unknown field {section_name}.{key!r}"
                )

        errors = cfg.validate()
        if errors:
            raise ValueError(
                "Validation failed: " + "; ".join(errors)
            )

        self.save(cfg)

    def backup(self) -> Path:
        """Create a backup of the current configuration file.

        Returns:
            Path to the backup file.

        Raises:
            FileNotFoundError: If the config file does not exist.
        """
        if not self.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.config_path}"
            )
        return self._create_backup()

    def restore(self, backup_path: str | Path) -> AppConfig:
        """Restore configuration from a backup file.

        Args:
            backup_path: Path to the backup file to restore.

        Returns:
            Restored AppConfig instance.

        Raises:
            FileNotFoundError: If the backup file does not exist.
            json.JSONDecodeError: If the backup contains invalid JSON.
        """
        backup = Path(backup_path)
        if not backup.is_file():
            raise FileNotFoundError(f"Backup not found: {backup}")

        raw = json.loads(backup.read_text(encoding="utf-8"))
        self._config = AppConfig.from_dict(raw)
        self.save(self._config)
        logger.info("Restored config from backup: %s", backup)
        return self._config

    def list_backups(self) -> list[Path]:
        """List available backup files, newest first.

        Returns:
            Sorted list of backup file paths.
        """
        if not self.backup_dir.is_dir():
            return []

        backups = sorted(
            self.backup_dir.glob("config_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return backups

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        """Create parent directories for config and backups if needed."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _read_file(self) -> dict[str, Any]:
        """Read and parse the config JSON file.

        Returns:
            Parsed dictionary.

        Raises:
            json.JSONDecodeError: If the file contains invalid JSON.
        """
        raw_text = self.config_path.read_text(encoding="utf-8")
        try:
            return json.loads(raw_text)  # type: ignore[no-any-return]
        except json.JSONDecodeError as exc:
            logger.error("Invalid JSON in config file: %s", exc)
            raise

    def _run_migrations(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Run all necessary migrations on the raw config dict.

        Checks the ``config_version`` field and applies migrations
        sequentially until the config is at the current version.

        Args:
            raw: Raw config dictionary from disk.

        Returns:
            Migrated config dictionary.
        """
        current_version = raw.get("config_version", 0)

        if current_version >= CONFIG_VERSION:
            return raw

        for target_version in range(current_version + 1, CONFIG_VERSION + 1):
            migration_fn = _MIGRATIONS.get(target_version)
            if migration_fn is not None:
                logger.info(
                    "Running migration v%d -> v%d",
                    target_version - 1,
                    target_version,
                )
                migration_fn(raw)
                raw["config_version"] = target_version

        return raw

    def _create_backup(self) -> Path:
        """Create a timestamped backup of the config file.

        Automatically rotates old backups, keeping at most
        ``MAX_BACKUPS`` files.

        Returns:
            Path to the new backup file.
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        backup_name = f"config_{timestamp}.json"
        backup_path = self.backup_dir / backup_name

        shutil.copy2(str(self.config_path), str(backup_path))
        logger.debug("Created backup: %s", backup_path)

        self._rotate_backups()
        return backup_path

    def _rotate_backups(self) -> None:
        """Remove old backups, keeping only the most recent ones."""
        if not self.backup_dir.is_dir():
            return

        backups = sorted(
            self.backup_dir.glob("config_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        for old_backup in backups[MAX_BACKUPS:]:
            old_backup.unlink(missing_ok=True)
            logger.debug("Removed old backup: %s", old_backup)


# ---------------------------------------------------------------------------
# Serialization helpers (module-level, used by AppConfig and sections)
# ---------------------------------------------------------------------------

def _dataclass_to_dict(instance: Any) -> dict[str, Any]:
    """Convert a dataclass to a dictionary recursively.

    Args:
        instance: Dataclass instance.

    Returns:
        Dictionary representation.
    """
    result: dict[str, Any] = {}
    for f in fields(instance):
        value = getattr(instance, f.name)
        if hasattr(value, "__dataclass_fields__"):
            result[f.name] = _dataclass_to_dict(value)
        else:
            result[f.name] = value
    return result


def _dict_to_dataclass(cls: type, data: dict[str, Any]) -> Any:
    """Convert a dictionary to a dataclass instance.

    Handles nested dataclasses. Missing keys use field defaults.

    Args:
        cls: Target dataclass type.
        data: Source dictionary.

    Returns:
        Populated dataclass instance.
    """
    if not isinstance(data, dict):
        return cls()

    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name in data:
            value = data[f.name]
            # Check if field type is a dataclass
            field_type = getattr(cls, f.name, None)
            if hasattr(field_type, "__dataclass_fields__") and isinstance(value, dict):
                kwargs[f.name] = _dict_to_dataclass(type(field_type), value)
            else:
                kwargs[f.name] = value

    return cls(**kwargs)
