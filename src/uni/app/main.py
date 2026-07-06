"""Entry point — asyncio.run(), application init."""

from __future__ import annotations

import asyncio
import logging
import sys

from uni.app.application import Application
from uni.services.logger import setup_logging


def main() -> None:
    """Application entry point."""
    setup_logging(level=logging.INFO)
    logger = logging.getLogger(__name__)
    logger.info("UDP Network Intelligence v6 starting")

    app = Application()

    try:
        asyncio.run(_async_main(app))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


async def _async_main(app: Application) -> None:
    """Async main loop."""
    await app.start()
    try:
        # Application runs here — GUI event loop will be integrated in Phase 5
        await asyncio.Event().wait()  # Block until interrupted
    finally:
        await app.stop()


if __name__ == "__main__":
    main()
