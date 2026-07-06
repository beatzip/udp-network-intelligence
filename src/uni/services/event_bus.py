"""Event bus — async pub/sub for decoupled module communication."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for async event handlers
EventHandler = Callable[..., Coroutine[Any, Any, None]]


@dataclass
class _Subscription:
    """Internal subscription record."""
    handler: EventHandler
    priority: int = 0
    once: bool = False


class EventBus:
    """Async event bus for decoupled inter-module communication.

    Supports:
    - Multiple handlers per event
    - Priority ordering
    - One-shot handlers
    - Wildcard subscriptions
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[_Subscription]] = defaultdict(list)

    def on(
        self,
        event: str,
        handler: EventHandler,
        *,
        priority: int = 0,
    ) -> None:
        """Register a handler for an event.

        Args:
            event: Event name.
            handler: Async callable to invoke.
            priority: Lower values run first.
        """
        sub = _Subscription(handler=handler, priority=priority)
        self._handlers[event].append(sub)
        self._handlers[event].sort(key=lambda s: s.priority)
        logger.debug(
            "Subscribed to '%s': %s (priority=%d)",
            event, handler.__qualname__, priority,
        )

    def once(
        self,
        event: str,
        handler: EventHandler,
        *,
        priority: int = 0,
    ) -> None:
        """Register a one-shot handler (auto-removes after first call).

        Args:
            event: Event name.
            handler: Async callable to invoke once.
            priority: Lower values run first.
        """
        sub = _Subscription(handler=handler, priority=priority, once=True)
        self._handlers[event].append(sub)
        self._handlers[event].sort(key=lambda s: s.priority)

    def off(self, event: str, handler: EventHandler) -> None:
        """Remove a handler from an event.

        Args:
            event: Event name.
            handler: Handler to remove.
        """
        subs = self._handlers.get(event, [])
        self._handlers[event] = [s for s in subs if s.handler is not handler]

    async def emit(self, event: str, **kwargs: Any) -> None:
        """Emit an event to all registered handlers.

        Args:
            event: Event name.
            **kwargs: Event data passed to handlers.
        """
        subs = list(self._handlers.get(event, []))
        wildcard_subs = list(self._handlers.get("*", []))

        to_remove: list[tuple[str, _Subscription]] = []

        for sub in subs + wildcard_subs:
            try:
                await sub.handler(event, **kwargs)
            except Exception:
                logger.exception(
                    "Handler error for event '%s': %s",
                    event, sub.handler.__qualname__,
                )
            if sub.once:
                to_remove.append((event, sub))

        for evt, sub in to_remove:
            if sub in self._handlers.get(evt, []):
                self._handlers[evt].remove(sub)

    def remove_all(self) -> None:
        """Remove all handlers (useful for cleanup)."""
        self._handlers.clear()

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers."""
        return sum(len(subs) for subs in self._handlers.values())
