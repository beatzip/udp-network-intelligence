"""Analysis View — historical analysis and quality reports."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)


class AnalysisView(QWidget):
    """Historical analysis view placeholder.

    Signals:
        refresh_requested: Emitted when refresh is clicked.
    """

    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        label = QLabel("Analysis — Coming Soon")
        label.setStyleSheet("color: #6c7086; font-size: 14px;")
        layout.addWidget(label)
        layout.addStretch()
