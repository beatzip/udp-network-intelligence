"""Chart widgets — RTT, Loss, Jitter, History charts using pyqtgraph.

pyqtgraph provides:
- High-performance real-time plotting
- Built-in mouse zoom (scroll wheel) and pan (right-click drag)
- Export to PNG via PlotWidget.exportGraphics()
- Dark theme via pg.setConfigOption()

Example::

    chart = RTTChart(title="Latency")
    chart.add_point(42.5)
    chart.export_png("latency.png")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPen
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)

# Configure pyqtgraph dark theme globally
pg.setConfigOption("background", "#1e1e2e")
pg.setConfigOption("foreground", "#cdd6f4")
pg.setConfigOption("antialias", True)

# Color palette (Catppuccin Mocha)
_COLOR_GREEN = "#4ade80"
_COLOR_YELLOW = "#facc15"
_COLOR_RED = "#f87171"
_COLOR_PURPLE = "#a78bfa"
_COLOR_BLUE = "#60a5fa"
_COLOR_CYAN = "#22d3ee"
_COLOR_TEXT = "#cdd6f4"
_COLOR_GRID = "#313244"


# ---------------------------------------------------------------------------
# Base chart
# ---------------------------------------------------------------------------


class BaseChart(pg.PlotWidget):  # type: ignore[misc]
    """Base class for all real-time charts.

    Provides:
    - Auto-scrolling X axis
    - Zoom via scroll wheel
    - Pan via right-click drag
    - Export to PNG
    - Dark theme styling

    Attributes:
        max_points: Maximum data points before scrolling.
        title: Chart title text.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        max_points: int = 200,
        pen_color: str = _COLOR_GREEN,
    ) -> None:
        super().__init__(parent)
        self._max_points = max_points
        self._values: list[float] = []
        self._timestamps: list[float] = []
        self._title_text = title

        # Styling
        self.setBackground(_COLOR_GRID)
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setTitle(title, color=_COLOR_TEXT, size="11pt")
        self.setLabel("left", "", color=_COLOR_TEXT)
        self.setLabel("bottom", "", color=_COLOR_TEXT)

        # Pen for the main curve
        self._pen = QPen()
        self._pen.setColor(pen_color)
        self._pen.setWidth(2)

        # Plot curve
        self._curve = self.plot(pen=self._pen, name=title)

        # Enable mouse interaction
        self.setMouseEnabled(x=True, y=True)
        self.getViewBox().setMouseEnabled(x=True, y=True)

    def add_point(self, value: float, timestamp: float | None = None) -> None:
        """Add a data point to the chart.

        Args:
            value: Y-axis value.
            timestamp: Optional X-axis timestamp. Uses index if None.
        """
        ts = timestamp if timestamp is not None else len(self._values)
        self._values.append(value)
        self._timestamps.append(ts)

        # Trim to max points
        if len(self._values) > self._max_points:
            self._values = self._values[-self._max_points :]
            self._timestamps = self._timestamps[-self._max_points :]

        self._update_plot()

    def _update_plot(self) -> None:
        """Redraw the plot with current data."""
        if not self._values:
            self._curve.setData([], [])
            return

        x = np.array(self._timestamps)
        y = np.array(self._values)
        self._curve.setData(x, y)

        # Auto-range Y axis with padding
        y_min = max(0, np.min(y) - 5)
        y_max = np.max(y) + 5
        self.setYRange(y_min, y_max, padding=0.05)

        # Auto-range X axis (show last N points)
        if len(x) > 1:
            self.setXRange(x[0], x[-1], padding=0.02)

    def set_pen_color(self, color: str) -> None:
        """Change the curve color.

        Args:
            color: CSS color string.
        """
        self._pen.setColor(color)
        self._curve.setPen(self._pen)

    def add_horizontal_line(
        self, y: float, color: str = _COLOR_YELLOW, label: str = ""
    ) -> None:
        """Add a horizontal reference line.

        Args:
            y: Y position.
            color: Line color.
            label: Optional label text.
        """
        pen = QPen()
        pen.setColor(color)
        pen.setStyle(Qt.PenStyle.DashLine)
        pen.setWidth(1)
        self.addLine(y=y, pen=pen, label=label)

    def add_threshold_band(
        self, y_min: float, y_max: float, color: str = "#4ade8020"
    ) -> None:
        """Add a shaded threshold band.

        Args:
            y_min: Band lower bound.
            y_max: Band upper bound.
            color: Fill color (with alpha).
        """
        from PySide6.QtGui import QBrush, QColor

        brush = QBrush(QColor(color))
        self.plot(
            [
                self._timestamps[0] if self._timestamps else 0,
                self._timestamps[-1] if self._timestamps else 1,
            ],
            [y_max, y_max],
            pen=pg.mkPen(None),
            brush=brush,
        )

    def export_png(
        self, filepath: str | Path, width: int = 1920, height: int = 1080
    ) -> None:
        """Export the chart to a PNG file.

        Args:
            filepath: Output file path.
            width: Image width in pixels.
            height: Image height in pixels.
        """
        from PySide6.QtCore import QRect
        from PySide6.QtGui import QImage, QPainter

        # Create image at the specified size
        rect = QRect(0, 0, width, height)
        image = QImage(rect.size(), QImage.Format.Format_ARGB32)
        image.fill(_COLOR_GRID)

        painter = QPainter(image)
        self.render(painter, target=rect)
        painter.end()

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(path))
        logger.info("Chart exported to %s", path)

    def reset(self) -> None:
        """Reset all chart data and remove curves."""
        self._values.clear()
        self._timestamps.clear()
        self.clear()
        # Re-add the main curve after clear()
        self._curve = self.plot(pen=self._pen, name=self._title_text)

    @property
    def data_count(self) -> int:
        """Number of data points."""
        return len(self._values)

    def get_data(self) -> tuple[list[float], list[float]]:
        """Get current data.

        Returns:
            Tuple of (timestamps, values).
        """
        return list(self._timestamps), list(self._values)


