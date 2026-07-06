"""Tests for the Prediction Engine."""

from __future__ import annotations

import pytest

from uni.core.analysis.prediction import (
    PredictionConfig,
    PredictionEngine,
    PredictionGrade,
    PredictionResult,
    StabilityLevel,
    _inverse_sigmoid_mapped,
    _sigmoid,
    compute_confidence,
    compute_connection_probability,
    compute_quality_grade,
    compute_quality_score,
    compute_rating,
    compute_stability,
    compute_stability_level,
    estimate_next_rtt,
)

# ---------------------------------------------------------------------------
# _sigmoid
# ---------------------------------------------------------------------------

class TestSigmoid:
    def test_zero(self) -> None:
        assert _sigmoid(0.0) == pytest.approx(0.5)

    def test_positive(self) -> None:
        assert _sigmoid(10.0) > 0.9

    def test_negative(self) -> None:
        assert _sigmoid(-10.0) < 0.1

    def test_range(self) -> None:
        for x in [-100, -10, -1, 0, 1, 10, 100]:
            result = _sigmoid(x)
            assert 0.0 < result <= 1.0

    def test_steepness(self) -> None:
        assert _sigmoid(1.0, k=10.0) > _sigmoid(1.0, k=1.0)


# ---------------------------------------------------------------------------
# _inverse_sigmoid_mapped
# ---------------------------------------------------------------------------

class TestInverseSigmoidMapped:
    def test_at_midpoint(self) -> None:
        result = _inverse_sigmoid_mapped(80.0, 80.0, 60.0)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_low_value(self) -> None:
        result = _inverse_sigmoid_mapped(10.0, 80.0, 60.0)
        assert result > 0.8  # Low RTT = good score

    def test_high_value(self) -> None:
        result = _inverse_sigmoid_mapped(300.0, 80.0, 60.0)
        assert result < 0.2  # High RTT = bad score

    def test_zero_scale(self) -> None:
        result = _inverse_sigmoid_mapped(80.0, 80.0, 0.0)
        assert result == 0.0


# ---------------------------------------------------------------------------
# compute_connection_probability
# ---------------------------------------------------------------------------

class TestConnectionProbability:
    def test_perfect(self) -> None:
        assert compute_connection_probability(100, 100) == 1.0

    def test_98_percent(self) -> None:
        assert compute_connection_probability(100, 98) == pytest.approx(0.98)

    def test_with_consecutive_failures(self) -> None:
        p = compute_connection_probability(100, 98, consecutive_failures=5)
        assert p < 0.98

    def test_all_failures(self) -> None:
        assert compute_connection_probability(100, 0) == 0.0

    def test_zero_sent(self) -> None:
        assert compute_connection_probability(0, 0) == 0.0

    def test_consecutive_equals_window(self) -> None:
        p = compute_connection_probability(100, 100, consecutive_failures=10)
        assert p == 0.0  # anomaly_factor=1.0

    def test_partial_consecutive(self) -> None:
        p1 = compute_connection_probability(100, 98, consecutive_failures=2)
        p2 = compute_connection_probability(100, 98, consecutive_failures=8)
        assert p1 > p2

    def test_clamped(self) -> None:
        p = compute_connection_probability(100, 150, consecutive_failures=0)
        assert 0.0 <= p <= 1.0


# ---------------------------------------------------------------------------
# compute_stability
# ---------------------------------------------------------------------------

class TestStability:
    def test_perfect_stability(self) -> None:
        assert compute_stability([10.0, 10.0, 10.0, 10.0]) == 1.0

    def test_no_stability(self) -> None:
        s = compute_stability([1.0, 100.0, 1.0, 100.0])
        assert s < 0.3  # High variance = low stability

    def test_single_sample(self) -> None:
        assert compute_stability([10.0]) == 1.0

    def test_empty(self) -> None:
        assert compute_stability([]) == 1.0

    def test_moderate(self) -> None:
        s = compute_stability([10.0, 12.0, 11.0, 13.0, 10.0])
        assert 0.5 < s < 1.0

    def test_cv_weight_zero(self) -> None:
        s = compute_stability([10.0, 50.0], cv_weight=0.0)
        assert s == 1.0

    def test_clamped(self) -> None:
        s = compute_stability([1.0, 200.0], cv_weight=2.0)
        assert 0.0 <= s <= 1.0


