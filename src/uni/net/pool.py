"""Socket pool for reusable socket allocation.

Provides :class:`SocketPool` for managing a pool of pre-allocated
UDP sockets. Limits concurrent socket usage, reuses sockets when
possible, and provides automatic cleanup.

Example::

    pool = SocketPool(max_size=32)
    async with pool:
        sock = await pool.acquire()
        try:
            info = await sock.send_receive(data, addr)
        finally:
            await pool.release(sock)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from uni.net.models import SocketConfig
from uni.net.udp_socket import AsyncUDPSocket

logger = logging.getLogger(__name__)


class SocketPool:
    """Pool of reusable AsyncUDPSocket instances.

    Manages socket lifecycle, limits concurrent usage, and provides
    acquire/release semantics for controlled socket access.

    Attributes:
        max_size: Maximum number of sockets in the pool.
        active_count: Number of currently checked-out sockets.
        idle_count: Number of available sockets in the pool.

    Example::

        pool = SocketPool(max_size=16)
        async with pool:
            sock = await pool.acquire()
            try:
                await sock.send_receive(data, addr)
            finally:
                await pool.release(sock)
    """

    def __init__(self, max_size: int = 32) -> None:
        """Initialize the socket pool.

        Args:
            max_size: Maximum number of sockets.
        """
        if max_size < 1:
            raise ValueError(f"max_size must be >= 1, got {max_size}")
        self.max_size = max_size
        self._idle: asyncio.Queue[AsyncUDPSocket] = asyncio.Queue()
        self._all_sockets: list[AsyncUDPSocket] = []
        self._active = 0
        self._lock = asyncio.Lock()
        self._is_open = False

    @property
    def active_count(self) -> int:
        """Number of sockets currently checked out."""
        return self._active

    @property
    def idle_count(self) -> int:
        """Number of sockets available in the pool."""
        return self._idle.qsize()

    @property
    def total_count(self) -> int:
        """Total number of sockets created."""
        return len(self._all_sockets)

    async def open(self) -> None:
        """Open the pool.

        Does not pre-create sockets — they are created on demand.
        """
        self._is_open = True
        logger.debug("Socket pool opened (max_size=%d)", self.max_size)

    async def close(self) -> None:
        """Close all sockets in the pool."""
        self._is_open = False
        async with self._lock:
            while not self._idle.empty():
                try:
                    sock = self._idle.get_nowait()
                    await sock.close()
                except asyncio.QueueEmpty:
                    break
            for sock in self._all_sockets:
                try:
                    await sock.close()
                except Exception:
                    pass
            self._all_sockets.clear()
            self._active = 0
        logger.debug("Socket pool closed")

    async def __aenter__(self) -> SocketPool:
        """Async context manager entry."""
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.close()

    async def acquire(
        self,
        config: SocketConfig | None = None,
    ) -> AsyncUDPSocket:
        """Acquire a socket from the pool.

        Returns an idle socket if available, or creates a new one
        if the pool limit has not been reached.

        Args:
            config: Optional socket configuration. Uses defaults if None.

        Returns:
            An AsyncUDPSocket ready for use.

        Raises:
            RuntimeError: If the pool is at capacity and no sockets
                are available.
        """
        if not self._is_open:
            raise RuntimeError("Socket pool is not open")

        # Try to get an idle socket
        async with self._lock:
            if not self._idle.empty():
                sock = self._idle.get_nowait()
                self._active += 1
                logger.debug("Reusing socket from pool (idle=%d)", self.idle_count)
                return sock

            # Create new socket if under limit
            if len(self._all_sockets) < self.max_size:
                sock = AsyncUDPSocket(config or SocketConfig())
                await sock.open()
                self._all_sockets.append(sock)
                self._active += 1
                logger.debug(
                    "Created new socket (total=%d, active=%d)",
                    self.total_count,
                    self.active_count,
                )
                return sock

        # Pool is full — wait for a socket to be returned
        logger.debug("Pool at capacity, waiting for socket release")
        sock = await self._idle.get()
        self._active += 1
        return sock

    async def release(self, sock: AsyncUDPSocket) -> None:
        """Return a socket to the pool.

        Resets the socket statistics before returning to the pool.

        Args:
            sock: The socket to release.
        """
        async with self._lock:
            self._active = max(0, self._active - 1)

            if sock in self._all_sockets:
                sock.reset_statistics()
                self._idle.put_nowait(sock)
                logger.debug(
                    "Socket returned to pool (idle=%d, active=%d)",
                    self.idle_count,
                    self.active_count,
                )
            else:
                await sock.close()
                logger.debug("Unknown socket closed (not in pool)")

    async def release_all(self) -> None:
        """Release all checked-out sockets back to the pool.

        This is a best-effort operation — it resets the active count
        but cannot force-return sockets that are in use.
        """
        async with self._lock:
            self._active = 0
        logger.debug("Released all sockets (active count reset to 0)")
