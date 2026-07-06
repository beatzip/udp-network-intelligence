"""Tests for the Probe Engine — server testing system."""

from __future__ import annotations

import asyncio
import time

import pytest

from uni.app.constants import QualityGrade
from uni.core.probe.engine import (
    MODE_AGGRESSIVE,
    MODE_DEEP,
    MODE_NORMAL,
    CampaignResult,
    ParallelTestResult,
    ProbeEngine,
    ProbeTarget,
    RateLimiter,
    RetryConfig,
    RetryStrategy,
    TestMode,
    TestModeConfig,
)
from uni.core.probe.models import ProbeStats

# ---------------------------------------------------------------------------
# TestMode
# ---------------------------------------------------------------------------

class TestTestMode:
    """Tests for TestMode enum."""

    def test_values(self) -> None:
        assert TestMode.NORMAL.value == "normal"
        assert TestMode.DEEP.value == "deep"
        assert TestMode.AGGRESSIVE.value == "aggressive"

    def test_to_dict(self) -> None:
        assert TestMode.NORMAL.to_dict() == "normal"

    def test_from_dict(self) -> None:
        assert TestMode.from_dict("deep") == TestMode.DEEP


# ---------------------------------------------------------------------------
# TestModeConfig
# ---------------------------------------------------------------------------

class TestTestModeConfig:
    """Tests for TestModeConfig."""

    def test_mode_normal(self) -> None:
        assert MODE_NORMAL.count == 20
        assert MODE_NORMAL.interval == 1.0
        assert MODE_NORMAL.timeout == 3.0
        assert MODE_NORMAL.label == "Normal"

    def test_mode_deep(self) -> None:
        assert MODE_DEEP.count == 100
        assert MODE_DEEP.interval == 0.5

    def test_mode_aggressive(self) -> None:
        assert MODE_AGGRESSIVE.count == 200
        assert MODE_AGGRESSIVE.interval == 0.2
        assert MODE_AGGRESSIVE.max_retries == 1


# ---------------------------------------------------------------------------
# ProbeTarget
# ---------------------------------------------------------------------------

class TestProbeTarget:
    """Tests for ProbeTarget."""

    def test_str(self) -> None:
        t = ProbeTarget(host="1.2.3.4", port=27015)
        assert str(t) == "1.2.3.4:27015"

    def test_addr_tuple(self) -> None:
        t = ProbeTarget(host="10.0.0.1", port=9999)
        assert t.addr == ("10.0.0.1", 9999)

    def test_default_port(self) -> None:
        t = ProbeTarget(host="10.0.0.1")
        assert t.port == 27015


# ---------------------------------------------------------------------------
# RateLimiter
# ---------------------------------------------------------------------------

class TestRateLimiter:
    """Tests for RateLimiter."""

    @pytest.mark.asyncio
    async def test_acquire(self) -> None:
        limiter = RateLimiter(rate=1000.0)
        await limiter.acquire()  # Should not block

    @pytest.mark.asyncio
    async def test_rate_limiting(self) -> None:
        limiter = RateLimiter(rate=10.0, max_burst=10.0)
        start = time.monotonic()
        for _ in range(5):
            await limiter.acquire()
        elapsed = time.monotonic() - start
        # Should be near-instant since burst allows 10
        assert elapsed < 0.5

    @pytest.mark.asyncio
    async def test_burst_exhaustion(self) -> None:
        limiter = RateLimiter(rate=2.0, max_burst=2.0)
        # Exhaust burst
        await limiter.acquire()
        await limiter.acquire()
        # Next should wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.3  # Should have waited

    def test_invalid_rate(self) -> None:
        with pytest.raises(ValueError, match="Rate must be"):
            RateLimiter(rate=0)

    def test_available(self) -> None:
        limiter = RateLimiter(rate=100.0, max_burst=100.0)
        assert limiter.available >= 99.0


# ---------------------------------------------------------------------------
# RetryConfig
# ---------------------------------------------------------------------------

