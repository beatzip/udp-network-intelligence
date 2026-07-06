"""Source Query Protocol — unified high-level interface.

Provides :class:`SourceQuery` for performing complete A2S query
exchanges against game servers. Handles the full lifecycle:
challenge handshake, retry on failure, and structured result
assembly.

This is the primary entry point for server discovery — it wraps
the low-level :class:`~uni.protocol.a2s_protocol.A2SQueryProtocol`
with transport concerns (timeout, retry) and returns clean
dataclass results.

Example::

    query = SourceQuery(timeout=5.0)
    result = await query.query_info("1.2.3.4", 27015)
    if result.is_success:
        print(f"Server: {result.server_info.name}")
        print(f"Map: {result.server_info.map_name}")
"""

from __future__ import annotations

import asyncio
import logging
import socket
import time
from dataclasses import dataclass

from uni.core.discovery.models import (
    PlayerInfo,
    QueryResult,
    ServerRules,
)
from uni.protocol.a2s_protocol import (
    A2SQueryProtocol,
    WireRequest,
)
from uni.protocol.base import ProtocolValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Query configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class QueryConfig:
    """Configuration for a Source Query exchange.

    Attributes:
        timeout: Socket timeout in seconds.
        max_retries: Maximum number of retry attempts.
        retry_delay: Delay between retries in seconds.
        backoff: Exponential backoff multiplier.
        send_timeout: Timeout for individual send operations.
    """

    timeout: float = 5.0
    max_retries: int = 2
    retry_delay: float = 0.5
    backoff: float = 2.0
    send_timeout: float = 3.0


# ---------------------------------------------------------------------------
# Source Query implementation
# ---------------------------------------------------------------------------

