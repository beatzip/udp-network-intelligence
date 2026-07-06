"""Discovery ViewModel — server query operations."""

from __future__ import annotations

import logging

from PySide6.QtCore import Signal

from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class DiscoveryViewModel(BaseViewModel):
    """Manages server discovery and A2S queries.

    Signals:
        query_completed: Emitted with server info dict.
    """

    query_completed = Signal(dict)

    def __init__(self) -> None:
        super().__init__()

    async def query_server(self, host: str, port: int = 27015) -> None:
        """Query a server for info.

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
                self.query_completed.emit({
                    "host": host,
                    "port": port,
                    "name": info.name,
                    "map": info.map_name,
                    "game": info.game,
                    "players": info.player_count,
                    "max_players": info.max_players,
                    "app_id": info.app_id,
                    "rtt_ms": result.rtt_ms,
                })
            else:
                self.emit_error(f"Query failed: {result.error}")
        except Exception as exc:
            self.emit_error(f"Query error: {exc}")