class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_none_strategy(self) -> None:
        cfg = RetryConfig(strategy=RetryStrategy.NONE)
        assert cfg.get_delay(0) == 0.0

    def test_fixed_strategy(self) -> None:
        cfg = RetryConfig(strategy=RetryStrategy.FIXED, base_delay=1.0)
        assert cfg.get_delay(0) == 1.0
        assert cfg.get_delay(5) == 1.0

    def test_linear_strategy(self) -> None:
        cfg = RetryConfig(
            strategy=RetryStrategy.LINEAR, base_delay=0.5, max_delay=3.0
        )
        assert cfg.get_delay(0) == 0.5
        assert cfg.get_delay(1) == 1.0
        assert cfg.get_delay(10) == 3.0  # capped

    def test_exponential_strategy(self) -> None:
        cfg = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=0.5,
            backoff=2.0,
            max_delay=10.0,
        )
        assert cfg.get_delay(0) == 0.5
        assert cfg.get_delay(1) == 1.0
        assert cfg.get_delay(2) == 2.0
        assert cfg.get_delay(3) == 4.0
        assert cfg.get_delay(10) == 10.0  # capped


# ---------------------------------------------------------------------------
# CampaignResult
# ---------------------------------------------------------------------------

class TestCampaignResult:
    """Tests for CampaignResult."""

    def test_empty_result(self) -> None:
        r = CampaignResult(target=ProbeTarget("1.2.3.4"), mode=TestMode.NORMAL)
        assert r.is_success is False
        assert r.sent == 0
        assert r.duration_seconds == 0.0

    def test_with_stats(self) -> None:
        stats = ProbeStats()
        stats.sent = 10
        stats.received = 9
        stats.lost = 1
        r = CampaignResult(
            target=ProbeTarget("1.2.3.4"),
            mode=TestMode.NORMAL,
            stats=stats,
            start_time=100.0,
            end_time=105.0,
        )
        assert r.sent == 10
        assert r.received == 9
        assert r.loss_percent == pytest.approx(10.0)
        assert r.duration_seconds == 5.0

    def test_to_dict(self) -> None:
        r = CampaignResult(target=ProbeTarget("1.2.3.4"), mode=TestMode.DEEP)
        d = r.to_dict()
        assert d["target"] == "1.2.3.4:27015"
        assert d["mode"] == "deep"


# ---------------------------------------------------------------------------
# ParallelTestResult
# ---------------------------------------------------------------------------

class TestParallelTestResult:
    """Tests for ParallelTestResult."""

    def test_empty(self) -> None:
        r = ParallelTestResult()
        assert r.success_rate == 0.0
        assert r.total_targets == 0

    def test_success_rate(self) -> None:
        r = ParallelTestResult(total_targets=10, completed=8, failed=2)
        assert r.success_rate == 0.8


# ---------------------------------------------------------------------------
# ProbeEngine — quick tests (with mock server)
# ---------------------------------------------------------------------------

