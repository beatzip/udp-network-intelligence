"""Log console widget — embedded log viewer with level filtering."""

from __future__ import annotations

import logging

from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogConsole(QWidget):
    """Embedded log viewer with level filtering.

    Captures log records and displays them in a scrollable text area
    with colored level indicators.
    """

    _LEVEL_COLORS = {
        logging.DEBUG: QColor("#6c7086"),
        logging.INFO: QColor("#4ade80"),
        logging.WARNING: QColor("#facc15"),
        logging.ERROR: QColor("#f87171"),
        logging.CRITICAL: QColor("#ef4444"),
    }

    _LEVEL_NAMES = {
        10: "DEBUG",
        20: "INFO",
        30: "WARN",
        40: "ERROR",
        50: "CRIT",
    }

    def __init__(self, parent: QWidget | None = None, max_lines: int = 1000) -> None:
        super().__init__(parent)
        self._max_lines = max_lines
        self._min_level = logging.INFO
        self._handler: _QtLogHandler | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Filter bar
        filter_layout = QHBoxLayout()
        filter_layout.setContentsMargins(0, 0, 0, 0)

        self._chk_debug = QCheckBox("DEBUG")
        self._chk_info = QCheckBox("INFO")
        self._chk_warning = QCheckBox("WARN")
        self._chk_error = QCheckBox("ERROR")

        self._chk_info.setChecked(True)

        for chk in (self._chk_debug, self._chk_info, self._chk_warning, self._chk_error):
            chk.stateChanged.connect(self._on_filter_changed)
            filter_layout.addWidget(chk)

        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setStyleSheet(
            "QTextEdit { background-color: #1e1e2e; color: #cdd6f4; "
            "border: 1px solid #313244; }"
        )
        layout.addWidget(self._text)

        self._setup_handler()

    def _setup_handler(self) -> None:
        """Install a log handler that captures to this widget."""
        self._handler = _QtLogHandler(self)
        self._handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-5s | %(name)s | %(message)s",
                              datefmt="%H:%M:%S")
        )
        logging.getLogger().addHandler(self._handler)

    def _on_filter_changed(self) -> None:
        """Recalculate minimum log level from checkboxes."""
        level = logging.WARNING
        if self._chk_debug.isChecked():
            level = logging.DEBUG
        elif self._chk_info.isChecked():
            level = logging.INFO
        elif self._chk_warning.isChecked():
            level = logging.WARNING
        self._min_level = level

    def append_log(self, record: logging.LogRecord) -> None:
        """Append a log record to the console.

        Args:
            record: Log record to display.
        """
        if record.levelno < self._min_level:
            return

        level_name = self._LEVEL_NAMES.get(record.levelno, "?")
        color = self._LEVEL_COLORS.get(record.levelno, QColor("#cdd6f4"))

        import datetime as dt
        time_str = dt.datetime.fromtimestamp(
            record.created, tz=dt.UTC
        ).strftime("%H:%M:%S")
        line = f"{time_str} | {level_name:<5} | {record.name} | {record.getMessage()}\n"

        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text.setTextCursor(cursor)

        fmt = QTextCharFormat()
        fmt.setForeground(color)
        cursor.insertText(line, fmt)

        # Trim old lines
        if self._text.document().blockCount() > self._max_lines:
            cursor.movePosition(QTextCursor.MoveOperation.Start)
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()

        # Auto-scroll
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def clear(self) -> None:
        """Clear all log text."""
        self._text.clear()

    def set_level(self, level: int) -> None:
        """Set the minimum log level.

        Args:
            level: Logging level constant.
        """
        self._min_level = level


class _QtLogHandler(logging.Handler):
    """Log handler that forwards records to a LogConsole widget."""

    def __init__(self, console: LogConsole) -> None:
        super().__init__()
        self._console = console

    def emit(self, record: logging.LogRecord) -> None:
        """Forward the record to the console widget.

        Args:
            record: Log record.
        """
        try:
            self._console.append_log(record)
        except Exception:
            pass
