"""Tests for the statistical analysis module."""

from __future__ import annotations

import math

import pytest

from uni.core.analysis.statistics import (
    SampleStats,
    StatsEngine,
    compute_cv,
    compute_ema,
    compute_geometric_mean,
    compute_harmonic_mean,
    compute_jitter_rfc3550,
    compute_loss_percent,
    compute_mean,
    compute_median,
    compute_moving_average,
    compute_packet_loss,
    compute_percentile,
    compute_percentile_rank,
    compute_percentiles,
    compute_stddev,
    compute_variance,
    compute_weighted_average,
)

# ---------------------------------------------------------------------------
# compute_mean
# ---------------------------------------------------------------------------


class TestMean:
    def test_basic(self) -> None:
        assert compute_mean([10.0, 20.0, 30.0]) == 20.0

    def test_single(self) -> None:
        assert compute_mean([42.0]) == 42.0

    def test_empty(self) -> None:
        assert compute_mean([]) == 0.0

    def test_identical(self) -> None:
        assert compute_mean([5.0, 5.0, 5.0]) == 5.0

    def test_negative(self) -> None:
        assert compute_mean([-10.0, 10.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_median
# ---------------------------------------------------------------------------


class TestMedian:
    def test_odd_count(self) -> None:
        assert compute_median([1.0, 3.0, 5.0]) == 3.0

    def test_even_count(self) -> None:
        assert compute_median([1.0, 2.0, 3.0, 4.0]) == 2.5

    def test_single(self) -> None:
        assert compute_median([7.0]) == 7.0

    def test_empty(self) -> None:
        assert compute_median([]) == 0.0

    def test_unsorted(self) -> None:
        assert compute_median([5.0, 1.0, 3.0]) == 3.0

    def test_two_elements(self) -> None:
        assert compute_median([2.0, 4.0]) == 3.0


# ---------------------------------------------------------------------------
# compute_variance
# ---------------------------------------------------------------------------


class TestVariance:
    def test_population(self) -> None:
        assert compute_variance([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == 4.0

    def test_sample(self) -> None:
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        # ss=32, n=8, ddof=1 -> variance = 32/7
        assert compute_variance(vals, ddof=1) == pytest.approx(32 / 7)

    def test_single(self) -> None:
        assert compute_variance([5.0]) == 0.0

    def test_empty(self) -> None:
        assert compute_variance([]) == 0.0

    def test_constant(self) -> None:
        assert compute_variance([3.0, 3.0, 3.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_stddev
# ---------------------------------------------------------------------------


class TestStddev:
    def test_basic(self) -> None:
        assert compute_stddev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]) == 2.0

    def test_sample(self) -> None:
        vals = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]
        assert compute_stddev(vals, ddof=1) == pytest.approx(math.sqrt(32 / 7))

    def test_empty(self) -> None:
        assert compute_stddev([]) == 0.0

    def test_constant(self) -> None:
        assert compute_stddev([1.0, 1.0, 1.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_percentile
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_p50(self) -> None:
        assert compute_percentile([1, 2, 3, 4, 5], 50) == 3.0

    def test_p95(self) -> None:
        assert compute_percentile([1, 2, 3, 4, 5], 95) == 4.8

    def test_p0(self) -> None:
        assert compute_percentile([10, 20, 30], 0) == 10.0

    def test_p100(self) -> None:
        assert compute_percentile([10, 20, 30], 100) == 30.0

    def test_single(self) -> None:
        assert compute_percentile([5.0], 50) == 5.0

    def test_empty(self) -> None:
        assert compute_percentile([], 50) == 0.0

    def test_even_count(self) -> None:
        result = compute_percentile([1, 2, 3, 4], 50)
        assert result == 2.5

    def test_interpolation(self) -> None:
        result = compute_percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 25)
        assert result == pytest.approx(3.25)


class TestPercentiles:
    def test_multiple(self) -> None:
        result = compute_percentiles([1, 2, 3, 4, 5], [50, 95, 99])
        assert 50 in result
        assert 95 in result
        assert 99 in result
        assert result[50] == 3.0

    def test_empty(self) -> None:
        result = compute_percentiles([], [50])
        assert result[50] == 0.0


class TestPercentileRank:
    def test_middle(self) -> None:
        rank = compute_percentile_rank([1, 2, 3, 4, 5], 3)
        assert rank == 50.0

    def test_low(self) -> None:
        rank = compute_percentile_rank([1, 2, 3, 4, 5], 1)
        assert rank == 10.0

    def test_high(self) -> None:
        rank = compute_percentile_rank([1, 2, 3, 4, 5], 5)
        assert rank == 90.0

    def test_empty(self) -> None:
        assert compute_percentile_rank([], 5) == 0.0


# ---------------------------------------------------------------------------
# compute_packet_loss / compute_loss_percent
# ---------------------------------------------------------------------------


class TestPacketLoss:
    def test_no_loss(self) -> None:
        assert compute_packet_loss(100, 100) == 0.0

    def test_5_percent(self) -> None:
        assert compute_packet_loss(100, 95) == 0.05

    def test_total_loss(self) -> None:
        assert compute_packet_loss(100, 0) == 1.0

    def test_zero_sent(self) -> None:
        assert compute_packet_loss(0, 0) == 0.0

    def test_more_received(self) -> None:
        assert compute_packet_loss(100, 150) == 0.0

    def test_loss_percent(self) -> None:
        assert compute_loss_percent(100, 95) == 5.0


# ---------------------------------------------------------------------------
# compute_jitter_rfc3550
# ---------------------------------------------------------------------------


class TestJitterRFC3550:
    def test_constant_rtt(self) -> None:
        jitter = compute_jitter_rfc3550([10.0, 10.0, 10.0, 10.0])
        assert jitter == pytest.approx(0.0, abs=0.01)

    def test_varying_rtt(self) -> None:
        jitter = compute_jitter_rfc3550([10.0, 12.0, 11.0, 13.0, 10.0])
        assert jitter > 0

    def test_single_sample(self) -> None:
        assert compute_jitter_rfc3550([10.0]) == 0.0

    def test_empty(self) -> None:
        assert compute_jitter_rfc3550([]) == 0.0

    def test_initial_jitter(self) -> None:
        result = compute_jitter_rfc3550([10.0, 10.0], initial_jitter=5.0)
        assert result < 5.0  # converges toward 0

    def test_convergence(self) -> None:
        """Jitter should converge for constant RTT after many samples."""
        samples = [10.0] * 100
        jitter = compute_jitter_rfc3550(samples)
        assert jitter == pytest.approx(0.0, abs=0.001)

    def test_step_change(self) -> None:
        """Step change should produce a spike."""
        samples = [10.0] * 10 + [20.0] * 10
        jitter = compute_jitter_rfc3550(samples)
        assert jitter > 0


# ---------------------------------------------------------------------------
# compute_moving_average
# ---------------------------------------------------------------------------


class TestMovingAverage:
    def test_basic(self) -> None:
        result = compute_moving_average([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        assert result == [2.0, 3.0, 4.0]

    def test_window_1(self) -> None:
        result = compute_moving_average([1.0, 2.0, 3.0], 1)
        assert result == [1.0, 2.0, 3.0]

    def test_window_equals_length(self) -> None:
        result = compute_moving_average([1.0, 2.0, 3.0], 3)
        assert result == [2.0]

    def test_window_too_large(self) -> None:
        result = compute_moving_average([1.0, 2.0], 5)
        assert result == []

    def test_empty(self) -> None:
        assert compute_moving_average([], 3) == []

    def test_invalid_window(self) -> None:
        assert compute_moving_average([1, 2, 3], 0) == []


# ---------------------------------------------------------------------------
# compute_ema
# ---------------------------------------------------------------------------


class TestEMA:
    def test_basic(self) -> None:
        result = compute_ema([10.0, 11.0, 12.0, 11.0, 13.0], alpha=0.5)
        assert len(result) == 5
        assert result[0] == 10.0

    def test_alpha_1(self) -> None:
        result = compute_ema([10.0, 20.0, 30.0], alpha=1.0)
        assert result == [10.0, 20.0, 30.0]

    def test_small_alpha(self) -> None:
        result = compute_ema([10.0, 20.0, 30.0], alpha=0.1)
        assert result[0] == 10.0
        assert result[1] == pytest.approx(11.0)
        assert result[2] == pytest.approx(12.9)

    def test_empty(self) -> None:
        assert compute_ema([], alpha=0.3) == []

    def test_invalid_alpha(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            compute_ema([1, 2], alpha=0.0)

    def test_negative_alpha(self) -> None:
        with pytest.raises(ValueError, match="alpha"):
            compute_ema([1, 2], alpha=-1.0)


# ---------------------------------------------------------------------------
# compute_weighted_average
# ---------------------------------------------------------------------------


class TestWeightedAverage:
    def test_basic(self) -> None:
        result = compute_weighted_average([10.0, 20.0, 30.0], [1.0, 2.0, 1.0])
        assert result == 20.0

    def test_equal_weights(self) -> None:
        result = compute_weighted_average([10.0, 20.0], [1.0, 1.0])
        assert result == 15.0

    def test_mismatched_lengths(self) -> None:
        with pytest.raises(ValueError, match="same length"):
            compute_weighted_average([1, 2], [1])

    def test_zero_weights(self) -> None:
        with pytest.raises(ValueError, match="zero"):
            compute_weighted_average([1, 2], [0, 0])


# ---------------------------------------------------------------------------
# compute_harmonic_mean
# ---------------------------------------------------------------------------


class TestHarmonicMean:
    def test_basic(self) -> None:
        # 3 / (1/10 + 1/20 + 1/40) = 3 / (7/40) = 120/7 = 17.142857...
        result = compute_harmonic_mean([10.0, 20.0, 40.0])
        assert result == pytest.approx(120 / 7, abs=0.001)

    def test_equal_values(self) -> None:
        assert compute_harmonic_mean([5.0, 5.0, 5.0]) == pytest.approx(5.0)

    def test_empty(self) -> None:
        assert compute_harmonic_mean([]) == 0.0

    def test_negative(self) -> None:
        assert compute_harmonic_mean([-1.0, 5.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_geometric_mean
# ---------------------------------------------------------------------------


class TestGeometricMean:
    def test_basic(self) -> None:
        assert compute_geometric_mean([2.0, 8.0]) == 4.0

    def test_equal(self) -> None:
        assert compute_geometric_mean([5.0, 5.0, 5.0]) == pytest.approx(5.0)

    def test_empty(self) -> None:
        assert compute_geometric_mean([]) == 0.0

    def test_negative(self) -> None:
        assert compute_geometric_mean([-1.0, 4.0]) == 0.0


# ---------------------------------------------------------------------------
# compute_cv
# ---------------------------------------------------------------------------


class TestCV:
    def test_constant(self) -> None:
        assert compute_cv([5.0, 5.0, 5.0]) == 0.0

    def test_varying(self) -> None:
        cv = compute_cv([10.0, 20.0, 30.0])
        assert cv > 0

    def test_empty(self) -> None:
        assert compute_cv([]) == 0.0


# ---------------------------------------------------------------------------
# StatsEngine
# ---------------------------------------------------------------------------


class TestStatsEngine:
    def test_empty(self) -> None:
        engine = StatsEngine()
        report = engine.get_report()
        assert report.count == 0
        assert report.sent == 0

    def test_add_sample(self) -> None:
        engine = StatsEngine()
        engine.add_sample(10.0)
        engine.add_sample(20.0)
        engine.add_sample(30.0)
        report = engine.get_report()
        assert report.count == 3
        assert report.mean == 20.0
        assert report.min == 10.0
        assert report.max == 30.0

    def test_add_loss(self) -> None:
        engine = StatsEngine()
        engine.add_sample(10.0)
        engine.add_loss()
        report = engine.get_report()
        assert report.sent == 2
        assert report.received == 1
        assert report.loss_rate == 0.5

    def test_jitter(self) -> None:
        engine = StatsEngine()
        for rtt in [10.0, 12.0, 11.0, 13.0]:
            engine.add_sample(rtt)
        assert engine.current_jitter > 0

    def test_ema(self) -> None:
        engine = StatsEngine(ema_alpha=0.5)
        engine.add_sample(10.0)
        engine.add_sample(20.0)
        report = engine.get_report()
        assert report.ema == 15.0

    def test_moving_average(self) -> None:
        engine = StatsEngine(ma_window=3)
        engine.add_sample(1.0)
        engine.add_sample(2.0)
        engine.add_sample(3.0)
        engine.add_sample(4.0)
        report = engine.get_report()
        assert report.ma == pytest.approx(3.0)

    def test_percentiles(self) -> None:
        engine = StatsEngine()
        for i in range(1, 101):
            engine.add_sample(float(i))
        report = engine.get_report()
        assert report.p50 == pytest.approx(50.5)
        assert report.p95 == pytest.approx(95.05)
        assert report.p99 == pytest.approx(99.01)

    def test_reset(self) -> None:
        engine = StatsEngine()
        engine.add_sample(10.0)
        engine.add_sample(20.0)
        engine.reset()
        report = engine.get_report()
        assert report.count == 0
        assert report.sent == 0

    def test_invalid_ema_alpha(self) -> None:
        with pytest.raises(ValueError, match="ema_alpha"):
            StatsEngine(ema_alpha=0.0)

    def test_invalid_ma_window(self) -> None:
        with pytest.raises(ValueError, match="ma_window"):
            StatsEngine(ma_window=0)

    def test_min_max_tracking(self) -> None:
        engine = StatsEngine()
        engine.add_sample(5.0)
        engine.add_sample(1.0)
        engine.add_sample(10.0)
        engine.add_sample(3.0)
        report = engine.get_report()
        assert report.min == 1.0
        assert report.max == 10.0

    def test_cv_in_report(self) -> None:
        engine = StatsEngine()
        engine.add_sample(10.0)
        engine.add_sample(20.0)
        engine.add_sample(30.0)
        report = engine.get_report()
        assert report.cv > 0

    def test_sample_stats_to_dict(self) -> None:
        stats = SampleStats(count=5, mean=10.0, p95=15.0)
        d = stats.to_dict()
        assert d["count"] == 5
        assert d["mean"] == 10.0
        assert d["p95"] == 15.0

    def test_many_samples(self) -> None:
        engine = StatsEngine(ma_window=50)
        for i in range(500):
            engine.add_sample(float(i % 100))
        report = engine.get_report()
        assert report.count == 500
        assert report.mean == pytest.approx(49.5, abs=1.0)
        assert report.min == 0.0
        assert report.max == 99.0
        assert report.p50 == pytest.approx(49.5, abs=2.0)

    def test_incremental_consistency(self) -> None:
        """Incremental engine should match batch computation."""
        samples = [10.0, 15.0, 12.0, 18.0, 11.0, 14.0, 16.0, 13.0]

        # Incremental
        engine = StatsEngine()
        for s in samples:
            engine.add_sample(s)
        inc_report = engine.get_report()

        # Batch
        assert inc_report.mean == pytest.approx(compute_mean(samples))
        assert inc_report.median == pytest.approx(compute_median(samples))
        assert inc_report.p95 == pytest.approx(compute_percentile(samples, 95), abs=0.1)