# ---------------------------------------------------------------------------
# RTT Chart
# ---------------------------------------------------------------------------


class RTTChart(BaseChart):
    """Real-time RTT (latency) chart.

    Features:
    - Color-coded by latency (green < 50ms, yellow < 150ms, red > 150ms)
    - Scroll wheel zoom, right-click pan
    - Export to PNG
    - Horizontal threshold lines

    Example::

        chart = RTTChart(title="Latency")
        chart.add_point(42.5)
        chart.add_threshold_line(50.0, "Good")
    """

    point_added = Signal(float)  # value

    def __init__(self, parent: QWidget | None = None, max_points: int = 200) -> None:
        super().__init__(
            parent,
            title="RTT (ms)",
            max_points=max_points,
            pen_color=_COLOR_GREEN,
        )
        # Add default threshold lines
        self.add_horizontal_line(50.0, _COLOR_GREEN, "50ms")
        self.add_horizontal_line(150.0, _COLOR_YELLOW, "150ms")

    def add_point(self, value: float, timestamp: float | None = None) -> None:
        """Add RTT point with color coding.

        Args:
            value: RTT in milliseconds.
            timestamp: Optional timestamp.
        """
        super().add_point(value, timestamp)

        # Dynamic color based on latest value
        if value < 50:
            color = _COLOR_GREEN
        elif value < 150:
            color = _COLOR_YELLOW
        else:
            color = _COLOR_RED
        self.set_pen_color(color)

        self.point_added.emit(value)


# ---------------------------------------------------------------------------
# Loss Chart
# ---------------------------------------------------------------------------


class LossChart(BaseChart):
    """Packet loss percentage chart.

    Features:
    - 0-100% Y axis range
    - Red color coding
    - Scroll/pan/export

    Example::

        chart = LossChart(title="Packet Loss")
        chart.add_point(2.5)
    """

    point_added = Signal(float)

    def __init__(self, parent: QWidget | None = None, max_points: int = 200) -> None:
        super().__init__(
            parent,
            title="Loss (%)",
            max_points=max_points,
            pen_color=_COLOR_RED,
        )
        self.setYRange(0, 10, padding=0.1)
        self.add_horizontal_line(5.0, _COLOR_YELLOW, "5%")

    def add_point(self, value: float, timestamp: float | None = None) -> None:
        """Add loss point (clamped 0-100%).

        Args:
            value: Loss percentage.
            timestamp: Optional timestamp.
        """
        clamped = max(0.0, min(100.0, value))
        super().add_point(clamped, timestamp)

        if clamped < 2:
            color = _COLOR_GREEN
        elif clamped < 10:
            color = _COLOR_YELLOW
        else:
            color = _COLOR_RED
        self.set_pen_color(color)

        self.point_added.emit(clamped)


# ---------------------------------------------------------------------------
# Jitter Chart
# ---------------------------------------------------------------------------


class JitterChart(BaseChart):
    """Jitter chart displaying inter-packet delay variation.

    Features:
    - Purple color coding
    - Scroll/pan/export

    Example::

        chart = JitterChart(title="Jitter")
        chart.add_point(3.2)
    """

    point_added = Signal(float)

    def __init__(self, parent: QWidget | None = None, max_points: int = 200) -> None:
        super().__init__(
            parent,
            title="Jitter (ms)",
            max_points=max_points,
            pen_color=_COLOR_PURPLE,
        )
        self.add_horizontal_line(15.0, _COLOR_YELLOW, "15ms")

    def add_point(self, value: float, timestamp: float | None = None) -> None:
        """Add jitter point.

        Args:
            value: Jitter in milliseconds.
            timestamp: Optional timestamp.
        """
        super().add_point(value, timestamp)

        if value < 5:
            color = _COLOR_GREEN
        elif value < 15:
            color = _COLOR_YELLOW
        else:
            color = _COLOR_RED
        self.set_pen_color(color)

        self.point_added.emit(value)