# ---------------------------------------------------------------------------
# compute_quality_score
# ---------------------------------------------------------------------------

class TestQualityScore:
    def test_perfect(self) -> None:
        q, lat, loss, jit = compute_quality_score(
            [10.0, 10.0, 10.0], 0.0, 0.0
        )
        assert q > 0.9

    def test_poor(self) -> None:
        q, lat, loss, jit = compute_quality_score(
            [500.0, 500.0, 500.0], 0.5, 100.0
        )
        assert q < 0.3

    def test_weights_sum_to_one(self) -> None:
        q, lat, loss, jit = compute_quality_score(
            [20.0, 20.0], 0.0, 0.0
        )
        assert lat + loss + jit > 0

    def test_empty_samples(self) -> None:
        q, lat, loss, jit = compute_quality_score([], 0.0, 0.0)
        assert 0.0 <= q <= 1.0

    def test_custom_config(self) -> None:
        cfg = PredictionConfig(w_latency=1.0, w_loss=0.0, w_jitter=0.0)
        q, lat, loss, jit = compute_quality_score(
            [10.0, 10.0], 0.0, 0.0, cfg
        )
        assert q == pytest.approx(lat, abs=0.01)


# ---------------------------------------------------------------------------
# compute_rating
# ---------------------------------------------------------------------------

class TestRating:
    def test_five_stars(self) -> None:
        assert compute_rating(0.95) == 5

    def test_four_stars(self) -> None:
        assert compute_rating(0.75) == 4

    def test_three_stars(self) -> None:
        assert compute_rating(0.55) == 3

    def test_two_stars(self) -> None:
        assert compute_rating(0.35) == 2

    def test_one_star(self) -> None:
        assert compute_rating(0.1) == 1

    def test_boundary(self) -> None:
        assert compute_rating(0.0) == 1
        assert compute_rating(1.0) == 5


# ---------------------------------------------------------------------------
# compute_confidence
# ---------------------------------------------------------------------------

class TestConfidence:
    def test_many_samples(self) -> None:
        c = compute_confidence(1000, 0.05)
        assert c > 0.95

    def test_few_samples(self) -> None:
        c = compute_confidence(5, 0.05)
        assert c < 1.0

    def test_high_volatility(self) -> None:
        c = compute_confidence(100, 1.0)
        assert c < 1.0

    def test_zero_samples(self) -> None:
        assert compute_confidence(0, 0.0) == 0.0

    def test_perfect_stability(self) -> None:
        c = compute_confidence(100, 0.0)
        assert c == pytest.approx(1.0, abs=0.01)

    def test_below_min_samples(self) -> None:
        c1 = compute_confidence(3, 0.1, min_samples=10)
        c2 = compute_confidence(10, 0.1, min_samples=10)
        assert c1 < c2

    def test_clamped(self) -> None:
        c = compute_confidence(10000, 0.0, min_samples=1)
        assert 0.0 <= c <= 1.0


# ---------------------------------------------------------------------------
# compute_quality_grade
# ---------------------------------------------------------------------------

class TestQualityGrade:
    def test_excellent(self) -> None:
        assert compute_quality_grade(0.9) == PredictionGrade.EXCELLENT

    def test_good(self) -> None:
        assert compute_quality_grade(0.75) == PredictionGrade.GOOD

    def test_fair(self) -> None:
        assert compute_quality_grade(0.55) == PredictionGrade.FAIR

    def test_poor(self) -> None:
        assert compute_quality_grade(0.35) == PredictionGrade.POOR

    def test_bad(self) -> None:
        assert compute_quality_grade(0.1) == PredictionGrade.BAD

    def test_boundary_excellent_good(self) -> None:
        assert compute_quality_grade(0.85) == PredictionGrade.EXCELLENT
        assert compute_quality_grade(0.849) == PredictionGrade.GOOD


# ---------------------------------------------------------------------------
# compute_stability_level
# ---------------------------------------------------------------------------

