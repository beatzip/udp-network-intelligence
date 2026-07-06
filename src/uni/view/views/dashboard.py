"""Dashboard view — overview with live charts and stats."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from uni.view.widgets.chart import JitterChart, LossChart, RTTChart


class DashboardView(QWidget):
    """Dashboard overview with stats cards and live charts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        # Stats cards
        stats_layout = QGridLayout()
        self._stat_cards: dict[str, tuple[QLabel, QLabel]] = {}
        stats = [
            ("servers", "Servers", "0"),
            ("measurements", "Measurements", "0"),
            ("avg_rtt", "Avg RTT", "—"),
            ("avg_loss", "Avg Loss", "—"),
        ]
        for i, (key, title, default) in enumerate(stats):
            frame, title_label, value_label = self._create_stat_card(title, default)
            self._stat_cards[key] = (title_label, value_label)
            stats_layout.addWidget(frame, i // 4, i % 4)

        layout.addLayout(stats_layout)

        # Charts
        charts_layout = QHBoxLayout()

        self._latency_chart = RTTChart()
        charts_layout.addWidget(self._latency_chart)

        self._loss_chart = LossChart()
        charts_layout.addWidget(self._loss_chart)

        self._jitter_chart = JitterChart()
        charts_layout.addWidget(self._jitter_chart)

        layout.addLayout(charts_layout)

        # Quick actions
        actions_layout = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._export_btn = QPushButton("Export")
        actions_layout.addWidget(self._refresh_btn)
        actions_layout.addWidget(self._export_btn)
        actions_layout.addStretch()
        layout.addLayout(actions_layout)

        layout.addStretch()
        scroll.setWidget(content)
        main_layout.addWidget(scroll)

    def _create_stat_card(
        self, title: str, default: str
    ) -> tuple[QFrame, QLabel, QLabel]:
        """Create a stat card with title and value labels.

        Returns:
            A tuple of ``(container_frame, title_label, value_label)``. The
            caller must add ``container_frame`` to a layout — returning only
            the inner labels would let the frame (and, via Qt's parent-owns-
            child lifetime rules, the labels themselves) be garbage-collected
            as soon as this method returns.
        """
        frame = QFrame()
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background-color: #1e1e2e; border: 1px solid #313244; "
            "border-radius: 8px; padding: 10px; }"
        )
        v_layout = QVBoxLayout(frame)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        v_layout.addWidget(title_label)

        value_label = QLabel(default)
        value_label.setStyleSheet("color: #cdd6f4; font-size: 20px; font-weight: bold;")
        v_layout.addWidget(value_label)

        return frame, title_label, value_label

    def update_stat(self, key: str, value: str) -> None:
        """Update a stat card value.

        Args:
            key: Stat key (e.g., 'servers', 'avg_rtt').
            value: Display value.
        """
        if key in self._stat_cards:
            _, value_label = self._stat_cards[key]
            value_label.setText(value)

    def add_latency_point(self, value: float) -> None:
        """Add a point to the latency chart."""
        self._latency_chart.add_point(value)

    def add_loss_point(self, value: float) -> None:
        """Add a point to the loss chart."""
        self._loss_chart.add_point(value)

    def add_jitter_point(self, value: float) -> None:
        """Add a point to the jitter chart."""
        self._jitter_chart.add_point(value)

    def clear_charts(self) -> None:
        """Clear all chart data."""
        self._latency_chart.clear()
        self._loss_chart.clear()
        self._jitter_chart.clear()
