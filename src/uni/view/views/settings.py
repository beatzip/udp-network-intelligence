"""Settings View — app configuration UI."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


class SettingsView(QWidget):
    """Application settings view.

    Signals:
        setting_changed: Emitted with (section, key, value).
        theme_changed: Emitted with theme name.
    """

    setting_changed = Signal(str, str, object)
    theme_changed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # UI Settings
        ui_group = QGroupBox("Interface")
        ui_form = QFormLayout()

        self._theme_combo = QComboBox()
        self._theme_combo.addItems(["dark", "light"])
        self._theme_combo.currentTextChanged.connect(
            lambda v: self.theme_changed.emit(v)
        )
        ui_form.addRow("Theme:", self._theme_combo)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(800, 3840)
        self._width_spin.setValue(1280)
        ui_form.addRow("Window Width:", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(600, 2160)
        self._height_spin.setValue(800)
        ui_form.addRow("Window Height:", self._height_spin)

        self._notifications_check = QCheckBox("Show notifications")
        self._notifications_check.setChecked(True)
        ui_form.addRow(self._notifications_check)

        ui_group.setLayout(ui_form)
        layout.addWidget(ui_group)

        # Probe Settings
        probe_group = QGroupBox("Probe")
        probe_form = QFormLayout()

        self._default_count = QSpinBox()
        self._default_count.setRange(1, 1000)
        self._default_count.setValue(50)
        probe_form.addRow("Default Count:", self._default_count)

        self._default_interval = QSpinBox()
        self._default_interval.setRange(1, 100)
        self._default_interval.setValue(10)
        self._default_interval.setSuffix(" x0.1s")
        probe_form.addRow("Default Interval:", self._default_interval)

        self._default_timeout = QSpinBox()
        self._default_timeout.setRange(1, 30)
        self._default_timeout.setValue(3)
        self._default_timeout.setSuffix("s")
        probe_form.addRow("Default Timeout:", self._default_timeout)

        self._default_port = QSpinBox()
        self._default_port.setRange(1, 65535)
        self._default_port.setValue(27015)
        probe_form.addRow("Default Port:", self._default_port)

        probe_group.setLayout(probe_form)
        layout.addWidget(probe_group)

        # History Settings
        history_group = QGroupBox("History")
        history_form = QFormLayout()

        self._max_records = QSpinBox()
        self._max_records.setRange(100, 100000)
        self._max_records.setValue(10000)
        history_form.addRow("Max Records:", self._max_records)

        self._cleanup_days = QSpinBox()
        self._cleanup_days.setRange(1, 365)
        self._cleanup_days.setValue(90)
        self._cleanup_days.setSuffix(" days")
        history_form.addRow("Cleanup After:", self._cleanup_days)

        history_group.setLayout(history_form)
        layout.addWidget(history_group)

        layout.addStretch()

    def get_settings(self) -> dict[str, Any]:
        """Get all current settings."""
        return {
            "ui": {
                "theme": self._theme_combo.currentText(),
                "window_width": self._width_spin.value(),
                "window_height": self._height_spin.value(),
                "show_notifications": self._notifications_check.isChecked(),
            },
            "probe": {
                "default_count": self._default_count.value(),
                "default_interval": self._default_interval.value() / 10.0,
                "default_timeout": self._default_timeout.value(),
                "default_port": self._default_port.value(),
            },
            "history": {
                "max_records": self._max_records.value(),
                "auto_cleanup_days": self._cleanup_days.value(),
            },
        }

    def load_settings(self, settings: dict[str, Any]) -> None:
        """Load settings from a dictionary.

        Args:
            settings: Settings dictionary.
        """
        ui = settings.get("ui", {})
        if "theme" in ui:
            idx = self._theme_combo.findText(ui["theme"])
            if idx >= 0:
                self._theme_combo.setCurrentIndex(idx)
        if "window_width" in ui:
            self._width_spin.setValue(ui["window_width"])
        if "window_height" in ui:
            self._height_spin.setValue(ui["window_height"])
        if "show_notifications" in ui:
            self._notifications_check.setChecked(ui["show_notifications"])

        probe = settings.get("probe", {})
        if "default_count" in probe:
            self._default_count.setValue(probe["default_count"])
        if "default_interval" in probe:
            self._default_interval.setValue(int(probe["default_interval"] * 10))
        if "default_timeout" in probe:
            self._default_timeout.setValue(probe["default_timeout"])
        if "default_port" in probe:
            self._default_port.setValue(probe["default_port"])

        history = settings.get("history", {})
        if "max_records" in history:
            self._max_records.setValue(history["max_records"])
        if "auto_cleanup_days" in history:
            self._cleanup_days.setValue(history["auto_cleanup_days"])
