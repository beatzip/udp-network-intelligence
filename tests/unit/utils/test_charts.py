"""Tests for pyqtgraph chart widgets."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure QApplication exists before any widget imports
_qapp = None


def _ensure_qapp() -> None:
    global _qapp
    if _qapp is None:
        from PySide6.QtWidgets import QApplication
        _qapp = QApplication.instance() or QApplication(sys.argv)


_ensure_qapp()

from uni.view.widgets.chart import (
    BaseChart,
    HistoryChart,
    JitterChart,
    LossChart,
    RTTChart,
    StatsSummary,
    ChartPanel,
)


class TestBaseChart:
    """Tests for BaseChart."""

    def test_add_point(self) -> None:
        chart = BaseChart(title="Test")
        chart.add_point(10.0)
        assert chart.data_count == 1

    def test_add_multiple_points(self) -> None:
        chart = BaseChart(max_points=5)
        for i in range(10):
            chart.add_point(float(i))
        assert chart.data_count == 5

    def test_clear(self) -> None:
        chart = BaseChart()
        chart.add_point(10.0)
        chart.add_point(20.0)
        chart.reset()
        assert chart.data_count == 0

    def test_get_data(self) -> None:
        chart = BaseChart()
        chart.add_point(10.0)
        chart.add_point(20.0)
        timestamps, values = chart.get_data()
        assert len(values) == 2
        assert values[0] == 10.0
        assert values[1] == 20.0

    def test_export_png(self, tmp_path: Path) -> None:
        chart = BaseChart(title="Export Test")
        chart.add_point(42.0)
        filepath = tmp_path / "test_chart.png"
        chart.export_png(filepath)
        assert filepath.exists()


class TestRTTChart:
    """Tests for RTTChart."""

    def test_add_point(self) -> None:
        chart = RTTChart()
        chart.add_point(42.5)
        assert chart.data_count == 1

    def test_color_green(self) -> None:
        chart = RTTChart()
        chart.add_point(30.0)
        # Should not raise

    def test_color_yellow(self) -> None:
        chart = RTTChart()
        chart.add_point(100.0)

    def test_color_red(self) -> None:
        chart = RTTChart()
        chart.add_point(200.0)


class TestLossChart:
    """Tests for LossChart."""

    def test_add_point(self) -> None:
        chart = LossChart()
        chart.add_point(5.0)
        assert chart.data_count == 1

    def test_clamping(self) -> None:
        chart = LossChart()
        chart.add_point(150.0)  # Should be clamped to 100
        timestamps, values = chart.get_data()
        assert values[0] == 100.0

    def test_negative_clamped(self) -> None:
        chart = LossChart()
        chart.add_point(-10.0)
        timestamps, values = chart.get_data()
        assert values[0] == 0.0


class TestJitterChart:
    """Tests for JitterChart."""

    def test_add_point(self) -> None:
        chart = JitterChart()
        chart.add_point(3.2)
        assert chart.data_count == 1


class TestHistoryChart:
    """Tests for HistoryChart."""

    def test_add_series(self) -> None:
        chart = HistoryChart()
        series = chart.add_series("Test", "#ff0000")
        assert series is not None

    def test_update_series(self) -> None:
        chart = HistoryChart()
        series = chart.add_series("Test")
        chart.update_series(series, [1.0, 2.0, 3.0], [10.0, 20.0, 30.0])


class TestStatsSummary:
    """Tests for StatsSummary."""

    def test_add_metric(self) -> None:
        summary = StatsSummary()
        summary.add_metric("rtt", "RTT", "15.2 ms")
        assert "rtt" in summary._labels

    def test_update_metric(self) -> None:
        summary = StatsSummary()
        summary.add_metric("rtt", "RTT")
        summary.update_metric("rtt", "42.0 ms")
        _, label = summary._labels["rtt"]
        assert label.text() == "42.0 ms"


class TestChartPanel:
    """Tests for ChartPanel."""

    def test_creation(self) -> None:
        panel = ChartPanel(RTTChart, title="Test Panel")
        assert panel.chart is not None
        assert isinstance(panel.chart, RTTChart)

    def test_add_point(self) -> None:
        panel = ChartPanel(LossChart)
        panel.chart.add_point(5.0)
        assert panel.chart.data_count == 1
