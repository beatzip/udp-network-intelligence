"""Tests for ViewModels — dashboard, servers, history."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6", reason="PySide6 required for ViewModel tests")

from uni.core.history.repository import (
    ErrorRecord,
    HistoryRepository,
    MeasurementRecord,
    ServerRecord,
)
from uni.viewmodel.base import BaseViewModel
from uni.viewmodel.dashboard_vm import DashboardViewModel
from uni.viewmodel.history_vm import HistoryViewModel
from uni.viewmodel.servers_vm import ServersViewModel

# ---------------------------------------------------------------------------
# BaseViewModel
# ---------------------------------------------------------------------------


class TestBaseViewModel:
    def test_initial_state(self) -> None:
        vm = BaseViewModel()
        assert vm.is_loading is False

    def test_emit_status(self) -> None:
        vm = BaseViewModel()
        received: list[str] = []
        vm.status_changed.connect(lambda s: received.append(s))
        vm.emit_status("test")
        assert received == ["test"]

    def test_emit_error(self) -> None:
        vm = BaseViewModel()
        received: list[str] = []
        vm.error_occurred.connect(lambda s: received.append(s))
        vm.emit_error("error msg")
        assert received == ["error msg"]


# ---------------------------------------------------------------------------
# DashboardViewModel
# ---------------------------------------------------------------------------


class TestDashboardViewModel:
    def test_update_stats(self) -> None:
        vm = DashboardViewModel()
        received: list[dict] = []
        vm.stats_updated.connect(lambda s: received.append(s))
        vm.update_stats({"total_servers": 5})
        assert len(received) == 1
        assert received[0]["total_servers"] == 5

    def test_add_chart_point(self) -> None:
        vm = DashboardViewModel()
        received: list = []
        vm.chart_data_updated.connect(
            lambda labels, vals: received.append((labels, vals))
        )
        vm.add_chart_point("t1", 10.0)
        assert len(received) == 1
        assert received[0] == (["t1"], [10.0])

    def test_chart_max_points(self) -> None:
        vm = DashboardViewModel()
        for i in range(250):
            vm.add_chart_point(f"t{i}", float(i))
        stats = vm.get_stats()
        assert isinstance(stats, dict)


# ---------------------------------------------------------------------------
# ServersViewModel
# ---------------------------------------------------------------------------


class TestServersViewModel:
    @pytest.mark.asyncio
    async def test_load_servers(self, tmp_path: Path) -> None:
        repo = HistoryRepository(str(tmp_path / "test.db"))
        await repo.initialize()
        await repo.save_server(ServerRecord(host="1.2.3.4", port=27015, name="Test"))

        vm = ServersViewModel(repo)
        received: list[list] = []
        vm.servers_updated.connect(lambda s: received.append(s))
        await vm.load_servers()
        assert len(received) == 1
        assert len(received[0]) == 1
        await repo.close()

    @pytest.mark.asyncio
    async def test_add_server(self, tmp_path: Path) -> None:
        repo = HistoryRepository(str(tmp_path / "test.db"))
        await repo.initialize()

        vm = ServersViewModel(repo)
        received: list[list] = []
        vm.servers_updated.connect(lambda s: received.append(s))
        await vm.add_server("10.0.0.1", 27015, "My Server")
        assert len(received) == 1
        assert len(received[0]) == 1
        await repo.close()

    @pytest.mark.asyncio
    async def test_delete_server(self, tmp_path: Path) -> None:
        repo = HistoryRepository(str(tmp_path / "test.db"))
        await repo.initialize()
        await repo.save_server(ServerRecord(host="1.2.3.4", port=27015))

        vm = ServersViewModel(repo)
        received: list[list] = []
        vm.servers_updated.connect(lambda s: received.append(s))
        await vm.delete_server("1.2.3.4", 27015)
        assert len(received) == 1
        assert len(received[0]) == 0
        await repo.close()

    def test_get_servers_empty(self) -> None:
        vm = ServersViewModel()
        assert vm.get_servers() == []


# ---------------------------------------------------------------------------
# HistoryViewModel
# ---------------------------------------------------------------------------


class TestHistoryViewModel:
    @pytest.mark.asyncio
    async def test_load_measurements(self, tmp_path: Path) -> None:
        repo = HistoryRepository(str(tmp_path / "test.db"))
        await repo.initialize()
        await repo.save_measurement(
            MeasurementRecord(
                target_host="1.2.3.4",
                avg_rtt=15.0,
            )
        )

        vm = HistoryViewModel(repo)
        received: list[list] = []
        vm.measurements_updated.connect(lambda m: received.append(m))
        await vm.load_measurements()
        assert len(received) == 1
        assert len(received[0]) == 1
        await repo.close()

    @pytest.mark.asyncio
    async def test_load_errors(self, tmp_path: Path) -> None:
        repo = HistoryRepository(str(tmp_path / "test.db"))
        await repo.initialize()
        await repo.save_error(ErrorRecord(error_type="timeout"))

        vm = HistoryViewModel(repo)
        received: list[list] = []
        vm.errors_updated.connect(lambda e: received.append(e))
        await vm.load_errors()
        assert len(received) == 1
        assert len(received[0]) == 1
        await repo.close()

    def test_export_csv_empty(self) -> None:
        vm = HistoryViewModel()
        assert vm.export_measurements_csv() == ""

    def test_export_json_empty(self) -> None:
        vm = HistoryViewModel()
        assert vm.export_measurements_json() == "[]"
