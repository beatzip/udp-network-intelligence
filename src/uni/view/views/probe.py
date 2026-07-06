"""Probe View — configure and run probe campaigns with live charts."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from uni.view.widgets.chart import JitterChart, LossChart, RTTChart
from uni.view.widgets.target_input import TargetInput


class ProbeView(QWidget):
    """Probe campaign view with configuration and live charts.

    Signals:
        probe_requested: Emitted with (host, port, mode, interval, count).
        stop_requested: Emitted when stop is clicked.
    """

    probe_requested = Signal(str, int, str, float, int)
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Target input row
        target_layout = QHBoxLayout()
        self._target_input = TargetInput(placeholder="Target (host:port)")
        target_layout.addWidget(self._target_input)

        # Mode selector
        target_layout.addWidget(QLabel("Mode:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["normal", "deep", "aggressive"])
        target_layout.addWidget(self._mode_combo)

        # Custom count
        target_layout.addWidget(QLabel("Count:"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 1000)
        self._count_spin.setValue(20)
        target_layout.addWidget(self._count_spin)

        # Custom interval
        target_layout.addWidget(QLabel("Interval:"))
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(1, 100)
        self._interval_spin.setValue(10)
        self._interval_spin.setSuffix(" x0.1s")
        target_layout.addWidget(self._interval_spin)

        layout.addLayout(target_layout)

        # Buttons
        btn_layout = QHBoxLayout()
        self._start_btn = QPushButton("Start Probe")
        self._start_btn.clicked.connect(self._on_start)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self.stop_requested.emit)

        btn_layout.addWidget(self._start_btn)
        btn_layout.addWidget(self._stop_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Progress
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        # Status
        self._status = QLabel("Ready")
        self._status.setStyleSheet("color: #6c7086;")
        layout.addWidget(self._status)

        # Charts
        charts_layout = QHBoxLayout()
        self._latency_chart = RTTChart()
        self._loss_chart = LossChart()
        self._jitter_chart = JitterChart()
        charts_layout.addWidget(self._latency_chart)
        charts_layout.addWidget(self._loss_chart)
        charts_layout.addWidget(self._jitter_chart)
        layout.addLayout(charts_layout)

    def _on_start(self) -> None:
        target = self._target_input.get_target()
        if not target:
            self._status.setText("Invalid target")
            self._status.setStyleSheet("color: #f87171;")
            return

        mode = self._mode_combo.currentText()
        count = self._count_spin.value()
        interval = self._interval_spin.value() / 10.0

        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._progress.setVisible(True)
        self._progress.setMaximum(count)
        self._progress.setValue(0)
        self._latency_chart.clear()
        self._loss_chart.clear()
        self._jitter_chart.clear()

        self.probe_requested.emit(target[0], target[1], mode, interval, count)

    def update_progress(self, current: int, total: int, rtt: float) -> None:
        """Update progress and charts.

        Args:
            current: Current probe number.
            total: Total probes.
            rtt: Last RTT value (-1 if timeout).
        """
        self._progress.setMaximum(total)
        self._progress.setValue(current)
        self._status.setText(
            f"Probe {current}/{total} — RTT: {rtt:.1f}ms"
            if rtt >= 0
            else f"Probe {current}/{total} — timeout"
        )

        if rtt >= 0:
            self._latency_chart.add_point(rtt)

    def complete(self, result: dict[str, object]) -> None:
        """Called when probe completes."""
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)

        grade = result.get("grade", "?")
        rtt = result.get("avg_rtt", 0)
        loss = result.get("loss_percent", 0)
        jitter = result.get("jitter", 0)
        self._status.setText(
            f"Complete: grade={grade}, rtt={rtt:.1f}ms, "
            f"loss={loss:.1f}%, jitter={jitter:.1f}ms"
        )
        self._status.setStyleSheet("color: #4ade80;")

    def on_error(self, message: str) -> None:
        """Called on error."""
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._progress.setVisible(False)
        self._status.setText(f"Error: {message}")
        self._status.setStyleSheet("color: #f87171;")
