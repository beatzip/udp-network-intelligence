"""Add Server dialog."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class AddServerDialog(QDialog):
    """Dialog for adding a new server."""

    server_added = Signal(str, int, str)  # host, port, name

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Server")
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._host_input = QLineEdit()
        self._host_input.setPlaceholderText("192.168.1.1")
        form.addRow("Host:", self._host_input)

        self._port_input = QSpinBox()
        self._port_input.setRange(1, 65535)
        self._port_input.setValue(27015)
        form.addRow("Port:", self._port_input)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("Optional server name")
        form.addRow("Name:", self._name_input)

        layout.addLayout(form)

        # Buttons
        btn_layout = QHBoxLayout()
        self._ok_btn = QPushButton("Add")
        self._cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(self._ok_btn)
        btn_layout.addWidget(self._cancel_btn)

        layout.addLayout(btn_layout)

        self._ok_btn.clicked.connect(self._on_add)
        self._cancel_btn.clicked.connect(self.reject)

    def _on_add(self) -> None:
        host = self._host_input.text().strip()
        if not host:
            QMessageBox.warning(self, "Validation", "Host cannot be empty.")
            return
        port = self._port_input.value()
        name = self._name_input.text().strip()
        self.server_added.emit(host, port, name)
        self.accept()

    def get_data(self) -> tuple[str, int, str]:
        """Get the entered data."""
        return (
            self._host_input.text().strip(),
            self._port_input.value(),
            self._name_input.text().strip(),
        )
