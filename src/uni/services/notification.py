"""Notification service — toast notifications (stub for Phase 5+)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class NotificationService:
    """System notification service.

    Will integrate with Qt system tray in Phase 5.
    """

    def show(self, title: str, message: str, *, level: str = "info") -> None:
        """Show a notification.

        Args:
            title: Notification title.
            message: Notification body.
            level: Notification level (info, warning, error).
        """
        level_map = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
        }
        logger.log(
            level_map.get(level, logging.INFO),
            "[%s] %s: %s",
            level.upper(),
            title,
            message,
        )
