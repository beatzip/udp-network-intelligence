"""Export dialog — choose format and destination for data export."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ExportDialog(QDialog):
    """Dialog for selecting export format and saving to file."""

    export_requested = Signal(str, str)  # (format, filepath)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Export Data")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)

        # Format selection
        fmt_layout = QHBoxLayout()
        fmt_layout.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        self._format_combo.addItems(["CSV", "JSON", "HTML"])
        fmt_layout.addWidget(self._format_combo)
        layout.addLayout(fmt_layout)

        # Info
        self._info_label = QLabel("Select a format and click Export to save.")
        layout.addWidget(self._info_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self._export_btn = QPushButton("Export")
        self._cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(self._export_btn)
        btn_layout.addWidget(self._cancel_btn)
        layout.addLayout(btn_layout)

        self._export_btn.clicked.connect(self._on_export)
        self._cancel_btn.clicked.connect(self.reject)

    def _on_export(self) -> None:
        fmt = self._format_combo.currentText().lower()
        ext_map = {"csv": "csv", "json": "json", "html": "html"}
        ext = ext_map.get(fmt, "txt")

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Data", f"export.{ext}",
            f"{fmt.upper()} Files (*.{ext})"
        )
        if filepath:
            self.export_requested.emit(fmt, filepath)
            self.accept()
