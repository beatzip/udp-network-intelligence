"""Async helpers — gather_with_limit, retry, cancel_on_timeout."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def gather_with_limit(
    *coros: Awaitable[Any],
    limit: int = 10,
) -> list[Any]:
    """Run coroutines with a concurrency limit.

    Args:
        *coros: Coroutines to run.
        limit: Maximum concurrent tasks.

    Returns:
        List of results in order.
    """
    semaphore = asyncio.Semaphore(limit)

    async def _limited(coro: Awaitable[Any]) -> Any:
        async with semaphore:
            return await coro

    return list(await asyncio.gather(*[_limited(c) for c in coros]))


async def retry(
    coro_fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    **kwargs: Any,
) -> T:
    """Retry a coroutine with exponential backoff.

    Args:
        coro_fn: Async callable to retry.
        *args: Positional arguments.
        max_attempts: Maximum number of attempts.
        delay: Initial delay between attempts (seconds).
        backoff: Backoff multiplier.
        exceptions: Tuple of exceptions to catch and retry.
        **kwargs: Keyword arguments.

    Returns:
        Result of the coroutine.

    Raises:
        The last exception if all attempts fail.
    """
    last_exc: Exception | None = None
    current_delay = delay

    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn(*args, **kwargs)
        except exceptions as exc:
            last_exc = exc
            if attempt < max_attempts:
                logger.debug(
                    "Retry %d/%d after %.1fs: %s",
                    attempt,
                    max_attempts,
                    current_delay,
                    exc,
                )
                await asyncio.sleep(current_delay)
                current_delay *= backoff

    raise last_exc  # type: ignore[misc]


async def cancel_on_timeout(
    coro: Awaitable[T],
    timeout: float,
) -> T:
    """Run a coroutine with a timeout, cancelling on expiry.

    Args:
        coro: Coroutine to run.
        timeout: Timeout in seconds.

    Returns:
        Result of the coroutine.

    Raises:
        asyncio.TimeoutError: If the coroutine times out.
    """
    return await asyncio.wait_for(coro, timeout=timeout)


async def safe_await(coro: Awaitable[Any], default: Any = None) -> Any:
    """Await a coroutine, returning a default on exception.

    Args:
        coro: Coroutine to await.
        default: Value to return on exception.

    Returns:
        Coroutine result or default.
    """
    try:
        return await coro
    except Exception:
        logger.debug("safe_await caught exception", exc_info=True)
        return default
