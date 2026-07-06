"""Settings ViewModel — bridges config read/write to SettingsView."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Signal

from uni.app.config import AppConfig
from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class SettingsViewModel(BaseViewModel):
    """Manages application settings with change notifications.

    Signals:
        settings_changed: Emitted when any setting changes.
        theme_changed: Emitted with theme name.
    """

    settings_changed = Signal(str, object)  # key, value
    theme_changed = Signal(str)

    def __init__(self, config: AppConfig | None = None) -> None:
        super().__init__()
        self._config = config or AppConfig()

    def get_config(self) -> AppConfig:
        """Get the current configuration."""
        return self._config

    def get(self, section: str, key: str, default: Any = None) -> Any:
        """Get a config value.

        Args:
            section: Config section (e.g., 'network', 'probe').
            key: Setting key within the section.
            default: Default value if not found.

        Returns:
            Setting value.
        """
        section_obj = getattr(self._config, section, None)
        if section_obj is None:
            return default
        return getattr(section_obj, key, default)

    def set(self, section: str, key: str, value: Any) -> None:
        """Set a config value.

        Args:
            section: Config section.
            key: Setting key.
            value: New value.
        """
        section_obj = getattr(self._config, section, None)
        if section_obj is None:
            return
        setattr(section_obj, key, value)
        self.settings_changed.emit(f"{section}.{key}", value)
        logger.debug("Setting changed: %s.%s = %r", section, key, value)

    def set_theme(self, theme: str) -> None:
        """Change the application theme.

        Args:
            theme: Theme name ('dark' or 'light').
        """
        self._config.ui.theme = theme
        self.theme_changed.emit(theme)
        self.settings_changed.emit("ui.theme", theme)

    def get_all_settings(self) -> dict[str, Any]:
        """Get all settings as a nested dictionary."""
        return self._config.to_dict()