class SourceQuery:
    """High-level Source Query protocol interface.

    Performs complete A2S query exchanges against game servers,
    handling challenge handshakes, retries, and transport errors.

    Attributes:
        config: Query configuration.
        protocol: Underlying A2S protocol encoder/decoder.

    Example::

        query = SourceQuery(timeout=5.0)
        result = await query.query_info("1.2.3.4", 27015)
    """

    def __init__(self, config: QueryConfig | None = None) -> None:
        """Initialize the query handler.

        Args:
            config: Query configuration. Uses defaults if None.
        """
        self.config = config or QueryConfig()
        self.protocol = A2SQueryProtocol()

    async def query_info(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
    ) -> QueryResult:
        """Query server info (A2S_INFO).

        Performs the full challenge handshake if required, retrying
        on timeout.

        Args:
            host: Server IP address or hostname.
            port: Server query port.
            timeout: Override timeout for this query.

        Returns:
            QueryResult with ServerInfo or error details.
        """
        effective_timeout = timeout or self.config.timeout
        request = self.protocol.encode_info_request()
        return await self._query(
            host, port, request, "info", effective_timeout
        )

    async def query_players(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
    ) -> list[PlayerInfo]:
        """Query server player list (A2S_PLAYER).

        Args:
            host: Server IP address.
            port: Server query port.
            timeout: Override timeout.

        Returns:
            List of PlayerInfo, or empty list on failure.
        """
        effective_timeout = timeout or self.config.timeout
        request = self.protocol.encode_player_request()
        result = await self._query(
            host, port, request, "player", effective_timeout
        )
        return result.players

    async def query_rules(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
    ) -> ServerRules:
        """Query server rules (A2S_RULES).

        Args:
            host: Server IP address.
            port: Server query port.
            timeout: Override timeout.

        Returns:
            ServerRules with parsed key-value pairs.
        """
        effective_timeout = timeout or self.config.timeout
        request = self.protocol.encode_rules_request()
        result = await self._query(
            host, port, request, "rules", effective_timeout
        )
        return result.rules or ServerRules()

    async def query_all(
        self,
        host: str,
        port: int,
        *,
        timeout: float | None = None,
    ) -> QueryResult:
        """Query all: info + players + rules.

        Performs three sequential queries and combines the results.

        Args:
            host: Server IP address.
            port: Server query port.
            timeout: Override timeout.

        Returns:
            Combined QueryResult with all data.
        """
        effective_timeout = timeout or self.config.timeout

        info_result = await self.query_info(
            host, port, timeout=effective_timeout
        )
        if not info_result.is_success:
            return info_result

        players = await self.query_players(
            host, port, timeout=effective_timeout
        )
        rules = await self.query_rules(
            host, port, timeout=effective_timeout
        )

        return QueryResult(
            host=host,
            port=port,
            server_info=info_result.server_info,
            players=players,
            rules=rules,
            rtt_ms=info_result.rtt_ms,
            error=None,
            query_time=time.time(),
        )

    # ------------------------------------------------------------------
    # Internal query engine
    # ------------------------------------------------------------------

    async def _query(
        self,
        host: str,
        port: int,
        initial_request: WireRequest,
        query_type: str,
        timeout: float,
    ) -> QueryResult:
        """Execute a single query type with challenge support and retries.

        Args:
            host: Target host.
            port: Target port.
            initial_request: First request packet.
            query_type: Query type name for logging.
            timeout: Timeout per attempt.

        Returns:
            QueryResult with parsed data.
        """
        addr = (host, port)
        current_request = initial_request
        last_error: str | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = await self._send_and_receive(
                    addr, current_request, timeout
                )
                if result is not None:
                    return self._parse_response(
                        addr, result, query_type
                    )

                last_error = "No response received"

            except TimeoutError:
                last_error = "Timeout"
                logger.debug(
                    "%s query to %s:%d attempt %d timed out",
                    query_type, host, port, attempt + 1,
                )

            except OSError as exc:
                last_error = str(exc)
                logger.debug(
                    "%s query to %s:%d failed: %s",
                    query_type, host, port, exc,
                )

            # Exponential backoff before retry
            if attempt < self.config.max_retries:
                delay = self.config.retry_delay * (
                    self.config.backoff ** attempt
                )
                await asyncio.sleep(delay)

        return QueryResult(
            host=host,
            port=port,
            rtt_ms=0.0,
            error=last_error or "Query failed",
            query_time=time.time(),
        )

    async def _send_and_receive(
        self,
        addr: tuple[str, int],
        request: WireRequest,
        timeout: float,
    ) -> bytes | None:
        """Send a request and receive a single response.

        Handles the challenge handshake: if a challenge response
        (``0x41``) is received, automatically re-sends with the
        challenge number.

        Args:
            addr: Target address.
            request: Request packet to send.
            timeout: Response timeout.

        Returns:
            Response bytes, or None on timeout.
        """
        loop = asyncio.get_running_loop()

        # Create UDP socket for this exchange
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.settimeout(timeout)

        try:
            payload = request.encode()
            sock.sendto(payload, addr)
            send_time = time.monotonic()

            # Wait for response
            try:
                data: bytes = await asyncio.wait_for(
                    loop.sock_recv(sock, 4096),
                    timeout=timeout,
                )
            except TimeoutError:
                return None

            # Handle challenge response
            if self.protocol.is_challenge_response(data):
                challenge = self.protocol.extract_challenge(data)
                if challenge < 0:
                    return None

                # Re-send with challenge
                challenge_request = WireRequest(
                    type_byte=request.type_byte,
                    challenge=challenge,
                )
                sock.sendto(challenge_request.encode(), addr)

                try:
                    data2: bytes = await asyncio.wait_for(
                        loop.sock_recv(sock, 4096),
                        timeout=timeout,
                    )
                    return data2
                except TimeoutError:
                    return None

            return data

        finally:
            sock.close()

    def _parse_response(
        self,
        addr: tuple[str, int],
        data: bytes,
        query_type: str,
    ) -> QueryResult:
        """Parse a response into a QueryResult.

        Args:
            addr: Source address of the response.
            data: Raw response bytes.
            query_type: Query type for result assembly.

        Returns:
            QueryResult with parsed data.
        """
        try:
            self.protocol.decode_response(data)

            if query_type == "info":
                server_info = self.protocol.decode_info_response(data)
                return QueryResult(
                    host=addr[0],
                    port=addr[1],
                    server_info=server_info,
                    rtt_ms=0.0,
                    query_time=time.time(),
                )

            if query_type == "player":
                players = self.protocol.decode_player_response(data)
                return QueryResult(
                    host=addr[0],
                    port=addr[1],
                    players=players,
                    rtt_ms=0.0,
                    query_time=time.time(),
                )

            if query_type == "rules":
                rules = self.protocol.decode_rules_response(data)
                return QueryResult(
                    host=addr[0],
                    port=addr[1],
                    rules=rules,
                    rtt_ms=0.0,
                    query_time=time.time(),
                )

            return QueryResult(
                host=addr[0],
                port=addr[1],
                error=f"Unknown query type: {query_type}",
                query_time=time.time(),
            )

        except ProtocolValidationError as exc:
            return QueryResult(
                host=addr[0],
                port=addr[1],
                error=f"Parse error: {exc}",
                query_time=time.time(),
            )