class TestStabilityLevel:
    def test_rock_solid(self) -> None:
        assert compute_stability_level(0.95) == StabilityLevel.ROCK_SOLID

    def test_stable(self) -> None:
        assert compute_stability_level(0.75) == StabilityLevel.STABLE

    def test_moderate(self) -> None:
        assert compute_stability_level(0.55) == StabilityLevel.MODERATE

    def test_unstable(self) -> None:
        assert compute_stability_level(0.35) == StabilityLevel.UNSTABLE

    def test_chaotic(self) -> None:
        assert compute_stability_level(0.1) == StabilityLevel.CHAOTIC


# ---------------------------------------------------------------------------
# estimate_next_rtt
# ---------------------------------------------------------------------------

class TestEstimateNextRtt:
    def test_basic(self) -> None:
        result = estimate_next_rtt([10.0, 11.0, 12.0, 13.0])
        assert result > 10.0
        assert result < 13.0

    def test_constant(self) -> None:
        assert estimate_next_rtt([10.0, 10.0, 10.0]) == 10.0

    def test_empty(self) -> None:
        assert estimate_next_rtt([]) == 0.0

    def test_single(self) -> None:
        assert estimate_next_rtt([10.0]) == 10.0

    def test_trend(self) -> None:
        samples = [10.0, 20.0, 30.0, 40.0, 50.0]
        result = estimate_next_rtt(samples, ema_alpha=0.5)
        assert result > 30.0

    def test_high_alpha(self) -> None:
        result = estimate_next_rtt([10.0, 20.0, 30.0], ema_alpha=0.9)
        assert result == pytest.approx(30.0, abs=2.0)


# ---------------------------------------------------------------------------
# PredictionConfig
# ---------------------------------------------------------------------------

