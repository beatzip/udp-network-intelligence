"""Theme manager — load and apply QSS stylesheets."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

_STYLES_DIR = Path(__file__).parent.parent / "resources" / "styles"


class ThemeManager:
    """Manages application theme (dark/light QSS).

    Example::

        theme = ThemeManager()
        theme.apply("dark")
    """

    def __init__(self) -> None:
        self._current_theme = "dark"

    def apply(self, theme: str = "dark") -> None:
        """Apply a theme to the application.

        Args:
            theme: Theme name ('dark' or 'light').
        """
        qss_file = _STYLES_DIR / f"{theme}.qss"
        if qss_file.exists():
            qss = qss_file.read_text(encoding="utf-8")
            app = QApplication.instance()
            if app is not None:
                cast("QApplication", app).setStyleSheet(qss)
            self._current_theme = theme
            logger.info("Theme applied: %s", theme)
        else:
            logger.warning("Theme file not found: %s", qss_file)

    @property
    def current_theme(self) -> str:
        """Current theme name."""
        return self._current_theme
