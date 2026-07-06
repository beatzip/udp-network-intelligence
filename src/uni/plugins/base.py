"""Stub: PluginBase — abstract base class for plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from uni.app.constants import PluginState


@dataclass
class PluginMeta:
    """Plugin metadata."""

    name: str = ""
    version: str = "0.1.0"
    author: str = ""
    description: str = ""


class PluginBase(ABC):
    """Abstract base class for all plugins."""

    @property
    @abstractmethod
    def meta(self) -> PluginMeta:
        """Plugin metadata."""

    @property
    def state(self) -> PluginState:
        """Current plugin state."""
        return PluginState.DISCOVERED

    async def on_load(self) -> None:
        """Called when the plugin is loaded."""

    async def on_unload(self) -> None:
        """Called when the plugin is unloaded."""
