"""Statistical analysis engine — RTT, loss, jitter, percentiles, EMA.

Provides :class:`StatsEngine` for computing network quality metrics
from raw probe samples. All calculations are pure math — no I/O,
no async, fully testable.

Implemented Metrics
-------------------

- **RTT statistics**: min, max, mean, median, variance, stddev
- **Packet loss**: count, rate, percentage
- **Jitter**: RFC 3550 interarrival jitter estimate
- **Percentiles**: p50, p95, p99, arbitrary percentile
- **Moving average**: simple moving average over a window
- **EMA**: exponential moving average with configurable alpha

All functions accept ``list[float]`` of RTT samples and return
scalar results. The :class:`StatsEngine` class maintains running
state for real-time computation.

Example::

    engine = StatsEngine()
    for rtt in probe_results:
        engine.add_sample(rtt)
    report = engine.get_report()
    print(f"p95={report.p95:.1f}ms jitter={report.jitter:.1f}ms")
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Pure functions (stateless)
# ---------------------------------------------------------------------------


def compute_mean(values: list[float]) -> float:
    """Arithmetic mean.

    Args:
        values: List of numeric values.

    Returns:
        Mean value, or 0.0 if the list is empty.

    Example::

        >>> compute_mean([10.0, 20.0, 30.0])
        20.0
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def compute_median(values: list[float]) -> float:
    """Median (50th percentile).

    Args:
        values: List of numeric values.

    Returns:
        Median value, or 0.0 if the list is empty.

    Example::

        >>> compute_median([1.0, 3.0, 5.0, 7.0, 9.0])
        5.0
    """
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return float(s[mid])


def compute_variance(values: list[float], ddof: int = 0) -> float:
    """Variance.

    Args:
        values: List of numeric values.
        ddof: Delta degrees of freedom (0 for population, 1 for sample).

    Returns:
        Variance, or 0.0 if the list is empty or has one element with ddof=1.

    Example::

        >>> compute_variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        4.0
    """
    n = len(values)
    if n <= ddof:
        return 0.0
    mean = sum(values) / n
    ss = sum((x - mean) ** 2 for x in values)
    return ss / (n - ddof)


def compute_stddev(values: list[float], ddof: int = 0) -> float:
    """Standard deviation.

    Args:
        values: List of numeric values.
        ddof: Delta degrees of freedom (0 for population, 1 for sample).

    Returns:
        Standard deviation, or 0.0 if insufficient data.

    Example::

        >>> compute_stddev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        2.0
    """
    return math.sqrt(compute_variance(values, ddof=ddof))


