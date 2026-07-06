"""Discovery View — server query and info display."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uni.view.widgets.target_input import TargetInput


class DiscoveryView(QWidget):
    """Server discovery and A2S query view.

    Signals:
        query_requested: Emitted with (host, port).
    """

    query_requested = Signal(str, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Target input
        input_layout = QHBoxLayout()
        self._target_input = TargetInput(placeholder="Server to query (host:port)")
        input_layout.addWidget(self._target_input)

        self._query_btn = QPushButton("Query Server")
        self._query_btn.clicked.connect(self._on_query)
        input_layout.addWidget(self._query_btn)
        layout.addLayout(input_layout)

        # Server info group
        info_group = QGroupBox("Server Information")
        info_layout = QVBoxLayout()

        self._info_table = QTableWidget()
        self._info_table.setColumnCount(2)
        self._info_table.setHorizontalHeaderLabels(["Property", "Value"])
        self._info_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._info_table.setAlternatingRowColors(True)
        self._info_table.setStyleSheet(
            "QTableWidget { background-color: #1e1e2e; color: #cdd6f4; "
            "gridline-color: #313244; } "
            "QHeaderView::section { background-color: #181825; color: #cdd6f4; "
            "padding: 4px; border: 1px solid #313244; }"
        )
        info_layout.addWidget(self._info_table)
        info_group.setLayout(info_layout)
        layout.addWidget(info_group)

        # Status
        self._status = QLabel("Enter a server address and click Query")
        self._status.setStyleSheet("color: #6c7086;")
        layout.addWidget(self._status)

    def _on_query(self) -> None:
        target = self._target_input.get_target()
        if target:
            self._query_btn.setEnabled(False)
            self._status.setText("Querying...")
            self._status.setStyleSheet("color: #facc15;")
            self.query_requested.emit(target[0], target[1])

    def display_result(self, result: dict) -> None:
        """Display query result.

        Args:
            result: Server info dictionary.
        """
        self._query_btn.setEnabled(True)

        properties = [
            ("Name", result.get("name", "")),
            ("Host", f"{result.get('host', '')}:{result.get('port', '')}"),
            ("Map", result.get("map", "")),
            ("Game", result.get("game", "")),
            ("Players", f"{result.get('players', 0)}/{result.get('max_players', 0)}"),
            ("App ID", str(result.get("app_id", ""))),
            ("RTT", f"{result.get('rtt_ms', 0):.1f} ms"),
        ]

        self._info_table.setRowCount(len(properties))
        for i, (prop, val) in enumerate(properties):
            self._info_table.setItem(i, 0, QTableWidgetItem(prop))
            self._info_table.setItem(i, 1, QTableWidgetItem(str(val)))

        self._status.setText("Query successful")
        self._status.setStyleSheet("color: #4ade80;")

    def on_error(self, message: str) -> None:
        """Called on query error."""
        self._query_btn.setEnabled(True)
        self._status.setText(f"Error: {message}")
        self._status.setStyleSheet("color: #f87171;")
