"""History view — browse measurement and error history."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from uni.view.dialogs.export import ExportDialog


class HistoryView(QWidget):
    """History browsing view with measurements and errors tabs.

    Signals:
        load_requested: Emitted when data should be loaded.
        export_requested: Emitted when export is requested.
    """

    load_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self.load_requested.emit)
        toolbar.addWidget(self._refresh_btn)

        self._export_btn = QPushButton("Export")
        self._export_btn.clicked.connect(self._on_export)
        toolbar.addWidget(self._export_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # Tabs
        self._tabs = QTabWidget()

        # Measurements tab
        self._measurements_table = QTableWidget()
        self._measurements_table.setColumnCount(10)
        self._measurements_table.setHorizontalHeaderLabels([
            "Host", "Port", "Mode", "Sent", "Received", "Loss%",
            "Avg RTT", "Jitter", "Grade", "Duration"
        ])
        self._measurements_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._measurements_table.setAlternatingRowColors(True)
        self._tabs.addTab(self._measurements_table, "Measurements")

        # Errors tab
        self._errors_table = QTableWidget()
        self._errors_table.setColumnCount(5)
        self._errors_table.setHorizontalHeaderLabels([
            "Time", "Host", "Type", "Message", "Resolved"
        ])
        self._errors_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._errors_table.setAlternatingRowColors(True)
        self._tabs.addTab(self._errors_table, "Errors")

        layout.addWidget(self._tabs)

        # Status
        self._status_label = QLabel("No history loaded")
        self._status_label.setStyleSheet("color: #6c7086;")
        layout.addWidget(self._status_label)

        # Style tables
        for table in (self._measurements_table, self._errors_table):
            table.setStyleSheet(
                "QTableWidget { background-color: #1e1e2e; color: #cdd6f4; "
                "gridline-color: #313244; } "
                "QTableWidget::item:selected { background-color: #45475a; } "
                "QHeaderView::section { background-color: #181825; color: #cdd6f4; "
                "padding: 4px; border: 1px solid #313244; }"
            )

    def _on_export(self) -> None:
        dialog = ExportDialog(self)
        dialog.export_requested.connect(self.export_requested.emit)
        dialog.exec()

    def update_measurements(self, data: list[dict]) -> None:
        """Update the measurements table.

        Args:
            data: List of measurement dictionaries.
        """
        self._measurements_table.setRowCount(len(data))
        for i, m in enumerate(data):
            self._measurements_table.setItem(i, 0, QTableWidgetItem(str(m.get("target_host", ""))))
            self._measurements_table.setItem(i, 1, QTableWidgetItem(str(m.get("target_port", ""))))
            self._measurements_table.setItem(i, 2, QTableWidgetItem(str(m.get("mode", ""))))
            self._measurements_table.setItem(i, 3, QTableWidgetItem(str(m.get("sent", ""))))
            self._measurements_table.setItem(i, 4, QTableWidgetItem(str(m.get("received", ""))))
            loss = f"{m.get('lost', 0) / max(1, m.get('sent', 1)) * 100:.1f}%"
            self._measurements_table.setItem(i, 5, QTableWidgetItem(loss))
            self._measurements_table.setItem(i, 6, QTableWidgetItem(f"{m.get('avg_rtt', 0):.1f}"))
            self._measurements_table.setItem(i, 7, QTableWidgetItem(f"{m.get('jitter', 0):.1f}"))
            self._measurements_table.setItem(i, 8, QTableWidgetItem(str(m.get("quality_grade", ""))))
            self._measurements_table.setItem(i, 9, QTableWidgetItem(f"{m.get('duration_seconds', 0):.1f}s"))
        self._status_label.setText(f"{len(data)} measurements loaded")

    def update_errors(self, data: list[dict]) -> None:
        """Update the errors table.

        Args:
            data: List of error dictionaries.
        """
        self._errors_table.setRowCount(len(data))
        for i, e in enumerate(data):
            self._errors_table.setItem(i, 0, QTableWidgetItem(str(e.get("timestamp", ""))))
            self._errors_table.setItem(i, 1, QTableWidgetItem(str(e.get("host", ""))))
            self._errors_table.setItem(i, 2, QTableWidgetItem(str(e.get("error_type", ""))))
            self._errors_table.setItem(i, 3, QTableWidgetItem(str(e.get("error_message", ""))))
            resolved = "Yes" if e.get("resolved") else "No"
            self._errors_table.setItem(i, 4, QTableWidgetItem(resolved))