def compute_percentile(values: list[float], percentile: float) -> float:
    """Compute an arbitrary percentile using linear interpolation.

    Args:
        values: List of numeric values.
        percentile: Percentile to compute (0-100).

    Returns:
        Percentile value, or 0.0 if the list is empty.

    Example::

        >>> compute_percentile([1, 2, 3, 4, 5], 50)
        3.0
        >>> compute_percentile([1, 2, 3, 4, 5], 95)
        4.8
    """
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    if n == 1:
        return s[0]
    k = (percentile / 100.0) * (n - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return s[int(k)]
    return s[f] * (c - k) + s[c] * (k - f)


def compute_percentiles(
    values: list[float], percentiles: list[float]
) -> dict[float, float]:
    """Compute multiple percentiles at once.

    Args:
        values: List of numeric values.
        percentiles: List of percentile values (0-100).

    Returns:
        Dictionary mapping percentile to value.

    Example::

        >>> compute_percentiles([1,2,3,4,5], [50, 95, 99])
        {50: 3.0, 95: 4.8, 99: 4.96}
    """
    return {p: compute_percentile(values, p) for p in percentiles}


def compute_percentile_rank(values: list[float], value: float) -> float:
    """Compute the percentile rank of a value within a dataset.

    Args:
        values: List of numeric values.
        value: Value to rank.

    Returns:
        Percentile rank (0-100).

    Example::

        >>> compute_percentile_rank([1,2,3,4,5], 3)
        50.0
    """
    if not values:
        return 0.0
    count_below = sum(1 for v in values if v < value)
    count_equal = sum(1 for v in values if v == value)
    return ((count_below + 0.5 * count_equal) / len(values)) * 100.0


def compute_packet_loss(sent: int, received: int) -> float:
    """Packet loss rate as a fraction (0.0 to 1.0).

    Args:
        sent: Total packets sent.
        received: Total packets received.

    Returns:
        Loss rate from 0.0 (no loss) to 1.0 (100% loss).

    Example::

        >>> compute_packet_loss(100, 95)
        0.05
    """
    if sent <= 0:
        return 0.0
    return max(0.0, min(1.0, (sent - received) / sent))


def compute_loss_percent(sent: int, received: int) -> float:
    """Packet loss as a percentage (0.0 to 100.0).

    Args:
        sent: Total packets sent.
        received: Total packets received.

    Returns:
        Loss percentage.

    Example::

        >>> compute_loss_percent(100, 95)
        5.0
    """
    return compute_packet_loss(sent, received) * 100.0


def compute_jitter_rfc3550(samples: list[float], initial_jitter: float = 0.0) -> float:
    """Interarrival jitter per RFC 3550 (Appendix A.8).

    The interarrival jitter is defined as the mean deviation of the
    difference in packet spacing at the receiver compared to the
    sender. This is the standard metric used in VoIP and gaming
    quality assessment.

    Algorithm (RFC 3550):

        J(i) = J(i-1) + (|D(i-1,i)| - J(i-1)) / 16

    Where D(i-1,i) = (Ri - Si) - (R(i-1) - S(i-1))

    Since we only have RTT measurements (not separate send/receive
    timestamps), we approximate D as the change in RTT between
    consecutive samples.

    Args:
        samples: List of RTT values in milliseconds.
        initial_jitter: Initial jitter estimate (default 0.0).

    Returns:
        Estimated jitter in milliseconds.

    Example::

        >>> compute_jitter_rfc3550([10.0, 12.0, 11.0, 13.0, 10.0])
        0.8125
    """
    if len(samples) < 2:
        return initial_jitter

    jitter = initial_jitter
    for i in range(1, len(samples)):
        delta = abs(samples[i] - samples[i - 1])
        jitter += (delta - jitter) / 16.0

    return jitter


def compute_moving_average(values: list[float], window: int) -> list[float]:
    """Simple moving average.

    Args:
        values: List of numeric values.
        window: Window size (number of samples).

    Returns:
        List of moving averages. Length is ``len(values) - window + 1``
        (or empty if insufficient data).

    Example::

        >>> compute_moving_average([1, 2, 3, 4, 5], 3)
        [2.0, 3.0, 4.0]
    """
    if window <= 0 or len(values) < window:
        return []
    result: list[float] = []
    window_sum = sum(values[:window])
    result.append(window_sum / window)
    for i in range(window, len(values)):
        window_sum += values[i] - values[i - window]
        result.append(window_sum / window)
    return result


def compute_ema(
    values: list[float], alpha: float = 0.3, initial: float | None = None
) -> list[float]:
    """Exponential moving average.

    EMA(t) = alpha * value(t) + (1 - alpha) * EMA(t-1)

    Args:
        values: List of numeric values.
        alpha: Smoothing factor (0 < alpha <= 1). Higher = more reactive.
        initial: Initial EMA value. Defaults to first value.

    Returns:
        List of EMA values, same length as input.

    Example::

        >>> compute_ema([10.0, 11.0, 12.0, 11.0, 13.0], alpha=0.5)
        [10.0, 10.5, 11.25, 11.125, 12.0625]
    """
    if not values:
        return []
    if not (0.0 < alpha <= 1.0):
        raise ValueError(f"alpha must be in (0, 1], got {alpha}")

    ema_values: list[float] = []
    current = initial if initial is not None else values[0]
    current = values[0] if initial is None else initial
    for v in values:
        current = alpha * v + (1.0 - alpha) * current
        ema_values.append(current)
    return ema_values


def compute_weighted_average(values: list[float], weights: list[float]) -> float:
    """Weighted average.

    Args:
        values: List of values.
        weights: Corresponding weights (same length as values).

    Returns:
        Weighted average.

    Raises:
        ValueError: If lengths don't match or weights sum to zero.

    Example::

        >>> compute_weighted_average([10, 20, 30], [1, 2, 1])
        20.0
    """
    if len(values) != len(weights):
        raise ValueError("values and weights must have the same length")
    weight_sum = sum(weights)
    if weight_sum == 0:
        raise ValueError("weights must not sum to zero")
    return sum(v * w for v, w in zip(values, weights, strict=True)) / weight_sum


def compute_harmonic_mean(values: list[float]) -> float:
    """Harmonic mean.

    Useful for averaging rates (e.g., throughput).

    Args:
        values: List of positive numeric values.

    Returns:
        Harmonic mean, or 0.0 if the list is empty.

    Example::

        >>> compute_harmonic_mean([10.0, 20.0, 40.0])
        18.285714285714285
    """
    if not values or any(v <= 0 for v in values):
        return 0.0
    n = len(values)
    return n / sum(1.0 / v for v in values)


def compute_geometric_mean(values: list[float]) -> float:
    """Geometric mean.

    Useful for averaging ratios or growth rates.

    Args:
        values: List of positive numeric values.

    Returns:
        Geometric mean, or 0.0 if the list is empty.

    Example::

        >>> compute_geometric_mean([2.0, 8.0])
        4.0
    """
    if not values or any(v <= 0 for v in values):
        return 0.0
    log_sum = sum(math.log(v) for v in values)
    return math.exp(log_sum / len(values))


def compute_cv(values: list[float]) -> float:
    """Coefficient of variation (stddev / mean).

    Dimensionless measure of dispersion. Lower = more consistent.

    Args:
        values: List of numeric values.

    Returns:
        CV as a fraction (0.0+), or 0.0 if mean is zero.

    Example::

        >>> compute_cv([10.0, 10.0, 10.0])
        0.0
    """
    mean = compute_mean(values)
    if mean == 0.0:
        return 0.0
    return compute_stddev(values) / mean


# ---------------------------------------------------------------------------
# Running stats engine
# ---------------------------------------------------------------------------


@dataclass
class SampleStats:
    """Snapshot of computed statistics from a set of samples.

    Attributes:
        count: Number of samples.
        mean: Arithmetic mean.
        median: Median (p50).
        min: Minimum value.
        max: Maximum value.
        variance: Population variance.
        stddev: Standard deviation.
        p50: 50th percentile.
        p75: 75th percentile.
        p90: 90th percentile.
        p95: 95th percentile.
        p99: 99th percentile.
        jitter: RFC 3550 jitter estimate.
        cv: Coefficient of variation.
        loss_rate: Packet loss rate (0.0-1.0).
        loss_percent: Packet loss percentage.
        sent: Total packets sent.
        received: Total packets received.
        lost: Total packets lost.
        ema: Current exponential moving average value.
        ma: Current moving average value.
    """

    count: int = 0
    mean: float = 0.0
    median: float = 0.0
    min: float = 0.0
    max: float = 0.0
    variance: float = 0.0
    stddev: float = 0.0
    p50: float = 0.0
    p75: float = 0.0
    p90: float = 0.0
    p95: float = 0.0
    p99: float = 0.0
    jitter: float = 0.0
    cv: float = 0.0
    loss_rate: float = 0.0
    loss_percent: float = 0.0
    sent: int = 0
    received: int = 0
    lost: int = 0
    ema: float = 0.0
    ma: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "count": self.count,
            "mean": round(self.mean, 3),
            "median": round(self.median, 3),
            "min": round(self.min, 3),
            "max": round(self.max, 3),
            "variance": round(self.variance, 3),
            "stddev": round(self.stddev, 3),
            "p50": round(self.p50, 3),
            "p75": round(self.p75, 3),
            "p90": round(self.p90, 3),
            "p95": round(self.p95, 3),
            "p99": round(self.p99, 3),
            "jitter": round(self.jitter, 3),
            "cv": round(self.cv, 4),
            "loss_rate": round(self.loss_rate, 4),
            "loss_percent": round(self.loss_percent, 2),
            "sent": self.sent,
            "received": self.received,
            "lost": self.lost,
            "ema": round(self.ema, 3),
            "ma": round(self.ma, 3),
        }


