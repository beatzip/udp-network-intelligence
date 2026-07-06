"""Tests for uni.services.event_bus module."""

from __future__ import annotations

import pytest

from uni.services.event_bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


class TestEventBus:
    """Tests for EventBus."""

    @pytest.mark.asyncio
    async def test_basic_emit(self, bus: EventBus) -> None:
        received: list[str] = []

        async def handler(event: str) -> None:
            received.append(event)

        bus.on("test", handler)
        await bus.emit("test")
        assert received == ["test"]

    @pytest.mark.asyncio
    async def test_multiple_handlers(self, bus: EventBus) -> None:
        results: list[int] = []

        async def handler_a(event: str) -> None:
            results.append(1)

        async def handler_b(event: str) -> None:
            results.append(2)

        bus.on("test", handler_a)
        bus.on("test", handler_b)
        await bus.emit("test")
        assert results == [1, 2]

    @pytest.mark.asyncio
    async def test_priority_ordering(self, bus: EventBus) -> None:
        results: list[str] = []

        async def low_priority(event: str) -> None:
            results.append("low")

        async def high_priority(event: str) -> None:
            results.append("high")

        bus.on("test", low_priority, priority=10)
        bus.on("test", high_priority, priority=1)
        await bus.emit("test")
        assert results == ["high", "low"]

    @pytest.mark.asyncio
    async def test_once_handler(self, bus: EventBus) -> None:
        call_count = 0

        async def handler(event: str) -> None:
            nonlocal call_count
            call_count += 1

        bus.once("test", handler)
        await bus.emit("test")
        await bus.emit("test")
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_off_removes_handler(self, bus: EventBus) -> None:
        called = False

        async def handler(event: str) -> None:
            nonlocal called
            called = True

        bus.on("test", handler)
        bus.off("test", handler)
        await bus.emit("test")
        assert called is False

    @pytest.mark.asyncio
    async def test_emit_with_kwargs(self, bus: EventBus) -> None:
        received_kwargs: dict = {}

        async def handler(event: str, **kwargs: object) -> None:
            received_kwargs.update(kwargs)

        bus.on("test", handler)
        await bus.emit("test", value=42, name="test")
        assert received_kwargs["value"] == 42
        assert received_kwargs["name"] == "test"

    @pytest.mark.asyncio
    async def test_wildcard_handler(self, bus: EventBus) -> None:
        received: list[str] = []

        async def handler(event: str) -> None:
            received.append(event)

        bus.on("*", handler)
        await bus.emit("foo")
        await bus.emit("bar")
        assert received == ["foo", "bar"]

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_others(self, bus: EventBus) -> None:
        results: list[str] = []

        async def bad_handler(event: str) -> None:
            raise ValueError("oops")

        async def good_handler(event: str) -> None:
            results.append("ok")

        bus.on("test", bad_handler)
        bus.on("test", good_handler)
        await bus.emit("test")
        assert results == ["ok"]

    def test_remove_all(self, bus: EventBus) -> None:
        async def handler(event: str) -> None:
            pass

        bus.on("test", handler)
        assert bus.handler_count == 1
        bus.remove_all()
        assert bus.handler_count == 0

    def test_handler_count(self, bus: EventBus) -> None:
        async def handler(event: str) -> None:
            pass

        bus.on("a", handler)
        bus.on("b", handler)
        assert bus.handler_count == 2