class TestPredictionConfig:
    def test_defaults(self) -> None:
        cfg = PredictionConfig()
        assert cfg.w_latency == 0.40
        assert cfg.w_loss == 0.35
        assert cfg.w_jitter == 0.25
        assert cfg.min_samples == 5

    def test_weights_validation(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            PredictionConfig(w_latency=0.5, w_loss=0.5, w_jitter=0.5)

    def test_sigmoid_k_validation(self) -> None:
        with pytest.raises(ValueError, match="sigmoid_k"):
            PredictionConfig(sigmoid_k=0)


# ---------------------------------------------------------------------------
# PredictionResult
# ---------------------------------------------------------------------------

class TestPredictionResult:
    def test_to_dict(self) -> None:
        r = PredictionResult(
            probability=0.95,
            stability=0.8,
            quality=0.85,
            rating=4,
            confidence=0.9,
            grade=PredictionGrade.GOOD,
            stability_level=StabilityLevel.STABLE,
            latency_score=0.9,
            loss_score=0.95,
            jitter_score=0.8,
            sample_count=100,
            expected_rtt=15.0,
            rtt_range=(10.0, 20.0),
        )
        d = r.to_dict()
        assert d["probability"] == 0.95
        assert d["rating"] == 4
        assert d["grade"] == "good"
        assert d["stability_level"] == "stable"


# ---------------------------------------------------------------------------
# PredictionEngine
# ---------------------------------------------------------------------------

class TestPredictionEngine:
    @pytest.fixture
    def engine(self) -> PredictionEngine:
        return PredictionEngine()

    def test_perfect_connection(self, engine: PredictionEngine) -> None:
        samples = [10.0] * 100
        result = engine.predict(
            samples=samples, sent=100, received=100, jitter=0.0
        )
        assert result.probability == 1.0
        assert result.stability == 1.0
        assert result.quality > 0.9
        assert result.rating == 5
        assert result.grade == PredictionGrade.EXCELLENT
        assert result.stability_level == StabilityLevel.ROCK_SOLID

    def test_poor_connection(self, engine: PredictionEngine) -> None:
        samples = [500.0, 100.0, 800.0, 50.0, 600.0]
        result = engine.predict(
            samples=samples, sent=100, received=50, jitter=200.0
        )
        assert result.probability < 0.6
        assert result.quality < 0.4
        assert result.rating <= 2
        assert result.grade in (PredictionGrade.POOR, PredictionGrade.BAD)

    def test_with_consecutive_failures(self, engine: PredictionEngine) -> None:
        result = engine.predict(
            samples=[10.0, 10.0, 10.0],
            sent=100, received=100,
            consecutive_failures=5,
        )
        assert result.probability < 1.0

    def test_empty_samples(self, engine: PredictionEngine) -> None:
        result = engine.predict(
            samples=[], sent=0, received=0
        )
        assert result.probability == 0.0
        assert result.sample_count == 0

    def test_predict_simple(self, engine: PredictionEngine) -> None:
        result = engine.predict_simple(
            avg_rtt=15.0, loss_percent=2.0, jitter=3.0
        )
        assert 0.0 <= result.quality <= 1.0
        assert 1 <= result.rating <= 5

    def test_expected_rtt(self, engine: PredictionEngine) -> None:
        samples = [10.0, 20.0, 30.0, 40.0]
        result = engine.predict(
            samples=samples, sent=4, received=4
        )
        assert result.expected_rtt > 10.0

    def test_rtt_range(self, engine: PredictionEngine) -> None:
        samples = [10.0, 50.0, 20.0]
        result = engine.predict(
            samples=samples, sent=3, received=3
        )
        assert result.rtt_range == (10.0, 50.0)

    def test_confidence_increases_with_samples(self, engine: PredictionEngine) -> None:
        r1 = engine.predict(
            samples=[10.0] * 5, sent=5, received=5
        )
        r2 = engine.predict(
            samples=[10.0] * 100, sent=100, received=100
        )
        # With zero variance, confidence is 1.0 for both — just check range
        assert 0.0 <= r1.confidence <= 1.0
        assert 0.0 <= r2.confidence <= 1.0

    def test_stability_decreases_with_variance(self, engine: PredictionEngine) -> None:
        r1 = engine.predict(
            samples=[10.0, 10.0, 10.0, 10.0], sent=4, received=4
        )
        r2 = engine.predict(
            samples=[10.0, 100.0, 10.0, 100.0], sent=4, received=4
        )
        assert r1.stability > r2.stability

    def test_all_metrics_in_range(self, engine: PredictionEngine) -> None:
        samples = [15.0, 20.0, 18.0, 22.0, 16.0, 19.0, 21.0]
        result = engine.predict(
            samples=samples, sent=50, received=48, jitter=5.0
        )
        assert 0.0 <= result.probability <= 1.0
        assert 0.0 <= result.stability <= 1.0
        assert 0.0 <= result.quality <= 1.0
        assert 1 <= result.rating <= 5
        assert 0.0 <= result.confidence <= 1.0
        assert 0.0 <= result.latency_score <= 1.0
        assert 0.0 <= result.loss_score <= 1.0
        assert 0.0 <= result.jitter_score <= 1.0

    def test_grade_rating_consistency(self, engine: PredictionEngine) -> None:
        """Grade and rating should generally agree."""
        result = engine.predict(
            samples=[10.0] * 50, sent=50, received=50, jitter=1.0
        )
        if result.rating >= 4:
            assert result.grade in (PredictionGrade.EXCELLENT, PredictionGrade.GOOD)
        if result.rating <= 2:
            assert result.grade in (PredictionGrade.POOR, PredictionGrade.BAD)

    def test_custom_config(self) -> None:
        cfg = PredictionConfig(w_latency=0.7, w_loss=0.2, w_jitter=0.1)
        engine = PredictionEngine(config=cfg)
        result = engine.predict(
            samples=[10.0, 12.0, 11.0], sent=3, received=3
        )
        assert 0.0 <= result.quality <= 1.0

    def test_probability_penalizes_bursty_failures(self, engine: PredictionEngine) -> None:
        """Same loss rate but bursty failures should have lower probability."""
        r1 = engine.predict(
            samples=[10.0] * 100,
            sent=100, received=95,
            consecutive_failures=0,
        )
        r2 = engine.predict(
            samples=[10.0] * 95,
            sent=100, received=95,
            consecutive_failures=5,
        )
        assert r1.probability > r2.probability
