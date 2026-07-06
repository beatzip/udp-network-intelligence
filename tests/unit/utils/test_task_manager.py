"""Tests for uni.services.task_manager module."""

from __future__ import annotations

import asyncio

import pytest

from uni.services.task_manager import TaskManager


@pytest.fixture
def manager() -> TaskManager:
    return TaskManager()


class TestTaskManager:
    """Tests for TaskManager."""

    @pytest.mark.asyncio
    async def test_create_task(self, manager: TaskManager) -> None:
        async def work() -> None:
            await asyncio.sleep(0.1)

        task = manager.create("test-task", work())
        assert "test-task" in manager.task_names
        assert manager.active_count >= 1
        await task

    @pytest.mark.asyncio
    async def test_duplicate_name_raises(self, manager: TaskManager) -> None:
        async def work() -> None:
            await asyncio.sleep(10)

        manager.create("dup", work())
        with pytest.raises(RuntimeError, match="Task already exists"):
            manager.create("dup", work())
        manager.cancel("dup")

    @pytest.mark.asyncio
    async def test_cancel_task(self, manager: TaskManager) -> None:
        async def long_work() -> None:
            await asyncio.sleep(10)

        manager.create("cancel-me", long_work())
        assert manager.cancel("cancel-me") is True
        assert "cancel-me" not in manager.task_names

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, manager: TaskManager) -> None:
        assert manager.cancel("nope") is False

    @pytest.mark.asyncio
    async def test_cancel_all(self, manager: TaskManager) -> None:
        async def work() -> None:
            await asyncio.sleep(10)

        manager.create("a", work())
        manager.create("b", work())
        await manager.cancel_all()
        assert manager.active_count == 0
