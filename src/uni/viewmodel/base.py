"""Base ViewModel — common signal definitions and async task management.

Provides the base class for all ViewModels with PySide6 signal support,
async task lifecycle management, and thread-safe property updates.
"""

from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class BaseViewModel(QObject):
    """Base class for all ViewModels.

    Provides:
    - Qt signal definitions for common events
    - Async task management (start, cancel)
    - Thread-safe property change notifications
    - Error handling with signal emission

    Example::

        class ProbeViewModel(BaseViewModel):
            progress_updated = Signal(int, int)  # current, total
            probe_completed = Signal(dict)

            def start_probe(self, target: str) -> None:
                self.run_async(self._do_probe(target))
    """

    # Common signals
    error_occurred = Signal(str)           # error message
    status_changed = Signal(str)          # status text
    loading_changed = Signal(bool)        # loading state
    data_changed = Signal()               # generic data refresh trigger

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize the ViewModel.

        Args:
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._tasks: list[asyncio.Task[Any]] = []
        self._is_loading = False

    @property
    def is_loading(self) -> bool:
        """Whether the ViewModel is performing an async operation."""
        return self._is_loading

    def run_async(self, coro: Any, name: str = "") -> asyncio.Task[Any]:
        """Schedule an async coroutine as a background task.

        The task is tracked and cancelled on shutdown. Errors are
        caught and emitted via error_occurred signal.

        Args:
            coro: Coroutine to run.
            name: Task name for debugging.

        Returns:
            The asyncio Task.
        """
        task = asyncio.ensure_future(self._safe_coro(coro, name))
        self._tasks.append(task)
        task.add_done_callback(lambda t: self._on_task_done(t, name))
        return task

    async def _safe_coro(self, coro: Any, name: str) -> Any:
        """Wrapper that catches exceptions from a coroutine."""
        try:
            self._set_loading(True)
            return await coro
        except Exception as exc:
            msg = f"Task error ({name}): {exc}"
            logger.error(msg)
            logger.debug(traceback.format_exc())
            self.error_occurred.emit(msg)
            return None
        finally:
            self._set_loading(False)

    def _on_task_done(self, task: asyncio.Task[Any], name: str) -> None:
        """Callback when a task completes."""
        if task in self._tasks:
            self._tasks.remove(task)
        if task.cancelled():
            logger.debug("Task cancelled: %s", name)
        elif task.exception():
            logger.error("Task failed: %s — %s", name, task.exception())

    def _set_loading(self, loading: bool) -> None:
        """Thread-safe loading state update."""
        if self._is_loading != loading:
            self._is_loading = loading
            self.loading_changed.emit(loading)

    def cancel_all(self) -> None:
        """Cancel all running async tasks."""
        for task in self._tasks:
            if not task.done():
                task.cancel()
        self._tasks.clear()

    def emit_error(self, message: str) -> None:
        """Emit an error signal.

        Args:
            message: Error description.
        """
        logger.warning("ViewModel error: %s", message)
        self.error_occurred.emit(message)

    def emit_status(self, message: str) -> None:
        """Emit a status change signal.

        Args:
            message: Status text.
        """
        self.status_changed.emit(message)
