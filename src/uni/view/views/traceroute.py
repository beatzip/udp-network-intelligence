"""Traceroute View — UDP traceroute with hop visualization."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from uni.view.widgets.target_input import TargetInput


class TracerouteView(QWidget):
    """UDP traceroute view with hop table.

    Signals:
        traceroute_requested: Emitted with (host, port).
        stop_requested: Emitted when stop is clicked.
    """

    traceroute_requested = Signal(str, int)
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Target input
        self._target_input = TargetInput(placeholder="Target for traceroute (host:port)")

        # Buttons
        btn_layout = __import__("PySide6.QtWidgets", fromlist=["QHBoxLayout"]).QHBoxLayout()
        self._trace_btn = QPushButton("Trace")
        self._trace_btn.clicked.connect(self._on_trace)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)

        btn_layout.addWidget(self._target_input)
        btn_layout.addWidget(self._trace_btn)
        btn_layout.addWidget(self._stop_btn)
        layout.addLayout(btn_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status
        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #6c7086;")
        layout.addWidget(self._status)

        # Hop table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["TTL", "IP", "RTT (ms)", "Hostname"])
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            "QTableWidget { background-color: #1e1e2e; color: #cdd6f4; "
            "gridline-color: #313244; } "
            "QTableWidget::item:selected { background-color: #45475a; } "
            "QHeaderView::section { background-color: #181825; color: #cdd6f4; "
            "padding: 4px; border: 1px solid #313244; }"
        )
        layout.addWidget(self._table)

    def _on_trace(self) -> None:
        target = self._target_input.get_target()
        if target:
            self._trace_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
            self._progress.setVisible(True)
            self._table.setRowCount(0)
            self.traceroute_requested.emit(target[0], target[1])

    def add_hop(self, hop: dict) -> None:
        """Add a hop row to the table.

        Args:
            hop: Dict with ttl, ip, rtt_ms, is_timeout.
        """
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(str(hop.get("ttl", ""))))
        self._table.setItem(row, 1, QTableWidgetItem(str(hop.get("ip", "*"))))
        rtt = f"{hop['rtt_ms']:.1f}" if hop.get("rtt_ms") is not None else "timeout"
        self._table.setItem(row, 2, QTableWidgetItem(rtt))
        self._table.setItem(row, 3, QTableWidgetItem(str(hop.get("hostname", ""))))

    def set_progress(self, current: int, total: int) -> None:
        """Update progress bar."""
        self._progress.setMaximum(total)
        self._progress.setValue(current)

    def complete(self, result: dict) -> None:
        """Called when traceroute completes."""
        self._trace_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)
        resolved = result.get("resolved", 0)
        total = result.get("total", 0)
        self._status.setText(f"Complete: {resolved}/{total} hops resolved")

    def on_error(self, message: str) -> None:
        """Called on error."""
        self._trace_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)
        self._status.setText(f"Error: {message}")
        self._status.setStyleSheet("color: #f87171;")
