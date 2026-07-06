"""Tests for uni.app.config module — ConfigManager and config dataclasses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uni.app.config import (
    CONFIG_VERSION,
    AppConfig,
    ConfigManager,
    HistoryConfig,
    NetworkConfig,
    ProbeConfig,
    TracerouteConfig,
    UIConfig,
)

# ---------------------------------------------------------------------------
# Section defaults
# ---------------------------------------------------------------------------


class TestNetworkConfig:
    """Tests for NetworkConfig defaults and validation."""

    def test_defaults(self) -> None:
        cfg = NetworkConfig()
        assert cfg.socket_timeout == 3.0
        assert cfg.max_concurrent_sockets == 64
        assert cfg.default_ttl == 64

    def test_valid(self) -> None:
        assert NetworkConfig().validate() == []

    def test_invalid_timeout(self) -> None:
        errors = NetworkConfig(socket_timeout=-1).validate()
        assert any("socket_timeout" in e for e in errors)

    def test_invalid_ttl(self) -> None:
        errors = NetworkConfig(default_ttl=0).validate()
        assert any("default_ttl" in e for e in errors)


class TestProbeConfig:
    """Tests for ProbeConfig defaults and validation."""

    def test_defaults(self) -> None:
        cfg = ProbeConfig()
        assert cfg.default_count == 50
        assert cfg.default_interval == 1.0
        assert cfg.default_port == 27015

    def test_valid(self) -> None:
        assert ProbeConfig().validate() == []

    def test_invalid_count(self) -> None:
        errors = ProbeConfig(default_count=0).validate()
        assert any("default_count" in e for e in errors)

    def test_invalid_protocol(self) -> None:
        errors = ProbeConfig(protocol="invalid").validate()
        assert any("protocol" in e for e in errors)


class TestTracerouteConfig:
    """Tests for TracerouteConfig defaults and validation."""

    def test_defaults(self) -> None:
        cfg = TracerouteConfig()
        assert cfg.max_hops == 30
        assert cfg.hop_timeout == 2.0
        assert cfg.probes_per_hop == 3

    def test_valid(self) -> None:
        assert TracerouteConfig().validate() == []

    def test_invalid_max_hops(self) -> None:
        errors = TracerouteConfig(max_hops=0).validate()
        assert any("max_hops" in e for e in errors)


class TestUIConfig:
    """Tests for UIConfig defaults and validation."""

    def test_defaults(self) -> None:
        cfg = UIConfig()
        assert cfg.theme == "dark"
        assert cfg.window_width == 1280

    def test_valid(self) -> None:
        assert UIConfig().validate() == []

    def test_invalid_theme(self) -> None:
        errors = UIConfig(theme="invalid").validate()
        assert any("theme" in e for e in errors)


class TestHistoryConfig:
    """Tests for HistoryConfig defaults and validation."""

    def test_defaults(self) -> None:
        cfg = HistoryConfig()
        assert cfg.enabled is True
        assert cfg.max_records == 10000

    def test_valid(self) -> None:
        assert HistoryConfig().validate() == []

    def test_invalid_max_records(self) -> None:
        errors = HistoryConfig(max_records=0).validate()
        assert any("max_records" in e for e in errors)


# ---------------------------------------------------------------------------
# AppConfig serialization
# ---------------------------------------------------------------------------


class TestAppConfig:
    """Tests for AppConfig dataclass."""

    def test_defaults(self) -> None:
        config = AppConfig()
        assert config.name == "UDP Network Intelligence"
        assert config.config_version == CONFIG_VERSION
        assert config.debug is False
        assert config.network.socket_timeout == 3.0
        assert config.probe.default_count == 50
        assert config.ui.theme == "dark"

    def test_valid_by_default(self) -> None:
        assert AppConfig().validate() == []

    def test_to_dict_roundtrip(self) -> None:
        original = AppConfig()
        original.debug = True
        original.ui.theme = "light"
        data = original.to_dict()
        restored = AppConfig.from_dict(data)
        assert restored.debug is True
        assert restored.ui.theme == "light"
        assert restored.network.socket_timeout == 3.0

    def test_from_dict_missing_sections(self) -> None:
        data = {"debug": True}
        config = AppConfig.from_dict(data)
        assert config.debug is True
        assert config.network.socket_timeout == 3.0
        assert config.ui.theme == "dark"

    def test_from_dict_empty(self) -> None:
        config = AppConfig.from_dict({})
        assert config.debug is False
        assert config.name == "UDP Network Intelligence"

    def test_to_dict_contains_all_sections(self) -> None:
        data = AppConfig().to_dict()
        assert "network" in data
        assert "probe" in data
        assert "traceroute" in data
        assert "discovery" in data
        assert "geo" in data
        assert "ui" in data
        assert "plugins" in data
        assert "history" in data


# ---------------------------------------------------------------------------
# ConfigManager — file operations
# ---------------------------------------------------------------------------


class TestConfigManager:
    """Tests for ConfigManager lifecycle."""

    def test_first_run_creates_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        config = manager.load()
        assert config_file.exists()
        assert config.name == "UDP Network Intelligence"
        assert config.debug is False

    def test_load_existing_config(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)

        # First run creates defaults
        config = manager.load()
        config.debug = True
        manager.save(config)

        # Second run loads saved values
        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.debug is True

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)

        config = manager.load()
        config.debug = True
        config.log_level = "DEBUG"
        config.ui.theme = "light"
        config.network.socket_timeout = 5.0
        manager.save(config)

        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.debug is True
        assert config2.log_level == "DEBUG"
        assert config2.ui.theme == "light"
        assert config2.network.socket_timeout == 5.0

    def test_update_field(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        updated = manager.update(debug=True)
        assert updated.debug is True

        # Verify persisted
        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.debug is True

    def test_update_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        manager.update(ui={"theme": "light", "window_width": 1920})
        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.ui.theme == "light"
        assert config2.ui.window_width == 1920

    def test_update_invalid_field_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        with pytest.raises(KeyError, match="Unknown config field"):
            manager.update(nonexistent_field=True)

    def test_update_validation_failure(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        with pytest.raises(ValueError, match="Validation failed"):
            manager.update(network={"socket_timeout": -1})

    def test_set_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        manager.set_section("probe", {"default_count": 200})
        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.probe.default_count == 200

    def test_get_section(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        network = manager.get_section("network")
        assert isinstance(network, NetworkConfig)
        assert network.socket_timeout == 3.0

    def test_reset(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        manager.update(debug=True, ui={"theme": "light"})
        manager.reset()

        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.debug is False
        assert config2.ui.theme == "dark"

    def test_exists(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        assert manager.exists() is False
        manager.load()
        assert manager.exists() is True

    def test_config_property_raises_before_load(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        with pytest.raises(RuntimeError, match="not loaded"):
            _ = manager.config

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {{{", encoding="utf-8")
        manager = ConfigManager(config_file)
        with pytest.raises(json.JSONDecodeError):
            manager.load()


# ---------------------------------------------------------------------------
# ConfigManager — backup and restore
# ---------------------------------------------------------------------------


class TestConfigManagerBackup:
    """Tests for backup and restore functionality."""

    def test_backup_created_on_save(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        # Create initial config
        manager.update(debug=True)

        # Create another save (should backup the first)
        manager.update(debug=False)

        backups = manager.list_backups()
        assert len(backups) >= 1

    def test_backup_rotation(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        for i in range(6):
            manager.update(debug=bool(i % 2))

        backups = manager.list_backups()
        assert len(backups) <= 3  # MAX_BACKUPS

    def test_restore_from_backup(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        config = manager.load()
        config.debug = True
        manager.save(config)

        # Save again — creates backup of debug=True version
        config.debug = False
        manager.save(config)

        backups = manager.list_backups()
        assert len(backups) >= 1

        # Corrupt the config
        config_file.write_text("invalid", encoding="utf-8")

        # Restore from the backup that contains debug=True
        # backups[0] is newest (debug=True backup from save #2)
        # backups[1] is older (debug=False backup from save #1)
        restored = manager.restore(backups[0])
        assert restored.debug is True

    def test_restore_nonexistent_raises(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        manager.load()

        with pytest.raises(FileNotFoundError):
            manager.restore(tmp_path / "nonexistent.json")

    def test_list_backups_empty(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        assert manager.list_backups() == []


# ---------------------------------------------------------------------------
# ConfigManager — migrations
# ---------------------------------------------------------------------------


class TestConfigManagerMigrations:
    """Tests for configuration migration system."""

    def test_no_migration_needed(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        config = manager.load()
        assert config.config_version == CONFIG_VERSION

    def test_migration_v0_to_v1(self, tmp_path: Path) -> None:
        """Simulate loading a legacy v0 config (TOML-style with 'app' key)."""
        config_file = tmp_path / "config.json"
        legacy_data = {
            "app": {
                "name": "Old Name",
                "debug": True,
                "version": "5.0.0",
            },
            "network": {
                "socket_timeout": 10.0,
            },
        }
        config_file.write_text(json.dumps(legacy_data, indent=2), encoding="utf-8")

        manager = ConfigManager(config_file)
        config = manager.load()

        # Should be migrated
        assert config.config_version == CONFIG_VERSION
        assert config.debug is True
        assert config.network.socket_timeout == 10.0

    def test_migration_missing_sections(self, tmp_path: Path) -> None:
        """Config with only some sections should get defaults for missing."""
        config_file = tmp_path / "config.json"
        partial_data = {
            "config_version": 0,
            "debug": True,
        }
        config_file.write_text(json.dumps(partial_data, indent=2), encoding="utf-8")

        manager = ConfigManager(config_file)
        config = manager.load()

        assert config.debug is True
        assert config.ui.theme == "dark"  # default
        assert config.probe.default_count == 50  # default


# ---------------------------------------------------------------------------
# ConfigManager — version update
# ---------------------------------------------------------------------------


class TestConfigManagerVersionUpdate:
    """Tests for version update behavior."""

    def test_version_updated_on_load(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.json"
        manager = ConfigManager(config_file)
        config = manager.load()

        # Simulate old version
        data = config.to_dict()
        data["config_version"] = 0
        data["version"] = "5.0.0"
        config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        manager2 = ConfigManager(config_file)
        config2 = manager2.load()
        assert config2.config_version == CONFIG_VERSION
        assert config2.version == "6.0.0"
