"""Servers view — server list with add/delete/query."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uni.view.dialogs.add_server import AddServerDialog
from uni.view.widgets.target_input import TargetInput


class ServersView(QWidget):
    """Server list management view.

    Signals:
        add_server_requested: Emitted with (host, port, name).
        delete_server_requested: Emitted with (host, port).
        query_server_requested: Emitted with (host, port).
        refresh_requested: Emitted when refresh is clicked.
    """

    add_server_requested = Signal(str, int, str)
    delete_server_requested = Signal(str, int)
    query_server_requested = Signal(str, int)
    refresh_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        self._target_input = TargetInput(placeholder="Server to query (host:port)")
        toolbar.addWidget(self._target_input)

        self._query_btn = QPushButton("Query")
        self._query_btn.clicked.connect(self._on_query)
        toolbar.addWidget(self._query_btn)

        self._add_btn = QPushButton("Add Server")
        self._add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(self._add_btn)

        self._delete_btn = QPushButton("Delete Selected")
        self._delete_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(self._delete_btn)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        # Server table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels([
            "Host", "Port", "Name", "Map", "Game", "Players", "Last Seen"
        ])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { background-color: #1e1e2e; color: #cdd6f4; "
            "gridline-color: #313244; } "
            "QTableWidget::item:selected { background-color: #45475a; } "
            "QHeaderView::section { background-color: #181825; color: #cdd6f4; "
            "padding: 4px; border: 1px solid #313244; }"
        )
        layout.addWidget(self._table)

        # Status
        self._status_label = QLabel("No servers loaded")
        self._status_label.setStyleSheet("color: #6c7086;")
        layout.addWidget(self._status_label)

    def _on_add(self) -> None:
        dialog = AddServerDialog(self)
        dialog.server_added.connect(self.add_server_requested.emit)
        dialog.exec()

    def _on_delete(self) -> None:
        row = self._table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Delete", "Select a server first.")
            return
        host_item = self._table.item(row, 0)
        port_item = self._table.item(row, 1)
        if host_item is None or port_item is None:
            return
        host = host_item.text()
        port = int(port_item.text())
        reply = QMessageBox.question(
            self, "Delete Server",
            f"Delete {host}:{port}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.delete_server_requested.emit(host, port)

    def _on_query(self) -> None:
        target = self._target_input.get_target()
        if target:
            self.query_server_requested.emit(target[0], target[1])

    def update_servers(self, servers: list[dict[str, object]]) -> None:
        """Update the server table.

        Args:
            servers: List of server dictionaries.
        """
        self._table.setRowCount(len(servers))
        for i, srv in enumerate(servers):
            self._table.setItem(i, 0, QTableWidgetItem(str(srv.get("host", ""))))
            self._table.setItem(i, 1, QTableWidgetItem(str(srv.get("port", ""))))
            self._table.setItem(i, 2, QTableWidgetItem(str(srv.get("name", ""))))
            self._table.setItem(i, 3, QTableWidgetItem(str(srv.get("map_name", ""))))
            self._table.setItem(i, 4, QTableWidgetItem(str(srv.get("game", ""))))
            players = f"{srv.get('player_count', 0)}/{srv.get('max_players', 0)}"
            self._table.setItem(i, 5, QTableWidgetItem(players))
            self._table.setItem(i, 6, QTableWidgetItem(str(srv.get("last_seen", ""))))
        self._status_label.setText(f"{len(servers)} servers loaded")
