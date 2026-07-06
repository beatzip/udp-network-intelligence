"""UDP Probe Engine — orchestrates server testing campaigns.

Provides :class:`ProbeEngine` for executing structured UDP probe
campaigns against game servers. Supports Normal, Deep, and Aggressive
testing modes, configurable intervals, parallel target testing,
rate limiting, and retry strategies.

Testing Modes
-------------

- **Normal**: 20 probes, 1s interval, 3s timeout. Standard quality check.
- **Deep**: 100 probes, 0.5s interval, 3s timeout. Detailed analysis.
- **Aggressive**: 200 probes, 0.2s interval, 5s timeout. Stress test.

Example::

    engine = ProbeEngine()
    result = await engine.test_normal("1.2.3.4", 27015)
    print(f"Grade: {result.quality.grade}, RTT: {result.stats.avg_rtt:.1f}ms")
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from uni.core.analysis.models import QualityReport
from uni.core.probe.models import (
    ProbeResult,
    ProbeStats,
    ProbeStatus,
)
from uni.net.udp_socket import AsyncUDPSocket, SendResult, SocketConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Test modes
# ---------------------------------------------------------------------------

class TestMode(Enum):
    """Server testing intensity modes."""

    NORMAL = "normal"
    DEEP = "deep"
    AGGRESSIVE = "aggressive"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> TestMode:
        """Deserialize from string."""
        return cls(value)


@dataclass(frozen=True, slots=True)
class TestModeConfig:
    """Configuration for a specific test mode.

    Attributes:
        count: Number of probe packets to send.
        interval: Seconds between probes.
        timeout: Response timeout per probe.
        payload_size: UDP payload size in bytes.
        ttl: IP Time-To-Live.
        max_retries: Retries per probe on timeout.
        label: Human-readable mode label.
    """

    count: int
    interval: float
    timeout: float
    payload_size: int = 64
    ttl: int = 0
    max_retries: int = 0
    label: str = ""


# Predefined mode configurations
MODE_NORMAL = TestModeConfig(
    count=20, interval=1.0, timeout=3.0, label="Normal"
)
MODE_DEEP = TestModeConfig(
    count=100, interval=0.5, timeout=3.0, label="Deep"
)
MODE_AGGRESSIVE = TestModeConfig(
    count=200, interval=0.2, timeout=5.0, max_retries=1, label="Aggressive"
)

_MODE_MAP: dict[TestMode, TestModeConfig] = {
    TestMode.NORMAL: MODE_NORMAL,
    TestMode.DEEP: MODE_DEEP,
    TestMode.AGGRESSIVE: MODE_AGGRESSIVE,
}


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------

class RateLimiter:
    """Token-bucket rate limiter for controlling probe send rate.

    Ensures that probes are sent at most ``rate`` per second.
    Thread-safe via asyncio lock.

    Attributes:
        rate: Maximum tokens per second.
        tokens: Current available tokens.
        max_tokens: Maximum burst size.

    Example::

        limiter = RateLimiter(rate=100.0)
        await limiter.acquire()  # blocks until a token is available
    """

    def __init__(self, rate: float, max_burst: float | None = None) -> None:
        """Initialize the rate limiter.

        Args:
            rate: Tokens per second.
            max_burst: Maximum burst size. Defaults to ``rate``.
        """
        if rate <= 0:
            raise ValueError(f"Rate must be > 0, got {rate}")
        self.rate = rate
        self.max_tokens = max_burst if max_burst is not None else rate
        self.tokens = self.max_tokens
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a token, blocking until one is available."""
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
            await asyncio.sleep(0.01)

    async def acquire_many(self, count: int) -> None:
        """Acquire multiple tokens.

        Args:
            count: Number of tokens to acquire.
        """
        for _ in range(count):
            await self.acquire()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self.tokens = min(self.max_tokens, self.tokens + elapsed * self.rate)
        self._last_refill = now

    @property
    def available(self) -> float:
        """Current available tokens (approximate)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        return min(self.max_tokens, self.tokens + elapsed * self.rate)


# ---------------------------------------------------------------------------
# Retry strategy
# ---------------------------------------------------------------------------

class RetryStrategy(Enum):
    """Retry behavior on probe failure."""

    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> RetryStrategy:
        """Deserialize from string."""
        return cls(value)


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        strategy: Retry strategy type.
        max_retries: Maximum number of retries per probe.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries.
        backoff: Multiplier for exponential backoff.
    """

    strategy: RetryStrategy = RetryStrategy.NONE
    max_retries: int = 0
    base_delay: float = 0.5
    max_delay: float = 5.0
    backoff: float = 2.0

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given retry attempt.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds.
        """
        if self.strategy == RetryStrategy.NONE:
            return 0.0
        if self.strategy == RetryStrategy.FIXED:
            return self.base_delay
        if self.strategy == RetryStrategy.LINEAR:
            return min(self.base_delay * (attempt + 1), self.max_delay)
        if self.strategy == RetryStrategy.EXPONENTIAL:
            return min(
                self.base_delay * (self.backoff ** attempt), self.max_delay
            )
        return 0.0


# ---------------------------------------------------------------------------
# Probe target
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProbeTarget:
    """A target server for probing.

    Attributes:
        host: IP address or hostname.
        port: UDP port.
        label: Optional human-readable label.
    """

    host: str
    port: int = 27015
    label: str = ""

    def __str__(self) -> str:
        """Target as ``host:port`` string."""
        return f"{self.host}:{self.port}"

    @property
    def addr(self) -> tuple[str, int]:
        """Address tuple for socket operations."""
        return (self.host, self.port)


# ---------------------------------------------------------------------------
# Probe campaign result
# ---------------------------------------------------------------------------

@dataclass
class CampaignResult:
    """Result of a complete probe campaign against one target.

    Contains all probe results, computed statistics, and quality
    assessment.

    Attributes:
        target: The probed target.
        mode: Test mode used.
        results: Individual probe results.
        stats: Aggregated statistics.
        quality: Quality assessment.
        start_time: Campaign start timestamp.
        end_time: Campaign end timestamp.
        error: Error message if the campaign failed.
    """

    target: ProbeTarget
    mode: TestMode
    results: list[ProbeResult] = field(default_factory=list)
    stats: ProbeStats = field(default_factory=ProbeStats)
    quality: QualityReport = field(default_factory=QualityReport)
    start_time: float = 0.0
    end_time: float = 0.0
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """True if the campaign completed without fatal error."""
        return self.error is None and len(self.results) > 0

    @property
    def duration_seconds(self) -> float:
        """Elapsed time of the campaign."""
        if self.end_time <= 0:
            return 0.0
        return self.end_time - self.start_time

    @property
    def sent(self) -> int:
        """Total probes sent."""
        return self.stats.sent

    @property
    def received(self) -> int:
        """Total probes received."""
        return self.stats.received

    @property
    def loss_percent(self) -> float:
        """Packet loss percentage."""
        return self.stats.loss_percent

    @property
    def avg_rtt(self) -> float:
        """Average RTT in milliseconds."""
        return self.stats.avg_rtt

    @property
    def min_rtt(self) -> float:
        """Minimum RTT in milliseconds."""
        return self.stats.min_rtt

    @property
    def max_rtt(self) -> float:
        """Maximum RTT in milliseconds."""
        return self.stats.max_rtt

    @property
    def jitter(self) -> float:
        """Inter-packet jitter in milliseconds."""
        return self.stats.jitter

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "target": str(self.target),
            "mode": self.mode.value,
            "sent": self.sent,
            "received": self.received,
            "loss_percent": round(self.loss_percent, 2),
            "avg_rtt": round(self.avg_rtt, 2),
            "min_rtt": round(self.min_rtt, 2),
            "max_rtt": round(self.max_rtt, 2),
            "jitter": round(self.jitter, 2),
            "grade": self.quality.grade.value,
            "duration_seconds": round(self.duration_seconds, 2),
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Parallel test result
# ---------------------------------------------------------------------------

@dataclass
class ParallelTestResult:
    """Result of testing multiple targets in parallel.

    Attributes:
        results: List of per-target CampaignResults.
        total_targets: Number of targets tested.
        completed: Number of completed tests.
        failed: Number of failed tests.
        start_time: When parallel testing started.
        end_time: When parallel testing completed.
    """

    results: list[CampaignResult] = field(default_factory=list)
    total_targets: int = 0
    completed: int = 0
    failed: int = 0
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration_seconds(self) -> float:
        """Elapsed time."""
        if self.end_time <= 0:
            return 0.0
        return self.end_time - self.start_time

    @property
    def success_rate(self) -> float:
        """Fraction of targets that responded."""
        if self.total_targets == 0:
            return 0.0
        return self.completed / self.total_targets

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_targets": self.total_targets,
            "completed": self.completed,
            "failed": self.failed,
            "success_rate": round(self.success_rate, 4),
            "duration_seconds": round(self.duration_seconds, 2),
            "results": [r.to_dict() for r in self.results],
        }


# ---------------------------------------------------------------------------
# ProbeEngine
# ---------------------------------------------------------------------------

ProgressCallback = Callable[[int, int, ProbeResult], Coroutine[Any, Any, None]]


class ProbeEngine:
    """UDP probe engine for server testing campaigns.

    Orchestrates probe campaigns against game servers with configurable
    modes, rate limiting, retry strategies, and parallel execution.

    Attributes:
        default_retry: Default retry configuration.
        default_rate_limit: Default rate limit (probes/second, 0=unlimited).

    Example::

        engine = ProbeEngine()
        result = await engine.test_normal("1.2.3.4", 27015)

        # Parallel
        targets = [ProbeTarget("10.0.0.1"), ProbeTarget("10.0.0.2")]
        parallel = await engine.test_parallel(targets, mode=TestMode.DEEP)
    """

    def __init__(
        self,
        default_retry: RetryConfig | None = None,
        default_rate_limit: float = 0,
    ) -> None:
        """Initialize the probe engine.

        Args:
            default_retry: Default retry configuration.
            default_rate_limit: Default rate limit (0 = unlimited).
        """
        self.default_retry = default_retry or RetryConfig()
        self.default_rate_limit = default_rate_limit

    # ------------------------------------------------------------------
    # Quick test methods
    # ------------------------------------------------------------------

    async def test_normal(
        self,
        host: str,
        port: int = 27015,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> CampaignResult:
        """Run a Normal probe campaign.

        20 probes, 1s interval, 3s timeout.

        Args:
            host: Target host.
            port: Target port.
            on_progress: Optional callback per probe.

        Returns:
            CampaignResult with statistics and quality.
        """
        target = ProbeTarget(host=host, port=port)
        return await self.run_campaign(
            target, TestMode.NORMAL, on_progress=on_progress
        )

    async def test_deep(
        self,
        host: str,
        port: int = 27015,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> CampaignResult:
        """Run a Deep probe campaign.

        100 probes, 0.5s interval, 3s timeout.

        Args:
            host: Target host.
            port: Target port.
            on_progress: Optional callback per probe.

        Returns:
            CampaignResult with statistics and quality.
        """
        target = ProbeTarget(host=host, port=port)
        return await self.run_campaign(
            target, TestMode.DEEP, on_progress=on_progress
        )

    async def test_aggressive(
        self,
        host: str,
        port: int = 27015,
        *,
        on_progress: ProgressCallback | None = None,
    ) -> CampaignResult:
        """Run an Aggressive probe campaign.

        200 probes, 0.2s interval, 5s timeout.

        Args:
            host: Target host.
            port: Target port.
            on_progress: Optional callback per probe.

        Returns:
            CampaignResult with statistics and quality.
        """
        target = ProbeTarget(host=host, port=port)
        return await self.run_campaign(
            target, TestMode.AGGRESSIVE, on_progress=on_progress
        )

    # ------------------------------------------------------------------
    # Core campaign runner
    # ------------------------------------------------------------------

    async def run_campaign(
        self,
        target: ProbeTarget,
        mode: TestMode = TestMode.NORMAL,
        *,
        config: TestModeConfig | None = None,
        retry: RetryConfig | None = None,
        rate_limit: float = 0,
        on_progress: ProgressCallback | None = None,
    ) -> CampaignResult:
        """Run a probe campaign against a single target.

        Args:
            target: Target to probe.
            mode: Testing mode (or use custom config).
            config: Custom mode config. Overrides mode preset.
            retry: Retry configuration. Uses engine default if None.
            rate_limit: Probes per second (0 = unlimited).
            on_progress: Callback after each probe.

        Returns:
            CampaignResult with all probe data and statistics.
        """
        cfg = config or _MODE_MAP.get(mode, MODE_NORMAL)
        retry_cfg = retry or self.default_retry
        effective_rate = rate_limit if rate_limit > 0 else self.default_rate_limit

        stats = ProbeStats()
        results: list[ProbeResult] = []
        limiter = RateLimiter(effective_rate) if effective_rate > 0 else None

        campaign_result = CampaignResult(
            target=target,
            mode=mode,
            start_time=time.monotonic(),
        )

        logger.info(
            "Campaign started: %s mode=%s count=%d",
            target, cfg.label, cfg.count,
        )

        socket_config = SocketConfig(
            host="0.0.0.0",
            port=0,
            timeout=cfg.timeout,
            ttl=cfg.ttl if cfg.ttl > 0 else 64,
        )

        try:
            async with AsyncUDPSocket(socket_config) as sock:
                for i in range(cfg.count):
                    # Rate limit
                    if limiter:
                        await limiter.acquire()

                    # Inter-probe delay
                    if i > 0 and cfg.interval > 0:
                        await asyncio.sleep(cfg.interval)

                    # Send probe with retry
                    result = await self._probe_with_retry(
                        sock, target, cfg, retry_cfg, i
                    )

                    stats.update(result)
                    results.append(result)

                    # Notify progress
                    if on_progress:
                        try:
                            await on_progress(i + 1, cfg.count, result)
                        except Exception:
                            logger.debug("Progress callback error", exc_info=True)

        except OSError as exc:
            campaign_result.error = str(exc)
            logger.warning("Campaign failed for %s: %s", target, exc)
        except Exception as exc:
            campaign_result.error = f"Unexpected: {exc}"
            logger.exception("Campaign error for %s", target)

        campaign_result.end_time = time.monotonic()
        campaign_result.results = results
        campaign_result.stats = stats

        # Compute quality
        campaign_result.quality = self._compute_quality(stats)

        logger.info(
            "Campaign completed: %s rtt=%.1fms loss=%.1f%% grade=%s",
            target,
            stats.avg_rtt,
            stats.loss_percent,
            campaign_result.quality.grade.value,
        )

        return campaign_result

    async def _probe_with_retry(
        self,
        sock: AsyncUDPSocket,
        target: ProbeTarget,
        cfg: TestModeConfig,
        retry_cfg: RetryConfig,
        sequence: int,
    ) -> ProbeResult:
        """Send a single probe with optional retry.

        Args:
            sock: Open UDP socket.
            target: Target to probe.
            cfg: Mode configuration.
            retry_cfg: Retry configuration.
            sequence: Probe sequence number.

        Returns:
            ProbeResult (best outcome from attempts).
        """
        last_result: ProbeResult | None = None
        payload = b"\x00" * cfg.payload_size

        for attempt in range(1 + retry_cfg.max_retries):
            pkt = await sock.send_receive(payload, target.addr, timeout=cfg.timeout)

            if pkt.is_success and pkt.rtt_ms is not None:
                return ProbeResult(
                    sequence=sequence,
                    rtt_ms=pkt.rtt_ms,
                    status=ProbeStatus.SUCCESS,
                    response_size=pkt.response_size,
                    timestamp=pkt.sent_time,
                    source_ip=pkt.source[0],
                    source_port=pkt.source[1],
                )

            status = ProbeStatus.TIMEOUT
            unreachable = (
                SendResult.CONNECTION_REFUSED,
                SendResult.NETWORK_UNREACHABLE,
            )
            if pkt.send_result in unreachable:
                status = ProbeStatus.UNREACHABLE

            last_result = ProbeResult(
                sequence=sequence,
                rtt_ms=None,
                status=status,
                response_size=0,
                timestamp=pkt.sent_time,
                source_ip=pkt.source[0],
                source_port=pkt.source[1],
            )

            if attempt < retry_cfg.max_retries:
                delay = retry_cfg.get_delay(attempt)
                if delay > 0:
                    await asyncio.sleep(delay)

        return last_result  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Parallel testing
    # ------------------------------------------------------------------

    async def test_parallel(
        self,
        targets: list[ProbeTarget],
        mode: TestMode = TestMode.NORMAL,
        *,
        max_concurrent: int = 10,
        config: TestModeConfig | None = None,
        retry: RetryConfig | None = None,
        rate_limit: float = 0,
        on_progress: (
            Callable[[str, int, int, ProbeResult], Coroutine[Any, Any, None]]
            | None
        ) = None,
    ) -> ParallelTestResult:
        """Test multiple targets in parallel.

        Args:
            targets: List of targets to probe.
            mode: Testing mode.
            max_concurrent: Maximum concurrent probe sessions.
            config: Custom mode config.
            retry: Retry configuration.
            rate_limit: Rate limit per target.
            on_progress: Callback(target_label, current, total, result).

        Returns:
            ParallelTestResult with all per-target results.
        """
        result = ParallelTestResult(
            total_targets=len(targets),
            start_time=time.monotonic(),
        )

        semaphore = asyncio.Semaphore(max_concurrent)

        async def _run_one(target: ProbeTarget) -> CampaignResult:
            async with semaphore:
                return await self.run_campaign(
                    target, mode, config=config, retry=retry,
                    rate_limit=rate_limit,
                )

        tasks = [_run_one(t) for t in targets]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for i, res in enumerate(completed):
            if isinstance(res, Exception):
                result.failed += 1
                target = targets[i]
                result.results.append(
                    CampaignResult(
                        target=target,
                        mode=mode,
                        error=str(res),
                        start_time=time.monotonic(),
                        end_time=time.monotonic(),
                    )
                )
            else:
                if res.is_success:
                    result.completed += 1
                else:
                    result.failed += 1
                result.results.append(res)

        result.end_time = time.monotonic()

        logger.info(
            "Parallel test: %d/%d succeeded in %.1fs",
            result.completed,
            result.total_targets,
            result.duration_seconds,
        )

        return result

    # ------------------------------------------------------------------
    # Quality computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_quality(stats: ProbeStats) -> QualityReport:
        """Compute quality grade from probe statistics.

        Uses weighted scoring of latency, loss, and jitter to produce
        a letter grade (A+ through F).

        Args:
            stats: Aggregated probe statistics.

        Returns:
            QualityReport with grade and component scores.
        """
        from uni.app.constants import (
            JITTER_A_THRESHOLD,
            JITTER_B_THRESHOLD,
            JITTER_C_THRESHOLD,
            JITTER_D_THRESHOLD,
            LOSS_A_THRESHOLD,
            LOSS_B_THRESHOLD,
            LOSS_C_THRESHOLD,
            LOSS_D_THRESHOLD,
            QUALITY_A_PLUS_THRESHOLD,
            QUALITY_A_THRESHOLD,
            QUALITY_B_PLUS_THRESHOLD,
            QUALITY_B_THRESHOLD,
            QUALITY_C_PLUS_THRESHOLD,
            QUALITY_C_THRESHOLD,
            QUALITY_D_THRESHOLD,
        )

        avg = stats.avg_rtt
        loss = stats.loss_percent
        jit = stats.jitter

        # Latency score (0-100)
        if avg <= QUALITY_A_PLUS_THRESHOLD:
            lat_score = 100.0
        elif avg <= QUALITY_A_THRESHOLD:
            lat_score = 90.0
        elif avg <= QUALITY_B_PLUS_THRESHOLD:
            lat_score = 80.0
        elif avg <= QUALITY_B_THRESHOLD:
            lat_score = 70.0
        elif avg <= QUALITY_C_PLUS_THRESHOLD:
            lat_score = 60.0
        elif avg <= QUALITY_C_THRESHOLD:
            lat_score = 50.0
        elif avg <= QUALITY_D_THRESHOLD:
            lat_score = 30.0
        else:
            lat_score = 10.0

        # Loss score
        if loss <= LOSS_A_THRESHOLD:
            loss_score = 100.0
        elif loss <= LOSS_B_THRESHOLD:
            loss_score = 80.0
        elif loss <= LOSS_C_THRESHOLD:
            loss_score = 60.0
        elif loss <= LOSS_D_THRESHOLD:
            loss_score = 40.0
        else:
            loss_score = 10.0

        # Jitter score
        if jit <= JITTER_A_THRESHOLD:
            jit_score = 100.0
        elif jit <= JITTER_B_THRESHOLD:
            jit_score = 80.0
        elif jit <= JITTER_C_THRESHOLD:
            jit_score = 60.0
        elif jit <= JITTER_D_THRESHOLD:
            jit_score = 40.0
        else:
            jit_score = 10.0

        # Weighted overall: 40% latency, 35% loss, 25% jitter
        overall = lat_score * 0.4 + loss_score * 0.35 + jit_score * 0.25

        # Map to grade
        if overall >= 92:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.A_PLUS
        elif overall >= 82:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.A
        elif overall >= 72:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.B_PLUS
        elif overall >= 62:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.B
        elif overall >= 52:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.C_PLUS
        elif overall >= 40:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.C
        elif overall >= 25:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.D
        else:
            from uni.app.constants import QualityGrade
            grade = QualityGrade.F

        return QualityReport(
            grade=grade,
            latency_score=lat_score,
            loss_score=loss_score,
            jitter_score=jit_score,
            overall_score=overall,
            avg_rtt_ms=avg,
            loss_percent=loss,
            jitter_ms=jit,
        )
