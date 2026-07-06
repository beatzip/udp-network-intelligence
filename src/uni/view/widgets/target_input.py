"""Target input widget — validated IP:Port input field."""

from __future__ import annotations

import re

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QWidget


class TargetInput(QWidget):
    """Validated input for IP:Port target strings.

    Signals:
        target_changed: Emitted with (host, port) when input is valid.
        target_invalid: Emitted when input is invalid.
    """

    target_changed = Signal(str, int)
    target_invalid = Signal(str)

    _PATTERN = re.compile(
        r"^(?P<host>"
        r"(?:\d{1,3}\.){3}\d{1,3}"
        r"|(?:[0-9a-fA-F:]+:+)+[0-9a-fA-F]+"
        r"|[\w.-]+"
        r")"
        r":(?P<port>\d{1,5})$"
    )

    def __init__(self, parent: QWidget | None = None, placeholder: str = "host:port") -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("Target:")
        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setMinimumWidth(200)

        layout.addWidget(self._label)
        layout.addWidget(self._input)

        self._input.textChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str) -> None:
        if not text.strip():
            return
        match = self._PATTERN.match(text.strip())
        if match:
            host = match.group("host")
            port = int(match.group("port"))
            if 1 <= port <= 65535:
                self.target_changed.emit(host, port)
        else:
            self.target_invalid.emit(text)

    def get_target(self) -> tuple[str, int] | None:
        """Get the current target as (host, port) if valid.

        Returns:
            (host, port) tuple, or None if invalid.
        """
        text = self._input.text().strip()
        match = self._PATTERN.match(text)
        if match:
            host = match.group("host")
            port = int(match.group("port"))
            if 1 <= port <= 65535:
                return host, port
        return None

    def set_target(self, host: str, port: int) -> None:
        """Set the input text.

        Args:
            host: Host string.
            port: Port number.
        """
        self._input.setText(f"{host}:{port}")

    def clear(self) -> None:
        """Clear the input field."""
        self._input.clear()

    @property
    def text(self) -> str:
        """Current input text."""
        return self._input.text()
