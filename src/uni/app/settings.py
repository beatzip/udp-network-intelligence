"""Runtime settings — user preferences with change notifications."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SettingsManager:
    """Runtime settings with observer pattern for change notifications."""

    _observers: dict[str, list[Callable[[str, Any, Any], None]]] = field(
        default_factory=dict, repr=False
    )
    _values: dict[str, Any] = field(default_factory=dict, repr=False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by dot-separated key."""
        return self._values.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and notify observers.

        Args:
            key: Dot-separated setting key.
            value: New value.
        """
        old = self._values.get(key)
        self._values[key] = value
        if old != value:
            logger.debug("Setting changed: %s = %r (was %r)", key, value, old)
            self._notify(key, old, value)

    def subscribe(self, key: str, callback: Callable[[str, Any, Any], None]) -> None:
        """Subscribe to changes for a setting key.

        Args:
            key: Setting key to watch (prefix match).
            callback: Called with (key, old_value, new_value).
        """
        self._observers.setdefault(key, []).append(callback)

    def unsubscribe(self, key: str, callback: Callable[[str, Any, Any], None]) -> None:
        """Unsubscribe from a setting key."""
        observers = self._observers.get(key, [])
        if callback in observers:
            observers.remove(callback)

    def _notify(self, key: str, old: Any, new: Any) -> None:
        """Notify all observers of a setting change."""
        for watched_key, callbacks in self._observers.items():
            if key.startswith(watched_key):
                for cb in callbacks:
                    try:
                        cb(key, old, new)
                    except Exception:
                        logger.exception("Observer error for key %s", key)

    def as_dict(self) -> dict[str, Any]:
        """Return all settings as a flat dictionary."""
        return dict(self._values)