class TestProbeEngine:
    """Tests for ProbeEngine with loopback echo server."""

    @pytest.fixture
    def engine(self) -> ProbeEngine:
        return ProbeEngine()

    @pytest.mark.asyncio
    async def test_test_normal_unreachable(self, engine: ProbeEngine) -> None:
        """Test normal mode against unreachable host."""
        result = await engine.test_normal("192.0.2.1", 9999)
        assert result.mode == TestMode.NORMAL
        assert not result.is_success or result.loss_percent > 50

    @pytest.mark.asyncio
    async def test_run_campaign_custom_config(self, engine: ProbeEngine) -> None:
        """Test campaign with custom config."""
        cfg = TestModeConfig(count=5, interval=0.01, timeout=0.1, label="Test")
        target = ProbeTarget("192.0.2.1", 9999)
        result = await engine.run_campaign(target, config=cfg)
        assert result.mode == TestMode.NORMAL
        assert len(result.results) == 5

    @pytest.mark.asyncio
    async def test_parallel_unreachable(self, engine: ProbeEngine) -> None:
        """Test parallel mode against unreachable hosts."""
        targets = [
            ProbeTarget("192.0.2.1", 9999),
            ProbeTarget("192.0.2.2", 9999),
        ]
        cfg = TestModeConfig(count=2, interval=0.01, timeout=0.1)
        result = await engine.test_parallel(
            targets, max_concurrent=2, config=cfg
        )
        assert result.total_targets == 2
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_loopback_echo(self, engine: ProbeEngine) -> None:
        """Full test with a loopback echo server."""
        # Create echo server
        server_sock = __import__("socket").socket(
            __import__("socket").AF_INET, __import__("socket").SOCK_DGRAM
        )
        server_sock.setblocking(False)
        server_sock.bind(("127.0.0.1", 0))
        server_port = server_sock.getsockname()[1]

        loop = asyncio.get_event_loop()
        echo_task = loop.create_task(_echo_server(server_sock))

        try:
            target = ProbeTarget("127.0.0.1", server_port)
            cfg = TestModeConfig(count=10, interval=0.01, timeout=1.0)
            result = await engine.run_campaign(target, config=cfg)

            assert result.is_success
            assert result.sent == 10
            assert result.received >= 8  # Allow some loss
            assert result.avg_rtt >= 0
            assert result.quality.grade in list(QualityGrade)
        finally:
            echo_task.cancel()
            server_sock.close()

    @pytest.mark.asyncio
    async def test_parallel_with_echo(self, engine: ProbeEngine) -> None:
        """Parallel test with loopback echo servers."""
        server1 = __import__("socket").socket(
            __import__("socket").AF_INET, __import__("socket").SOCK_DGRAM
        )
        server1.setblocking(False)
        server1.bind(("127.0.0.1", 0))
        port1 = server1.getsockname()[1]

        server2 = __import__("socket").socket(
            __import__("socket").AF_INET, __import__("socket").SOCK_DGRAM
        )
        server2.setblocking(False)
        server2.bind(("127.0.0.1", 0))
        port2 = server2.getsockname()[1]

        loop = asyncio.get_event_loop()
        t1 = loop.create_task(_echo_server(server1))
        t2 = loop.create_task(_echo_server(server2))

        try:
            targets = [
                ProbeTarget("127.0.0.1", port1, "Server1"),
                ProbeTarget("127.0.0.1", port2, "Server2"),
            ]
            cfg = TestModeConfig(count=5, interval=0.01, timeout=1.0)
            result = await engine.test_parallel(targets, max_concurrent=2, config=cfg)

            assert result.total_targets == 2
            assert result.completed == 2
            assert result.failed == 0
        finally:
            t1.cancel()
            t2.cancel()
            server1.close()
            server2.close()

    @pytest.mark.asyncio
    async def test_retry_config_passed(self, engine: ProbeEngine) -> None:
        """Test that retry config is respected."""
        retry = RetryConfig(
            strategy=RetryStrategy.EXPONENTIAL,
            max_retries=1,
            base_delay=0.01,
        )
        cfg = TestModeConfig(count=3, interval=0.01, timeout=0.05)
        target = ProbeTarget("192.0.2.1", 9999)
        result = await engine.run_campaign(
            target, config=cfg, retry=retry
        )
        assert len(result.results) == 3

    def test_compute_quality_perfect(self) -> None:
        """Test quality computation with perfect stats."""
        stats = ProbeStats()
        stats.sent = 100
        stats.received = 100
        stats.avg_rtt = 10.0
        stats.min_rtt = 8.0
        stats.max_rtt = 15.0
        stats.jitter = 2.0
        stats.lost = 0
        stats._rtt_sum = 1000.0
        stats._rtt_count = 100

        quality = ProbeEngine._compute_quality(stats)
        assert quality.grade == QualityGrade.A_PLUS
        assert quality.overall_score >= 90

    def test_compute_quality_poor(self) -> None:
        """Test quality computation with poor stats."""
        stats = ProbeStats()
        stats.sent = 100
        stats.received = 50
        stats.avg_rtt = 500.0
        stats.min_rtt = 100.0
        stats.max_rtt = 800.0
        stats.jitter = 100.0
        stats.lost = 50
        stats._rtt_sum = 25000.0
        stats._rtt_count = 50

        quality = ProbeEngine._compute_quality(stats)
        assert quality.grade in (QualityGrade.D, QualityGrade.F)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _echo_server(sock: __import__("socket").socket) -> None:
    """Simple UDP echo server for testing."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            data, addr = await loop.sock_recvfrom(sock, 4096)
            await loop.sock_sendto(sock, data, addr)
        except (asyncio.CancelledError, OSError):
            break
