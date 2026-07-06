"""Tests for the unified export engine."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from uni.core.export import (
    ExportEngine,
    ReportData,
    ReportError,
    ReportHeader,
    ReportMeasurement,
    ReportServer,
    ReportSummary,
)

# ---------------------------------------------------------------------------
# ReportHeader
# ---------------------------------------------------------------------------


class TestReportHeader:
    def test_default_timestamp(self) -> None:
        h = ReportHeader()
        assert h.generated_at != ""

    def test_to_dict(self) -> None:
        h = ReportHeader(title="Test Report")
        d = h.to_dict()
        assert d["title"] == "Test Report"
        assert "generated_at" in d
        assert d["app_version"]


# ---------------------------------------------------------------------------
# ReportSummary
# ---------------------------------------------------------------------------


class TestReportSummary:
    def test_to_dict(self) -> None:
        s = ReportSummary(total_servers=5, avg_rtt=15.0)
        d = s.to_dict()
        assert d["total_servers"] == 5
        assert d["avg_rtt"] == 15.0


# ---------------------------------------------------------------------------
# ReportServer
# ---------------------------------------------------------------------------


class TestReportServer:
    def test_to_dict(self) -> None:
        srv = ReportServer(host="1.2.3.4", name="Test", rank=1)
        d = srv.to_dict()
        assert d["host"] == "1.2.3.4"
        assert d["rank"] == 1


# ---------------------------------------------------------------------------
# ReportMeasurement
# ---------------------------------------------------------------------------


class TestReportMeasurement:
    def test_to_dict(self) -> None:
        m = ReportMeasurement(
            target="1.2.3.4:27015",
            mode="normal",
            avg_rtt=15.0,
            grade="A",
        )
        d = m.to_dict()
        assert d["target"] == "1.2.3.4:27015"
        assert d["grade"] == "A"


# ---------------------------------------------------------------------------
# ReportError
# ---------------------------------------------------------------------------


class TestReportError:
    def test_to_dict(self) -> None:
        e = ReportError(host="1.2.3.4", error_type="timeout", message="Timed out")
        d = e.to_dict()
        assert d["error_type"] == "timeout"
        assert d["resolved"] is False


# ---------------------------------------------------------------------------
# ReportData
# ---------------------------------------------------------------------------


class TestReportData:
    def test_empty_report(self) -> None:
        r = ReportData()
        d = r.to_dict()
        assert "header" in d
        assert "summary" in d
        assert d["servers"] == []
        assert d["measurements"] == []

    def test_add_measurement_updates_summary(self) -> None:
        r = ReportData()
        r.add_measurement(
            ReportMeasurement(
                target="a:27015",
                avg_rtt=10.0,
                jitter=2.0,
                loss_percent=1.0,
                quality_score=0.9,
            )
        )
        r.add_measurement(
            ReportMeasurement(
                target="b:27015",
                avg_rtt=20.0,
                jitter=5.0,
                loss_percent=3.0,
                quality_score=0.6,
            )
        )
        assert r.summary.total_measurements == 2
        assert r.summary.avg_rtt == 15.0
        assert r.summary.best_server == "a:27015"

    def test_add_server(self) -> None:
        r = ReportData()
        r.add_server(ReportServer(host="1.2.3.4"))
        assert r.summary.total_servers == 1

    def test_add_error(self) -> None:
        r = ReportData()
        r.add_error(ReportError(error_type="timeout"))
        assert r.summary.total_errors == 1

    def test_to_dict_full(self) -> None:
        r = ReportData()
        r.add_measurement(ReportMeasurement(target="a", avg_rtt=10.0))
        r.add_server(ReportServer(host="a"))
        r.add_error(ReportError(error_type="timeout"))
        d = r.to_dict()
        assert len(d["measurements"]) == 1
        assert len(d["servers"]) == 1
        assert len(d["errors"]) == 1


# ---------------------------------------------------------------------------
# ExportEngine
# ---------------------------------------------------------------------------


class TestExportEngine:
    @pytest.fixture
    def engine(self) -> ExportEngine:
        return ExportEngine()

    @pytest.fixture
    def sample_report(self) -> ReportData:
        r = ReportData(header=ReportHeader(title="Test Report"))
        r.add_measurement(
            ReportMeasurement(
                target="10.0.0.1:27015",
                mode="normal",
                avg_rtt=15.0,
                min_rtt=10.0,
                max_rtt=25.0,
                jitter=3.0,
                loss_percent=2.0,
                sent=50,
                received=49,
                grade="A",
                quality_score=0.92,
                duration=25.0,
            )
        )
        r.add_measurement(
            ReportMeasurement(
                target="10.0.0.2:27015",
                mode="deep",
                avg_rtt=45.0,
                min_rtt=30.0,
                max_rtt=60.0,
                jitter=8.0,
                loss_percent=5.0,
                sent=100,
                received=95,
                grade="B",
                quality_score=0.75,
                duration=50.0,
            )
        )
        r.add_server(
            ReportServer(
                host="10.0.0.1",
                name="Fast Server",
                rank=1,
                final_score=0.95,
            )
        )
        r.add_server(
            ReportServer(
                host="10.0.0.2",
                name="Slow Server",
                rank=2,
                final_score=0.65,
            )
        )
        r.add_error(
            ReportError(
                timestamp=1000.0,
                host="10.0.0.2",
                error_type="timeout",
                message="Connection timed out",
            )
        )
        return r

    def test_to_json(self, engine: ExportEngine, sample_report: ReportData) -> None:
        json_str = engine.to_json(sample_report)
        data = json.loads(json_str)
        assert data["header"]["title"] == "Test Report"
        assert len(data["measurements"]) == 2
        assert len(data["servers"]) == 2
        assert data["summary"]["total_measurements"] == 2

    def test_to_csv(self, engine: ExportEngine, sample_report: ReportData) -> None:
        csv_str = engine.to_csv(sample_report)
        lines = csv_str.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "target" in lines[0]

    def test_to_csv_empty(self, engine: ExportEngine) -> None:
        csv_str = engine.to_csv(ReportData())
        assert csv_str == ""

    def test_to_html(self, engine: ExportEngine, sample_report: ReportData) -> None:
        html = engine.to_html(sample_report)
        assert "<!DOCTYPE html>" in html
        assert "Test Report" in html
        assert "10.0.0.1" in html
        assert "<table>" in html

    def test_save_json(
        self, engine: ExportEngine, sample_report: ReportData, tmp_path: Path
    ) -> None:
        path = engine.save(sample_report, tmp_path / "report.json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["header"]["title"] == "Test Report"

    def test_save_csv(
        self, engine: ExportEngine, sample_report: ReportData, tmp_path: Path
    ) -> None:
        path = engine.save(sample_report, tmp_path / "report.csv")
        assert path.exists()
        content = path.read_text()
        assert "target" in content

    def test_save_html(
        self, engine: ExportEngine, sample_report: ReportData, tmp_path: Path
    ) -> None:
        path = engine.save(sample_report, tmp_path / "report.html")
        assert path.exists()
        content = path.read_text()
        assert "<!DOCTYPE html>" in content

    def test_save_auto_detect_format(
        self, engine: ExportEngine, sample_report: ReportData, tmp_path: Path
    ) -> None:
        path = engine.save(sample_report, tmp_path / "report.json")
        assert path.exists()
        data = json.loads(path.read_text())
        assert "header" in data

    def test_save_unsupported_format(
        self, engine: ExportEngine, sample_report: ReportData, tmp_path: Path
    ) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            engine.save(sample_report, tmp_path / "report.xyz")

    def test_json_roundtrip(self, engine: ExportEngine) -> None:
        r1 = ReportData(header=ReportHeader(title="Roundtrip Test"))
        r1.add_measurement(ReportMeasurement(target="a", avg_rtt=10.0))
        json_str = engine.to_json(r1)
        data = json.loads(json_str)
        r2 = ReportData(
            header=ReportHeader(**data["header"]),
            summary=ReportSummary(**data["summary"]),
        )
        assert r2.header.title == "Roundtrip Test"
