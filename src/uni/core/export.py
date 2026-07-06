"""Unified export engine — JSON, CSV, HTML, PDF with consistent structure.

All exporters produce reports with the same logical structure:

    Report
    ├── header      (title, timestamp, version)
    ├── summary     (aggregate statistics)
    ├── servers     (server list with scores)
    ├── measurements (probe results)
    ├── rankings    (ranking history)
    └── errors      (error log)

Each exporter writes this structure to its target format.

Example::

    from uni.core.export import ExportEngine, ReportData

    engine = ExportEngine()
    report = ReportData(title="Probe Campaign", ...)
    html = engine.to_html(report)
    engine.save(report, "report.html")
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from uni.app.constants import APP_NAME, APP_VERSION

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Unified report data model
# ---------------------------------------------------------------------------


@dataclass
class ReportHeader:
    """Report metadata header.

    Attributes:
        title: Report title.
        generated_at: ISO timestamp of report generation.
        app_version: Application version.
        generator: Generator identifier.
    """

    title: str = "UDP Network Intelligence Report"
    generated_at: str = ""
    app_version: str = APP_VERSION
    generator: str = APP_NAME

    def __post_init__(self) -> None:
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "app_version": self.app_version,
            "generator": self.generator,
        }


@dataclass
class ReportSummary:
    """Aggregate statistics for the report.

    Attributes:
        total_servers: Number of servers in report.
        total_measurements: Number of measurements.
        total_errors: Number of errors.
        avg_rtt: Average RTT across all measurements.
        avg_loss: Average packet loss percentage.
        avg_jitter: Average jitter.
        best_server: Best server host.
        worst_server: Worst server host.
    """

    total_servers: int = 0
    total_measurements: int = 0
    total_errors: int = 0
    avg_rtt: float = 0.0
    avg_loss: float = 0.0
    avg_jitter: float = 0.0
    best_server: str = ""
    worst_server: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_servers": self.total_servers,
            "total_measurements": self.total_measurements,
            "total_errors": self.total_errors,
            "avg_rtt": round(self.avg_rtt, 2),
            "avg_loss": round(self.avg_loss, 2),
            "avg_jitter": round(self.avg_jitter, 2),
            "best_server": self.best_server,
            "worst_server": self.worst_server,
        }


@dataclass
class ReportServer:
    """Server entry in the report.

    Attributes:
        host: Server host.
        port: Server port.
        name: Server name.
        map_name: Current map.
        game: Game folder.
        player_count: Current players.
        max_players: Max capacity.
        rtt_score: Normalized RTT score.
        loss_score: Normalized loss score.
        final_score: Final ranking score.
        rank: Position in ranking.
    """

    host: str = ""
    port: int = 27015
    name: str = ""
    map_name: str = ""
    game: str = ""
    player_count: int = 0
    max_players: int = 0
    rtt_score: float = 0.0
    loss_score: float = 0.0
    final_score: float = 0.0
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "name": self.name,
            "map_name": self.map_name,
            "game": self.game,
            "player_count": self.player_count,
            "max_players": self.max_players,
            "rtt_score": round(self.rtt_score, 4),
            "loss_score": round(self.loss_score, 4),
            "final_score": round(self.final_score, 4),
            "rank": self.rank,
        }


@dataclass
class ReportMeasurement:
    """Measurement entry in the report.

    Attributes:
        target: Target host:port.
        mode: Test mode.
        avg_rtt: Average RTT.
        min_rtt: Min RTT.
        max_rtt: Max RTT.
        jitter: Jitter value.
        loss_percent: Packet loss percentage.
        sent: Probes sent.
        received: Probes received.
        grade: Quality grade.
        quality_score: Quality score.
        duration: Duration in seconds.
        timestamp: Unix timestamp.
    """

    target: str = ""
    mode: str = ""
    avg_rtt: float = 0.0
    min_rtt: float = 0.0
    max_rtt: float = 0.0
    jitter: float = 0.0
    loss_percent: float = 0.0
    sent: int = 0
    received: int = 0
    grade: str = ""
    quality_score: float = 0.0
    duration: float = 0.0
    timestamp: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "target": self.target,
            "mode": self.mode,
            "avg_rtt": round(self.avg_rtt, 2),
            "min_rtt": round(self.min_rtt, 2),
            "max_rtt": round(self.max_rtt, 2),
            "jitter": round(self.jitter, 2),
            "loss_percent": round(self.loss_percent, 2),
            "sent": self.sent,
            "received": self.received,
            "grade": self.grade,
            "quality_score": round(self.quality_score, 4),
            "duration": round(self.duration, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class ReportError:
    """Error entry in the report.

    Attributes:
        timestamp: Unix timestamp.
        host: Target host.
        port: Target port.
        error_type: Error category.
        message: Error message.
        resolved: Whether resolved.
    """

    timestamp: float = 0.0
    host: str = ""
    port: int = 0
    error_type: str = ""
    message: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "timestamp": self.timestamp,
            "host": self.host,
            "port": self.port,
            "error_type": self.error_type,
            "message": self.message,
            "resolved": self.resolved,
        }


@dataclass
class ReportData:
    """Complete report data structure.

    This is the unified data model consumed by all exporters.

    Attributes:
        header: Report metadata.
        summary: Aggregate statistics.
        servers: List of server entries.
        measurements: List of measurement entries.
        errors: List of error entries.
        custom: Additional custom data.
    """

    header: ReportHeader = field(default_factory=ReportHeader)
    summary: ReportSummary = field(default_factory=ReportSummary)
    servers: list[ReportServer] = field(default_factory=list)
    measurements: list[ReportMeasurement] = field(default_factory=list)
    errors: list[ReportError] = field(default_factory=list)
    custom: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize entire report to dictionary.

        Returns:
            Complete report as a nested dictionary.
        """
        return {
            "header": self.header.to_dict(),
            "summary": self.summary.to_dict(),
            "servers": [s.to_dict() for s in self.servers],
            "measurements": [m.to_dict() for m in self.measurements],
            "errors": [e.to_dict() for e in self.errors],
            "custom": self.custom,
        }

    def add_measurement(self, measurement: ReportMeasurement) -> None:
        """Add a measurement and update summary statistics."""
        self.measurements.append(measurement)
        self._update_summary()

    def add_server(self, server: ReportServer) -> None:
        """Add a server entry."""
        self.servers.append(server)
        self.summary.total_servers = len(self.servers)

    def add_error(self, error: ReportError) -> None:
        """Add an error entry."""
        self.errors.append(error)
        self.summary.total_errors = len(self.errors)

    def _update_summary(self) -> None:
        """Recalculate summary statistics from measurements."""
        if not self.measurements:
            return
        n = len(self.measurements)
        self.summary.total_measurements = n
        self.summary.avg_rtt = sum(m.avg_rtt for m in self.measurements) / n
        self.summary.avg_loss = sum(m.loss_percent for m in self.measurements) / n
        self.summary.avg_jitter = sum(m.jitter for m in self.measurements) / n

        # Best / worst by quality score
        best = max(self.measurements, key=lambda m: m.quality_score)
        worst = min(self.measurements, key=lambda m: m.quality_score)
        self.summary.best_server = best.target
        self.summary.worst_server = worst.target


