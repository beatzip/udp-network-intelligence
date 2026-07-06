"""Application lifecycle manager."""

from __future__ import annotations

import logging
from typing import Any

from uni.app.config import AppConfig, ConfigManager

logger = logging.getLogger(__name__)


class Application:
    """Top-level application lifecycle manager.

    Owns all services, starts/stops subsystems.
    """

    def __init__(self, config_path: str = "uni.toml") -> None:
        """Initialize the application.

        Args:
            config_path: Path to the JSON configuration file.
        """
        self._config_manager = ConfigManager(config_path)
        self.config: AppConfig = self._config_manager.load()
        self._running = False
        self._services: dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        """Whether the application is currently running."""
        return self._running

    async def start(self) -> None:
        """Start all application subsystems."""
        logger.info("Starting %s v%s", self.config.name, self.config.version)
        self._running = True
        logger.info("Application started")

    async def stop(self) -> None:
        """Stop all application subsystems gracefully."""
        logger.info("Stopping application...")
        self._running = False
        logger.info("Application stopped")

    def save_config(self) -> None:
        """Save current configuration to disk."""
        self._config_manager.save(self.config)

    def register_service(self, name: str, service: Any) -> None:
        """Register a named service.

        Args:
            name: Service name identifier.
            service: Service instance.
        """
        self._services[name] = service
        logger.debug("Registered service: %s", name)

    def get_service(self, name: str) -> Any:
        """Get a registered service by name.

        Args:
            name: Service name.

        Returns:
            Service instance.

        Raises:
            KeyError: If service is not registered.
        """
        if name not in self._services:
            raise KeyError(f"Service not registered: {name}")
        return self._services[name]
