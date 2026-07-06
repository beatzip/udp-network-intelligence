"""Tests for the History Repository."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from uni.core.history.repository import (
    ErrorRecord,
    HistoryRepository,
    MeasurementRecord,
    RankingRecord,
    ServerRecord,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def repo(tmp_path: Path) -> HistoryRepository:
    """Create and initialize a temporary repository."""
    db = tmp_path / "test.db"
    r = HistoryRepository(str(db))
    await r.initialize()
    yield r  # type: ignore[misc]
    await r.close()


@pytest.fixture
def sample_measurement() -> MeasurementRecord:
    return MeasurementRecord(
        target_host="10.0.0.1",
        target_port=27015,
        timestamp=time.time(),
        mode="normal",
        sent=50,
        received=48,
        lost=2,
        min_rtt=10.0,
        max_rtt=50.0,
        avg_rtt=18.5,
        jitter=3.2,
        quality_grade="A",
        quality_score=0.92,
        duration_seconds=25.0,
    )


@pytest.fixture
def sample_server() -> ServerRecord:
    return ServerRecord(
        host="10.0.0.1",
        port=27015,
        name="Test Server",
        map_name="de_dust2",
        game="csgo",
        app_id=730,
        player_count=10,
        max_players=20,
    )


@pytest.fixture
def sample_error() -> ErrorRecord:
    return ErrorRecord(
        timestamp=time.time(),
        host="10.0.0.1",
        port=27015,
        error_type="timeout",
        error_message="Connection timed out after 3s",
    )


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    @pytest.mark.asyncio
    async def test_initialize_creates_db(self, tmp_path: Path) -> None:
        db = tmp_path / "new.db"
        assert not db.exists()
        repo = HistoryRepository(str(db))
        await repo.initialize()
        assert db.exists()
        await repo.close()

    @pytest.mark.asyncio
    async def test_double_initialize(self, repo: HistoryRepository) -> None:
        await repo.initialize()  # Should not raise

    @pytest.mark.asyncio
    async def test_close(self, repo: HistoryRepository) -> None:
        await repo.close()
        assert repo.is_initialized is False


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------

class TestMeasurements:
    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: HistoryRepository, sample_measurement: MeasurementRecord) -> None:
        row_id = await repo.save_measurement(sample_measurement)
        assert row_id > 0

        record = await repo.get_measurement(row_id)
        assert record is not None
        assert record.target_host == "10.0.0.1"
        assert record.avg_rtt == 18.5
        assert record.quality_grade == "A"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, repo: HistoryRepository) -> None:
        assert await repo.get_measurement(99999) is None

    @pytest.mark.asyncio
    async def test_list_measurements(self, repo: HistoryRepository, sample_measurement: MeasurementRecord) -> None:
        await repo.save_measurement(sample_measurement)
        results = await repo.get_measurements()
        assert len(results) == 1
        assert results[0].target_host == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_filter_by_host(self, repo: HistoryRepository) -> None:
        m1 = MeasurementRecord(target_host="10.0.0.1", timestamp=1.0)
        m2 = MeasurementRecord(target_host="10.0.0.2", timestamp=2.0)
        await repo.save_measurement(m1)
        await repo.save_measurement(m2)

        results = await repo.get_measurements(host="10.0.0.1")
        assert len(results) == 1
        assert results[0].target_host == "10.0.0.1"

    @pytest.mark.asyncio
    async def test_filter_by_time(self, repo: HistoryRepository) -> None:
        m1 = MeasurementRecord(target_host="a", timestamp=100.0)
        m2 = MeasurementRecord(target_host="b", timestamp=200.0)
        m3 = MeasurementRecord(target_host="c", timestamp=300.0)
        await repo.save_measurement(m1)
        await repo.save_measurement(m2)
        await repo.save_measurement(m3)

        results = await repo.get_measurements(start_time=150.0, end_time=250.0)
        assert len(results) == 1
        assert results[0].target_host == "b"

    @pytest.mark.asyncio
    async def test_count(self, repo: HistoryRepository, sample_measurement: MeasurementRecord) -> None:
        assert await repo.count_measurements() == 0
        await repo.save_measurement(sample_measurement)
        assert await repo.count_measurements() == 1

    @pytest.mark.asyncio
    async def test_delete(self, repo: HistoryRepository, sample_measurement: MeasurementRecord) -> None:
        await repo.save_measurement(sample_measurement)
        deleted = await repo.delete_measurements("10.0.0.1")
        assert deleted == 1
        assert await repo.count_measurements() == 0

    @pytest.mark.asyncio
    async def test_loss_rate(self, sample_measurement: MeasurementRecord) -> None:
        assert sample_measurement.loss_rate == pytest.approx(0.04)
        assert sample_measurement.loss_percent == pytest.approx(4.0)
        assert sample_measurement.success_rate == pytest.approx(0.96)

    @pytest.mark.asyncio
    async def test_to_dict(self, sample_measurement: MeasurementRecord) -> None:
        d = sample_measurement.to_dict()
        assert d["target_host"] == "10.0.0.1"
        assert d["mode"] == "normal"


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------

class TestServers:
    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: HistoryRepository, sample_server: ServerRecord) -> None:
        await repo.save_server(sample_server)
        record = await repo.get_server("10.0.0.1", 27015)
        assert record is not None
        assert record.name == "Test Server"
        assert record.app_id == 730

    @pytest.mark.asyncio
    async def test_upsert(self, repo: HistoryRepository, sample_server: ServerRecord) -> None:
        await repo.save_server(sample_server)
        # Update player count
        sample_server.player_count = 15
        await repo.save_server(sample_server)

        record = await repo.get_server("10.0.0.1", 27015)
        assert record is not None
        assert record.player_count == 15
        assert record.name == "Test Server"  # preserved

    @pytest.mark.asyncio
    async def test_list_servers(self, repo: HistoryRepository) -> None:
        for i in range(5):
            await repo.save_server(ServerRecord(host=f"10.0.0.{i}", port=27015))
        servers = await repo.get_servers(limit=3)
        assert len(servers) == 3

    @pytest.mark.asyncio
    async def test_search(self, repo: HistoryRepository) -> None:
        await repo.save_server(ServerRecord(host="1.2.3.4", port=27015, name="Faceit Server"))
        await repo.save_server(ServerRecord(host="5.6.7.8", port=27015, name="Random Server"))

        results = await repo.search_servers("Faceit")
        assert len(results) == 1
        assert results[0].name == "Faceit Server"

    @pytest.mark.asyncio
    async def test_count(self, repo: HistoryRepository, sample_server: ServerRecord) -> None:
        assert await repo.count_servers() == 0
        await repo.save_server(sample_server)
        assert await repo.count_servers() == 1

    @pytest.mark.asyncio
    async def test_delete(self, repo: HistoryRepository, sample_server: ServerRecord) -> None:
        await repo.save_server(sample_server)
        deleted = await repo.delete_server("10.0.0.1", 27015)
        assert deleted is True
        assert await repo.get_server("10.0.0.1", 27015) is None


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------

class TestRankings:
    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: HistoryRepository) -> None:
        ranking = RankingRecord(
            host="10.0.0.1", port=27015, timestamp=time.time(),
            final_score=0.95, rank=1, total_servers=5,
        )
        row_id = await repo.save_ranking(ranking)
        assert row_id > 0

        results = await repo.get_rankings(host="10.0.0.1")
        assert len(results) == 1
        assert results[0].final_score == 0.95

    @pytest.mark.asyncio
    async def test_latest_rankings(self, repo: HistoryRepository) -> None:
        # Save two ranking snapshots
        for i in range(3):
            await repo.save_ranking(RankingRecord(
                host=f"10.0.0.{i}", port=27015,
                timestamp=100.0, final_score=0.9 - i * 0.1, rank=i + 1,
            ))
        await repo.save_ranking(RankingRecord(
            host="10.0.0.9", port=27015,
            timestamp=200.0, final_score=0.99, rank=1,
        ))

        latest = await repo.get_latest_rankings()
        assert len(latest) == 1
        assert latest[0].host == "10.0.0.9"

    @pytest.mark.asyncio
    async def test_count(self, repo: HistoryRepository) -> None:
        assert await repo.count_rankings() == 0
        await repo.save_ranking(RankingRecord(host="a", timestamp=1.0))
        assert await repo.count_rankings() == 1


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class TestErrors:
    @pytest.mark.asyncio
    async def test_save_and_get(self, repo: HistoryRepository, sample_error: ErrorRecord) -> None:
        row_id = await repo.save_error(sample_error)
        assert row_id > 0

        results = await repo.get_errors(host="10.0.0.1")
        assert len(results) == 1
        assert results[0].error_type == "timeout"

    @pytest.mark.asyncio
    async def test_mark_resolved(self, repo: HistoryRepository, sample_error: ErrorRecord) -> None:
        row_id = await repo.save_error(sample_error)
        updated = await repo.mark_error_resolved(row_id)
        assert updated is True

        results = await repo.get_errors(resolved=True)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_filter_by_type(self, repo: HistoryRepository) -> None:
        await repo.save_error(ErrorRecord(timestamp=1.0, error_type="timeout"))
        await repo.save_error(ErrorRecord(timestamp=2.0, error_type="connection_refused"))

        results = await repo.get_errors(error_type="timeout")
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_count(self, repo: HistoryRepository, sample_error: ErrorRecord) -> None:
        assert await repo.count_errors() == 0
        await repo.save_error(sample_error)
        assert await repo.count_errors() == 1
        assert await repo.count_errors(resolved=False) == 1

    @pytest.mark.asyncio
    async def test_delete_old(self, repo: HistoryRepository) -> None:
        await repo.save_error(ErrorRecord(timestamp=100.0, resolved=True))
        await repo.save_error(ErrorRecord(timestamp=200.0, resolved=False))

        deleted = await repo.delete_old_errors(150.0)
        assert deleted == 1
        remaining = await repo.get_errors()
        assert len(remaining) == 1

    @pytest.mark.asyncio
    async def test_to_dict(self, sample_error: ErrorRecord) -> None:
        d = sample_error.to_dict()
        assert d["error_type"] == "timeout"
        assert d["resolved"] is False


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

class TestStats:
    @pytest.mark.asyncio
    async def test_empty_stats(self, repo: HistoryRepository) -> None:
        stats = await repo.get_stats()
        assert stats["measurements_total"] == 0
        assert stats["servers_total"] == 0
        assert stats["errors_total"] == 0

    @pytest.mark.asyncio
    async def test_populated_stats(self, repo: HistoryRepository) -> None:
        await repo.save_measurement(MeasurementRecord(
            target_host="a", avg_rtt=15.0, quality_score=0.9,
        ))
        await repo.save_server(ServerRecord(host="b", port=80))
        await repo.save_error(ErrorRecord(error_type="timeout"))

        stats = await repo.get_stats()
        assert stats["measurements_total"] == 1
        assert stats["servers_total"] == 1
        assert stats["errors_total"] == 1
        assert stats["measurements_avg_rtt"] == 15.0
