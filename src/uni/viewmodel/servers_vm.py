"""Servers ViewModel — manages server list, add/delete, query."""

from __future__ import annotations

import logging
import time
from typing import Any

from PySide6.QtCore import Signal

from uni.core.history.repository import HistoryRepository, ServerRecord
from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class ServersViewModel(BaseViewModel):
    """Manages the server list with add/delete/query operations.

    Signals:
        servers_updated: Emitted when the server list changes.
        server_queried: Emitted when a server query completes.
        query_progress: Emitted during batch queries.
    """

    servers_updated = Signal(list)  # list of server dicts
    server_queried = Signal(dict)  # query result dict
    query_progress = Signal(int, int)  # current, total
    query_complete = Signal(list)  # all results

    def __init__(self, repo: HistoryRepository | None = None) -> None:
        super().__init__()
        self._repo = repo
        self._servers: list[ServerRecord] = []

    def set_repository(self, repo: HistoryRepository) -> None:
        """Set the history repository.

        Args:
            repo: Initialized HistoryRepository.
        """
        self._repo = repo

    async def load_servers(self) -> None:
        """Load servers from the database."""
        if self._repo is None:
            return
        self._servers = await self._repo.get_servers(limit=500)
        self._emit_servers()

    async def add_server(self, host: str, port: int = 27015, name: str = "") -> None:
        """Add a server to the database.

        Args:
            host: Server host.
            port: Server port.
            name: Optional server name.
        """
        if self._repo is None:
            return
        record = ServerRecord(
            host=host,
            port=port,
            name=name,
            first_seen=time.time(),
            last_seen=time.time(),
        )
        await self._repo.save_server(record)
        await self.load_servers()
        self.emit_status(f"Added server {host}:{port}")

    async def delete_server(self, host: str, port: int) -> None:
        """Remove a server from the database.

        Args:
            host: Server host.
            port: Server port.
        """
        if self._repo is None:
            return
        await self._repo.delete_server(host, port)
        await self.load_servers()
        self.emit_status(f"Removed server {host}:{port}")

    async def query_server(self, host: str, port: int = 27015) -> None:
        """Query a server for live info.

        Args:
            host: Server host.
            port: Server port.
        """
        from uni.protocol.source_query import SourceQuery

        query = SourceQuery()
        try:
            result = await query.query_info(host, port)
            if result.is_success and result.server_info:
                info = result.server_info
                # Update in database
                if self._repo:
                    record = ServerRecord(
                        host=host,
                        port=port,
                        name=info.name,
                        map_name=info.map_name,
                        game=info.game,
                        app_id=info.app_id,
                        player_count=info.player_count,
                        max_players=info.max_players,
                        version=info.version,
                    )
                    await self._repo.save_server(record)

                self.server_queried.emit(
                    {
                        "host": host,
                        "port": port,
                        "name": info.name,
                        "map": info.map_name,
                        "game": info.game,
                        "players": info.player_count,
                        "max_players": info.max_players,
                        "app_id": info.app_id,
                        "rtt_ms": result.rtt_ms,
                    }
                )
            else:
                self.emit_error(f"Query failed: {result.error}")
        except Exception as exc:
            self.emit_error(f"Query error: {exc}")

    def get_servers(self) -> list[dict[str, Any]]:
        """Get the current server list as dictionaries."""
        return [s.to_dict() for s in self._servers]

    def _emit_servers(self) -> None:
        """Emit the current server list."""
        self.servers_updated.emit(self.get_servers())
