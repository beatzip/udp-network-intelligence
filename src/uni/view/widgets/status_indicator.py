"""Status indicator widget — colored dot showing connection state."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusIndicator(QWidget):
    """Colored status dot with optional label.

    Colors:
    - Green: connected/ok
    - Yellow: warning/loading
    - Red: error/disconnected
    - Gray: idle/unknown
    """

    def __init__(self, parent: QWidget | None = None, label: str = "") -> None:
        super().__init__(parent)
        self._color = QColor("#6c7086")  # gray default
        self._size = 10

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._dot = QLabel()
        self._dot.setFixedSize(self._size + 2, self._size + 2)
        self._label = QLabel(label)

        layout.addWidget(self._dot)
        layout.addWidget(self._label)
        layout.addStretch()

        self._update_dot()

    def _update_dot(self) -> None:
        """Repaint the status dot."""
        from PySide6.QtGui import QPixmap

        pixmap = QPixmap(self._size, self._size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(0, 0, self._size, self._size)
        painter.end()
        self._dot.setPixmap(pixmap)

    def set_status(self, status: str) -> None:
        """Set the status indicator color.

        Args:
            status: One of 'ok', 'warning', 'error', 'idle'.
        """
        color_map = {
            "ok": QColor("#4ade80"),
            "warning": QColor("#facc15"),
            "error": QColor("#f87171"),
            "idle": QColor("#6c7086"),
            "loading": QColor("#60a5fa"),
        }
        self._color = color_map.get(status, QColor("#6c7086"))
        self._update_dot()

    def set_label(self, text: str) -> None:
        """Update the label text."""
        self._label.setText(text)