# ---------------------------------------------------------------------------
# Export Engine
# ---------------------------------------------------------------------------


class ExportEngine:
    """Unified export engine producing JSON, CSV, HTML, PDF.

    All methods accept a :class:`ReportData` and produce output
    in the requested format.

    Example::

        engine = ExportEngine()
        report = ReportData(title="My Report")
        report.add_measurement(...)

        json_str = engine.to_json(report)
        csv_str = engine.to_csv(report)
        html_str = engine.to_html(report)
        engine.save(report, "report.html")
    """

    def to_json(self, report: ReportData, indent: int = 2) -> str:
        """Export report to JSON string.

        Args:
            report: Report data.
            indent: JSON indentation.

        Returns:
            JSON string.
        """
        return json.dumps(
            report.to_dict(), indent=indent, ensure_ascii=False, default=str
        )

    def to_csv(self, report: ReportData) -> str:
        """Export report to CSV string (measurements table).

        Args:
            report: Report data.

        Returns:
            CSV string with measurements.
        """
        output = io.StringIO()
        if report.measurements:
            fieldnames = list(report.measurements[0].to_dict().keys())
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            for m in report.measurements:
                writer.writerow(m.to_dict())
        return output.getvalue()

    def to_html(self, report: ReportData) -> str:
        """Export report to HTML string.

        Generates a self-contained HTML document with inline CSS
        and all report sections.

        Args:
            report: Report data.

        Returns:
            Complete HTML document string.
        """
        h = report.header
        s = report.summary

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8'>",
            f"<title>{h.title}</title>",
            "<style>",
            _HTML_CSS,
            "</style>",
            "</head>",
            "<body>",
            f"<h1>{h.title}</h1>",
            f"<p class='meta'>Generated: {h.generated_at} | "
            f"Version: {h.app_version}</p>",
            # Summary
            "<h2>Summary</h2>",
            "<table>",
            f"<tr><td>Total Servers</td><td>{s.total_servers}</td></tr>",
            f"<tr><td>Total Measurements</td><td>{s.total_measurements}</td></tr>",
            f"<tr><td>Total Errors</td><td>{s.total_errors}</td></tr>",
            f"<tr><td>Average RTT</td><td>{s.avg_rtt:.1f} ms</td></tr>",
            f"<tr><td>Average Loss</td><td>{s.avg_loss:.1f}%</td></tr>",
            f"<tr><td>Average Jitter</td><td>{s.avg_jitter:.1f} ms</td></tr>",
            f"<tr><td>Best Server</td><td>{s.best_server}</td></tr>",
            f"<tr><td>Worst Server</td><td>{s.worst_server}</td></tr>",
            "</table>",
        ]

        # Servers
        if report.servers:
            html_parts.extend(
                [
                    "<h2>Servers</h2>",
                    "<table>",
                    "<tr><th>Rank</th><th>Host</th><th>Name</th><th>Map</th>"
                    "<th>Players</th><th>Score</th></tr>",
                ]
            )
            for srv in report.servers:
                html_parts.append(
                    f"<tr><td>{srv.rank}</td><td>{srv.host}:{srv.port}</td>"
                    f"<td>{srv.name}</td><td>{srv.map_name}</td>"
                    f"<td>{srv.player_count}/{srv.max_players}</td>"
                    f"<td>{srv.final_score:.3f}</td></tr>"
                )
            html_parts.append("</table>")

        # Measurements
        if report.measurements:
            html_parts.extend(
                [
                    "<h2>Measurements</h2>",
                    "<table>",
                    "<tr><th>Target</th><th>Mode</th><th>Avg RTT</th>"
                    "<th>Loss</th><th>Jitter</th><th>Grade</th><th>Duration</th></tr>",
                ]
            )
            for m in report.measurements:
                html_parts.append(
                    f"<tr><td>{m.target}</td><td>{m.mode}</td>"
                    f"<td>{m.avg_rtt:.1f} ms</td>"
                    f"<td>{m.loss_percent:.1f}%</td>"
                    f"<td>{m.jitter:.1f} ms</td>"
                    f"<td>{m.grade}</td>"
                    f"<td>{m.duration:.1f}s</td></tr>"
                )
            html_parts.append("</table>")

        # Errors
        if report.errors:
            html_parts.extend(
                [
                    "<h2>Errors</h2>",
                    "<table>",
                    "<tr><th>Time</th><th>Host</th><th>Type</th>"
                    "<th>Message</th><th>Resolved</th></tr>",
                ]
            )
            for e in report.errors:
                ts = (
                    datetime.fromtimestamp(e.timestamp, tz=UTC).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                    if e.timestamp
                    else ""
                )
                resolved = "Yes" if e.resolved else "No"
                html_parts.append(
                    f"<tr><td>{ts}</td><td>{e.host}:{e.port}</td>"
                    f"<td>{e.error_type}</td><td>{e.message}</td>"
                    f"<td>{resolved}</td></tr>"
                )
            html_parts.append("</table>")

        html_parts.extend(["</body>", "</html>"])
        return "\n".join(html_parts)

    def save(
        self,
        report: ReportData,
        filepath: str | Path,
        fmt: str | None = None,
    ) -> Path:
        """Export report to a file.

        Auto-detects format from file extension if fmt is None.

        Args:
            report: Report data.
            filepath: Output file path.
            fmt: Format override ('json', 'csv', 'html').

        Returns:
            Path to the written file.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        if fmt is None:
            fmt = path.suffix.lstrip(".").lower()

        content: str
        if fmt == "json":
            content = self.to_json(report)
        elif fmt == "csv":
            content = self.to_csv(report)
        elif fmt == "html":
            content = self.to_html(report)
        else:
            raise ValueError(f"Unsupported export format: {fmt!r}")

        path.write_text(content, encoding="utf-8")
        logger.info("Report exported to %s (%s)", path, fmt)
        return path


# ---------------------------------------------------------------------------
# HTML CSS
# ---------------------------------------------------------------------------

_HTML_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    max-width: 960px;
    margin: 0 auto;
    padding: 20px;
    background: #fafafa;
    color: #333;
}
h1 {
    color: #1a1a2e;
    border-bottom: 2px solid #4ade80;
    padding-bottom: 8px;
}
h2 {
    color: #2d2d44;
    margin-top: 24px;
}
.meta {
    color: #666;
    font-size: 13px;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
}
th, td {
    border: 1px solid #ddd;
    padding: 8px 12px;
    text-align: left;
}
th {
    background: #4ade80;
    color: white;
    font-weight: 600;
}
tr:nth-child(even) {
    background: #f5f5f5;
}
tr:hover {
    background: #e8f5e9;
}
"""