class StatsEngine:
    """Running statistics engine with real-time sample ingestion.

    Maintains state for incremental computation of all metrics.
    Call :meth:`add_sample` for each probe result, then
    :meth:`get_report` for a full snapshot.

    Attributes:
        ema_alpha: Alpha parameter for exponential moving average.
        ma_window: Window size for simple moving average.

    Example::

        engine = StatsEngine(ema_alpha=0.3, ma_window=10)
        for rtt in [10.0, 12.0, 11.0, 13.0, 10.0]:
            engine.add_sample(rtt)
        report = engine.get_report()
        print(report.p95, report.jitter)
    """

    def __init__(
        self,
        ema_alpha: float = 0.3,
        ma_window: int = 10,
        rtt_history_size: int = 1000,
    ) -> None:
        """Initialize the statistics engine.

        Args:
            ema_alpha: Alpha for exponential moving average (0, 1].
            ma_window: Window size for simple moving average.
            rtt_history_size: Maximum RTT samples to retain.
        """
        if not (0.0 < ema_alpha <= 1.0):
            raise ValueError(f"ema_alpha must be in (0, 1], got {ema_alpha}")
        if ma_window < 1:
            raise ValueError(f"ma_window must be >= 1, got {ma_window}")

        self.ema_alpha = ema_alpha
        self.ma_window = ma_window
        self._rtt_samples: deque[float] = deque(maxlen=rtt_history_size)
        self._sent: int = 0
        self._received: int = 0
        self._jitter: float = 0.0
        self._ema: float = 0.0
        self._ema_initialized: bool = False
        self._ma_cache: deque[float] = deque(maxlen=ma_window)
        self._ma_sum: float = 0.0
        self._min: float = float("inf")
        self._max: float = float("-inf")

    def add_sample(self, rtt_ms: float) -> None:
        """Add a probe result.

        Args:
            rtt_ms: Round-trip time in milliseconds (>= 0).
        """
        self._sent += 1
        self._rtt_samples.append(rtt_ms)
        self._received += 1

        # Min/Max (incremental)
        if rtt_ms < self._min:
            self._min = rtt_ms
        if rtt_ms > self._max:
            self._max = rtt_ms

        # RFC 3550 jitter (incremental)
        if len(self._rtt_samples) >= 2:
            prev = self._rtt_samples[-2]
            delta = abs(rtt_ms - prev)
            self._jitter += (delta - self._jitter) / 16.0

        # EMA (incremental)
        if not self._ema_initialized:
            self._ema = rtt_ms
            self._ema_initialized = True
        else:
            self._ema = self.ema_alpha * rtt_ms + (1.0 - self.ema_alpha) * self._ema

        # Moving average (incremental)
        if len(self._ma_cache) >= self.ma_window:
            old = self._ma_cache.popleft()
            self._ma_sum -= old
        self._ma_cache.append(rtt_ms)
        self._ma_sum += rtt_ms

    def add_loss(self) -> None:
        """Record a packet loss (timeout/unreachable)."""
        self._sent += 1

    def reset(self) -> None:
        """Reset all state to initial values."""
        self._rtt_samples.clear()
        self._sent = 0
        self._received = 0
        self._jitter = 0.0
        self._ema = 0.0
        self._ema_initialized = False
        self._ma_cache.clear()
        self._ma_sum = 0.0
        self._min = float("inf")
        self._max = float("-inf")

    def get_report(self) -> SampleStats:
        """Compute and return a full statistics report.

        Returns:
            SampleStats with all computed metrics.
        """
        values = list(self._rtt_samples)
        n = len(values)

        if n == 0:
            return SampleStats(
                sent=self._sent,
                received=self._received,
                lost=self._sent - self._received,
            )

        mean_val = compute_mean(values)
        ma_val = self._ma_sum / len(self._ma_cache) if self._ma_cache else 0.0
        percentiles = compute_percentiles(values, [50, 75, 90, 95, 99])

        return SampleStats(
            count=n,
            mean=mean_val,
            median=compute_median(values),
            min=self._min if self._min != float("inf") else 0.0,
            max=self._max if self._max != float("-inf") else 0.0,
            variance=compute_variance(values, ddof=1),
            stddev=compute_stddev(values, ddof=1),
            p50=percentiles[50],
            p75=percentiles[75],
            p90=percentiles[90],
            p95=percentiles[95],
            p99=percentiles[99],
            jitter=self._jitter,
            cv=compute_cv(values),
            loss_rate=compute_packet_loss(self._sent, self._received),
            loss_percent=compute_loss_percent(self._sent, self._received),
            sent=self._sent,
            received=self._received,
            lost=self._sent - self._received,
            ema=self._ema,
            ma=ma_val,
        )

    @property
    def sample_count(self) -> int:
        """Number of RTT samples collected."""
        return len(self._rtt_samples)

    @property
    def current_jitter(self) -> float:
        """Current RFC 3550 jitter estimate."""
        return self._jitter

    @property
    def current_ema(self) -> float:
        """Current exponential moving average."""
        return self._ema

    @property
    def current_ma(self) -> float:
        """Current moving average."""
        if not self._ma_cache:
            return 0.0
        return self._ma_sum / len(self._ma_cache)