# ---------------------------------------------------------------------------
# History Chart
# ---------------------------------------------------------------------------


class HistoryChart(BaseChart):
    """Historical data chart with timestamps.

    Features:
    - Full timestamp-based X axis
    - Scroll/zoom/pan
    - Multiple series support
    - Export to PNG

    Example::

        chart = HistoryChart(title="Historical RTT")
        chart.add_point(42.5, timestamp=time.time())
    """

    def __init__(self, parent: QWidget | None = None, max_points: int = 1000) -> None:
        super().__init__(
            parent,
            title="History",
            max_points=max_points,
            pen_color=_COLOR_BLUE,
        )
        self.setLabel("bottom", "Time", color=_COLOR_TEXT)

    def add_series(self, name: str, color: str = _COLOR_CYAN) -> pg.PlotDataItem:
        """Add an additional data series.

        Args:
            name: Series name.
            color: Line color.

        Returns:
            The PlotDataItem for the new series.
        """
        pen = QPen()
        pen.setColor(color)
        pen.setWidth(2)
        return self.plot(pen=pen, name=name)

    def update_series(
        self, series: pg.PlotDataItem, x: list[float], y: list[float]
    ) -> None:
        """Update a specific series with new data.

        Args:
            series: The PlotDataItem to update.
            x: X-axis values.
            y: Y-axis values.
        """
        series.setData(x, y)


# ---------------------------------------------------------------------------
# Stats Summary Widget
# ---------------------------------------------------------------------------


class StatsSummary(QWidget):
    """Compact statistics summary with labels.

    Displays key metrics in a grid layout with colored indicators.

    Example::

        summary = StatsSummary()
        summary.update({"RTT": "15.2 ms", "Loss": "0.5%", "Jitter": "2.1 ms"})
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: dict[str, tuple[QLabel, QLabel]] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

    def add_metric(self, key: str, title: str, value: str = "—") -> None:
        """Add a metric display.

        Args:
            key: Unique metric key.
            title: Display title.
            value: Initial value.
        """
        container = QWidget()
        v_layout = QVBoxLayout(container)
        v_layout.setContentsMargins(8, 4, 8, 4)
        v_layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #6c7086; font-size: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        value_label = QLabel(value)
        value_label.setStyleSheet("color: #cdd6f4; font-size: 16px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        v_layout.addWidget(title_label)
        v_layout.addWidget(value_label)

        self._labels[key] = (title_label, value_label)
        lay = self.layout()
        if lay is not None:
            lay.addWidget(container)

    def update_metric(self, key: str, value: str, color: str = "#cdd6f4") -> None:
        """Update a metric value.

        Args:
            key: Metric key.
            value: New display value.
            color: Text color.
        """
        if key in self._labels:
            _, value_label = self._labels[key]
            value_label.setText(value)
            value_label.setStyleSheet(
                f"color: {color}; font-size: 16px; font-weight: bold;"
            )

    def clear(self) -> None:
        """Reset all metrics to default."""
        for _key, (_, value_label) in self._labels.items():
            value_label.setText("—")
            value_label.setStyleSheet(
                "color: #cdd6f4; font-size: 16px; font-weight: bold;"
            )


# ---------------------------------------------------------------------------
# Chart container with export button
# ---------------------------------------------------------------------------


class ChartPanel(QWidget):
    """Chart widget with title and export button.

    Wraps any BaseChart subclass with a header bar containing
    the chart title and an export PNG button.

    Example::

        panel = ChartPanel(RTTChart, title="Latency")
        panel.chart.add_point(42.0)
        panel.export_chart("latency.png")
    """

    def __init__(
        self,
        chart_class: type[BaseChart] | None = None,
        parent: QWidget | None = None,
        title: str = "Chart",
        **kwargs: Any,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #cdd6f4; font-size: 12px; font-weight: bold;")
        header.addWidget(title_label)
        header.addStretch()

        export_btn = QPushButton("Export PNG")
        export_btn.setFixedHeight(24)
        export_btn.setStyleSheet(
            "QPushButton { background-color: #45475a; color: #cdd6f4; "
            "border: none; border-radius: 4px; padding: 2px 8px; font-size: 10px; }"
            "QPushButton:hover { background-color: #585b70; }"
        )
        export_btn.clicked.connect(self._on_export)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # Chart
        if chart_class is not None:
            self._chart = chart_class(parent=self, **kwargs)
        else:
            self._chart = BaseChart(parent=self, **kwargs)
        layout.addWidget(self._chart)

        self._export_title = title.lower().replace(" ", "_")

    @property
    def chart(self) -> BaseChart:
        """The underlying chart widget."""
        return self._chart

    def _on_export(self) -> None:
        """Handle export button click."""
        from PySide6.QtWidgets import QFileDialog

        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Chart", f"{self._export_title}.png", "PNG Files (*.png)"
        )
        if filepath:
            self._chart.export_png(filepath)
