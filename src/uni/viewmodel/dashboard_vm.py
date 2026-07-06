"""Dashboard ViewModel — aggregates live data from other modules."""

from __future__ import annotations

import logging
from typing import Any

from PySide6.QtCore import Signal

from uni.viewmodel.base import BaseViewModel

logger = logging.getLogger(__name__)


class DashboardViewModel(BaseViewModel):
    """Aggregates data for the dashboard overview.

    Signals:
        stats_updated: Emitted when dashboard stats change.
        chart_data_updated: Emitted when chart data is ready.
    """

    stats_updated = Signal(dict)  # {servers, measurements, errors, avg_rtt, ...}
    chart_data_updated = Signal(list, list)  # (labels, values)

    def __init__(self) -> None:
        super().__init__()
        self._stats: dict[str, Any] = {
            "total_servers": 0,
            "total_measurements": 0,
            "total_errors": 0,
            "avg_rtt": 0.0,
            "avg_loss": 0.0,
            "avg_quality": 0.0,
        }
        self._recent_rtt: list[float] = []
        self._recent_labels: list[str] = []

    def update_stats(self, stats: dict[str, Any]) -> None:
        """Update dashboard statistics.

        Args:
            stats: Statistics dictionary.
        """
        self._stats.update(stats)
        self.stats_updated.emit(self._stats)

    def add_chart_point(self, label: str, value: float) -> None:
        """Add a data point to the live chart.

        Args:
            label: X-axis label (e.g., timestamp).
            value: Y-axis value (e.g., RTT).
        """
        self._recent_labels.append(label)
        self._recent_rtt.append(value)
        # Keep last 200 points
        if len(self._recent_rtt) > 200:
            self._recent_labels = self._recent_labels[-200:]
            self._recent_rtt = self._recent_rtt[-200:]
        self.chart_data_updated.emit(self._recent_labels, self._recent_rtt)

    def get_stats(self) -> dict[str, Any]:
        """Get current dashboard statistics."""
        return dict(self._stats)
