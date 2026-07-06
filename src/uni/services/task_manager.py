"""Task manager — manage async background tasks."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ManagedTask:
    """Wrapper around an asyncio Task with metadata."""

    name: str
    task: asyncio.Task[Any]


class TaskManager:
    """Track and manage background asyncio tasks.

    Ensures clean shutdown by cancelling all tasks.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ManagedTask] = {}

    def create(
        self,
        name: str,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task[Any]:
        """Create and track a named background task.

        Args:
            name: Unique task name.
            coro: Coroutine to run.

        Returns:
            The asyncio Task.

        Raises:
            RuntimeError: If a task with the same name already exists.
        """
        if name in self._tasks:
            raise RuntimeError(f"Task already exists: {name}")

        loop = asyncio.get_running_loop()
        task = loop.create_task(coro, name=name)
        self._tasks[name] = ManagedTask(name=name, task=task)
        logger.debug("Created task: %s", name)
        return task

    def cancel(self, name: str) -> bool:
        """Cancel a named task.

        Args:
            name: Task name.

        Returns:
            True if the task was found and cancelled.
        """
        managed = self._tasks.pop(name, None)
        if managed is None:
            return False
        managed.task.cancel()
        logger.debug("Cancelled task: %s", name)
        return True

    async def cancel_all(self) -> None:
        """Cancel all tracked tasks and wait for them to finish."""
        names = list(self._tasks.keys())
        for name in names:
            self.cancel(name)

        # Wait for all cancelled tasks to complete
        tasks = [mt.task for mt in self._tasks.values()]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        logger.debug("All tasks cancelled")

    @property
    def active_count(self) -> int:
        """Number of active (non-done) tasks."""
        return sum(1 for mt in self._tasks.values() if not mt.task.done())

    @property
    def task_names(self) -> list[str]:
        """Names of all tracked tasks."""
        return list(self._tasks.keys())
