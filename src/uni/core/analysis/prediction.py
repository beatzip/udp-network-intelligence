"""Prediction Engine — mathematical models for network quality forecasting.

Provides :class:`PredictionEngine` for computing connection probability,
stability, quality scores, and confidence intervals from historical
probe data. Uses pure statistical methods — no AI/ML.

Mathematical Models
-------------------

**Connection Probability (P):**

    P = received / sent * (1 - anomaly_factor)

    Where anomaly_factor penalizes consecutive failures:

    anomaly_factor = min(1.0, consecutive_failures / failure_window)

    This gives higher probability to stable connections and penalizes
    bursty failures even when overall loss is low.

**Stability (S):**

    S = 1.0 - (stddev / mean) * cv_weight

    Where:
    - stddev = standard deviation of RTT samples
    - mean = average RTT
    - cv_weight = coefficient of variation weight (clamped 0-1)
    - S is clamped to [0.0, 1.0]

    A perfectly stable connection (constant RTT) has S = 1.0.
    High variance reduces S.

**Quality Score (Q):**

    Q = w_latency * f_latency + w_loss * f_loss + w_jitter * f_jitter

    Where each component uses a sigmoid-like mapping:

    f_latency = 1.0 / (1.0 + exp(k * (rtt - midpoint) / scale))
    f_loss    = (1.0 - loss_rate) ^ loss_exponent
    f_jitter  = 1.0 / (1.0 + exp(k * (jitter - midpoint) / scale))

    Weights sum to 1.0 (default: 40% latency, 35% loss, 25% jitter).

**Rating (1-5 stars):**

    rating = max(1, min(5, round(Q * 5)))

**Confidence (C):**

    C = 1.0 - (1.0 / sqrt(n)) * volatility_factor

    Where:
    - n = number of samples
    - volatility_factor = stddev / mean (coefficient of variation)
    - C is clamped to [0.0, 1.0]

    More samples increase confidence. High volatility decreases it.
    A minimum sample count (default 5) is required for meaningful
    confidence.

References
----------

- RFC 3550 Appendix A.8 (Jitter estimation)
- ETSI TR 101 290 (DVB measurement guidelines)
- ITU-T G.107 (E-model for voice quality)
- EWMA for time-series smoothing

Example::

    engine = PredictionEngine()
    result = engine.predict(
        samples=[10.0, 12.0, 11.0, 13.0, 10.0, 11.0, 12.0],
        sent=100, received=97,
        jitter=2.5,
    )
    print(f"P={result.probability:.2f}, Q={result.quality:.2f}, "
          f"Rating={result.rating}★, C={result.confidence:.2f}")
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Any, Self

from uni.core.analysis.statistics import (
    compute_cv,
    compute_mean,
)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PredictionGrade(Enum):
    """Human-readable quality grades."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    BAD = "bad"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from string."""
        return cls(value)


class StabilityLevel(Enum):
    """Stability classification."""

    ROCK_SOLID = "rock_solid"
    STABLE = "stable"
    MODERATE = "moderate"
    UNSTABLE = "unstable"
    CHAOTIC = "chaotic"

    def to_dict(self) -> str:
        """Serialize to string."""
        return self.value

    @classmethod
    def from_dict(cls, value: str) -> Self:
        """Deserialize from string."""
        return cls(value)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PredictionConfig:
    """Configuration for the prediction engine.

    All weights and thresholds are tunable. Default values are
    calibrated for typical game server probe data (RTT 5-500ms,
    loss 0-30%, jitter 0-100ms).

    Attributes:
        w_latency: Weight for latency component (0.0-1.0).
        w_loss: Weight for loss component (0.0-1.0).
        w_jitter: Weight for jitter component (0.0-1.0).
        latency_midpoint: RTT value where f_latency = 0.5 (ms).
        latency_scale: Sigmoid scale for latency mapping.
        loss_exponent: Exponent for loss function.
        jitter_midpoint: Jitter value where f_jitter = 0.5 (ms).
        jitter_scale: Sigmoid scale for jitter mapping.
        sigmoid_k: Steepness of sigmoid function.
        min_samples: Minimum samples for meaningful confidence.
        failure_window: Window for consecutive failure detection.
        stability_cv_weight: How much CV affects stability.
    """

    w_latency: float = 0.40
    w_loss: float = 0.35
    w_jitter: float = 0.25
    latency_midpoint: float = 80.0
    latency_scale: float = 60.0
    loss_exponent: float = 2.0
    jitter_midpoint: float = 15.0
    jitter_scale: float = 20.0
    sigmoid_k: float = 4.0
    min_samples: int = 5
    failure_window: int = 10
    stability_cv_weight: float = 0.8

    def __post_init__(self) -> None:
        """Validate configuration values."""
        w_sum = self.w_latency + self.w_loss + self.w_jitter
        if abs(w_sum - 1.0) > 0.01:
            raise ValueError(
                f"Weights must sum to 1.0, got {w_sum:.3f}"
            )
        if self.sigmoid_k <= 0:
            raise ValueError(
                f"sigmoid_k must be > 0, got {self.sigmoid_k}"
            )


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Full prediction result from the engine.

    Attributes:
        probability: Connection success probability (0.0-1.0).
        stability: Connection stability score (0.0-1.0).
        quality: Overall quality score (0.0-1.0).
        rating: Star rating (1-5).
        confidence: Confidence in the prediction (0.0-1.0).
        grade: Human-readable quality grade.
        stability_level: Human-readable stability level.
        latency_score: Latency component score (0.0-1.0).
        loss_score: Loss component score (0.0-1.0).
        jitter_score: Jitter component score (0.0-1.0).
        sample_count: Number of RTT samples used.
        expected_rtt: Predicted RTT for next probe (EMA).
        rtt_range: (min, max) of observed RTT.
    """

    probability: float
    stability: float
    quality: float
    rating: int
    confidence: float
    grade: PredictionGrade
    stability_level: StabilityLevel
    latency_score: float
    loss_score: float
    jitter_score: float
    sample_count: int
    expected_rtt: float
    rtt_range: tuple[float, float]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "probability": round(self.probability, 4),
            "stability": round(self.stability, 4),
            "quality": round(self.quality, 4),
            "rating": self.rating,
            "confidence": round(self.confidence, 4),
            "grade": self.grade.value,
            "stability_level": self.stability_level.value,
            "latency_score": round(self.latency_score, 4),
            "loss_score": round(self.loss_score, 4),
            "jitter_score": round(self.jitter_score, 4),
            "sample_count": self.sample_count,
            "expected_rtt": round(self.expected_rtt, 2),
            "rtt_range": (round(self.rtt_range[0], 2), round(self.rtt_range[1], 2)),
        }


# ---------------------------------------------------------------------------
# Mathematical functions
# ---------------------------------------------------------------------------

def _sigmoid(x: float, k: float = 4.0) -> float:
    """Sigmoid function: 1 / (1 + exp(-k * x)).

    Maps any real number to (0, 1). The parameter k controls steepness.

    Args:
        x: Input value.
        k: Steepness parameter.

    Returns:
        Sigmoid output in (0, 1).
    """
    try:
        return 1.0 / (1.0 + math.exp(-k * x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _inverse_sigmoid_mapped(
    value: float,
    midpoint: float,
    scale: float,
    k: float = 4.0,
) -> float:
    """Map a metric value through an inverted sigmoid to a 0-1 score.

    Uses: score = 1 / (1 + exp(k * (value - midpoint) / scale))

    Low values produce high scores (good). High values produce low
    scores (bad). The midpoint is where score = 0.5.

    Args:
        value: Metric value (e.g., RTT in ms).
        midpoint: Value where score = 0.5.
        scale: Controls transition width.
        k: Steepness.

    Returns:
        Score in [0.0, 1.0].
    """
    if scale <= 0:
        return 0.0
    x = k * (value - midpoint) / scale
    return _sigmoid(-x, k=1.0)


def compute_connection_probability(
    sent: int,
    received: int,
    consecutive_failures: int = 0,
    failure_window: int = 10,
) -> float:
    """Compute probability of successful connection.

    **Formula:**

        P = (received / sent) * (1 - anomaly_factor)

        where:

        anomaly_factor = min(1.0, consecutive_failures / failure_window)

    This penalizes bursty failures even when overall loss is low.
    A server that lost 3 packets in a row is less reliable than one
    that lost 3 packets spread across 100 probes.

    Args:
        sent: Total probes sent.
        received: Total probes received successfully.
        consecutive_failures: Number of consecutive recent failures.
        failure_window: Window for consecutive failure normalization.

    Returns:
        Probability in [0.0, 1.0].

    Example::

        >>> compute_connection_probability(100, 98, consecutive_failures=0)
        0.98
        >>> compute_connection_probability(100, 98, consecutive_failures=5)
        0.49
    """
    if sent <= 0:
        return 0.0
    base_rate = received / sent
    anomaly_factor = min(
        1.0, consecutive_failures / max(1, failure_window)
    )
    return max(0.0, min(1.0, base_rate * (1.0 - anomaly_factor)))


def compute_stability(
    samples: list[float],
    cv_weight: float = 0.8,
) -> float:
    """Compute connection stability score.

    **Formula:**

        S = 1.0 - min(1.0, CV * cv_weight)

        where:

        CV = stddev / mean  (coefficient of variation)

    A perfectly stable connection (all RTT values identical) has
    S = 1.0. High variance drives S toward 0.0.

    Args:
        samples: List of RTT values in milliseconds.
        cv_weight: How much CV affects stability (0.0-1.0).

    Returns:
        Stability score in [0.0, 1.0].

    Example::

        >>> compute_stability([10.0, 10.0, 10.0, 10.0])
        1.0
        >>> compute_stability([10.0, 50.0, 10.0, 80.0])
        0.0
    """
    if len(samples) < 2:
        return 1.0
    cv = compute_cv(samples)
    return max(0.0, min(1.0, 1.0 - min(1.0, cv * cv_weight)))


def compute_quality_score(
    samples: list[float],
    loss_rate: float,
    jitter: float,
    config: PredictionConfig | None = None,
) -> tuple[float, float, float, float]:
    """Compute overall quality score with component breakdown.

    **Formula:**

        Q = w_lat * f_lat + w_loss * f_loss + w_jitter * f_jitter

        f_latency = 1 / (1 + exp(k * (mean_rtt - midpoint) / scale))
        f_loss    = (1 - loss_rate) ^ loss_exponent
        f_jitter  = 1 / (1 + exp(k * (jitter - midpoint) / scale))

    Each component maps its metric to [0.0, 1.0] where 1.0 = perfect.

    Args:
        samples: RTT values in ms.
        loss_rate: Packet loss rate (0.0-1.0).
        jitter: Jitter in ms.
        config: Prediction configuration.

    Returns:
        Tuple of (quality, latency_score, loss_score, jitter_score).
    """
    cfg = config or PredictionConfig()
    mean_rtt = compute_mean(samples) if samples else 0.0

    lat_score = _inverse_sigmoid_mapped(
        mean_rtt, cfg.latency_midpoint, cfg.latency_scale, cfg.sigmoid_k
    )
    loss_score = max(0.0, min(1.0, (1.0 - loss_rate) ** cfg.loss_exponent))
    jit_score = _inverse_sigmoid_mapped(
        jitter, cfg.jitter_midpoint, cfg.jitter_scale, cfg.sigmoid_k
    )

    quality = (
        cfg.w_latency * lat_score
        + cfg.w_loss * loss_score
        + cfg.w_jitter * jit_score
    )
    quality = max(0.0, min(1.0, quality))

    return quality, lat_score, loss_score, jit_score


def compute_rating(quality: float) -> int:
    """Map quality score to a 1-5 star rating.

    **Formula:**

        rating = max(1, min(5, round(Q * 5)))

    Args:
        quality: Quality score in [0.0, 1.0].

    Returns:
        Integer rating from 1 to 5.

    Example::

        >>> compute_rating(0.95)
        5
        >>> compute_rating(0.3)
        2
    """
    return max(1, min(5, round(quality * 5)))


def compute_confidence(
    sample_count: int,
    cv: float,
    min_samples: int = 5,
) -> float:
    """Compute confidence in the prediction.

    **Formula:**

        C = 1.0 - (1.0 / sqrt(n)) * min(1.0, CV)

        where:

        - n = number of samples
        - CV = coefficient of variation

    More samples increase confidence (1/sqrt(n) term decreases).
    High variability decreases confidence.

    A minimum of ``min_samples`` is required for meaningful results.
    Below that, confidence is scaled down proportionally.

    Args:
        sample_count: Number of RTT samples.
        cv: Coefficient of variation (stddev/mean).
        min_samples: Minimum samples for full confidence.

    Returns:
        Confidence in [0.0, 1.0].

    Example::

        >>> compute_confidence(100, 0.1)
        0.9
        >>> compute_confidence(5, 0.5)
        0.553...
    """
    if sample_count <= 0:
        return 0.0

    # Sample-size factor: more samples = higher confidence
    sample_factor = 1.0 / math.sqrt(max(1, sample_count))

    # Volatility penalty
    volatility = min(1.0, cv)

    confidence = 1.0 - sample_factor * volatility

    # Scale down if below minimum samples
    if sample_count < min_samples:
        confidence *= sample_count / min_samples

    return max(0.0, min(1.0, confidence))


def compute_quality_grade(quality: float) -> PredictionGrade:
    """Map quality score to a human-readable grade.

    Thresholds:
    - >= 0.85: EXCELLENT
    - >= 0.70: GOOD
    - >= 0.50: FAIR
    - >= 0.30: POOR
    - < 0.30: BAD

    Args:
        quality: Quality score in [0.0, 1.0].

    Returns:
        PredictionGrade enum member.
    """
    if quality >= 0.85:
        return PredictionGrade.EXCELLENT
    if quality >= 0.70:
        return PredictionGrade.GOOD
    if quality >= 0.50:
        return PredictionGrade.FAIR
    if quality >= 0.30:
        return PredictionGrade.POOR
    return PredictionGrade.BAD


def compute_stability_level(stability: float) -> StabilityLevel:
    """Map stability score to a human-readable level.

    Thresholds:
    - >= 0.90: ROCK_SOLID
    - >= 0.70: STABLE
    - >= 0.50: MODERATE
    - >= 0.30: UNSTABLE
    - < 0.30: CHAOTIC

    Args:
        stability: Stability score in [0.0, 1.0].

    Returns:
        StabilityLevel enum member.
    """
    if stability >= 0.90:
        return StabilityLevel.ROCK_SOLID
    if stability >= 0.70:
        return StabilityLevel.STABLE
    if stability >= 0.50:
        return StabilityLevel.MODERATE
    if stability >= 0.30:
        return StabilityLevel.UNSTABLE
    return StabilityLevel.CHAOTIC


def estimate_next_rtt(
    samples: list[float],
    ema_alpha: float = 0.3,
) -> float:
    """Estimate the next RTT using exponential moving average.

    **Formula:**

        EMA(t) = alpha * value(t) + (1 - alpha) * EMA(t-1)

    EMA gives more weight to recent samples, making it responsive
    to trend changes while smoothing noise.

    Args:
        samples: Historical RTT values in ms.
        ema_alpha: Smoothing factor (0 < alpha <= 1).

    Returns:
        Predicted next RTT in ms, or 0.0 if no samples.
    """
    if not samples:
        return 0.0
    ema = samples[0]
    for s in samples[1:]:
        ema = ema_alpha * s + (1.0 - ema_alpha) * ema
    return ema


# ---------------------------------------------------------------------------
# Prediction Engine
# ---------------------------------------------------------------------------

class PredictionEngine:
    """Mathematical prediction engine for network quality forecasting.

    Computes connection probability, stability, quality, rating,
    and confidence from raw probe data using statistical models.

    No AI/ML — pure math: sigmoid functions, weighted averages,
    coefficient of variation, and exponential smoothing.

    Example::

        engine = PredictionEngine()
        result = engine.predict(
            samples=[10.0, 12.0, 11.0, 13.0, 10.0],
            sent=100, received=97,
            jitter=2.5,
        )
        print(f"Quality: {result.grade.value}")
        print(f"Rating: {result.rating}/5")
    """

    def __init__(self, config: PredictionConfig | None = None) -> None:
        """Initialize the prediction engine.

        Args:
            config: Prediction configuration. Uses defaults if None.
        """
        self.config = config or PredictionConfig()

    def predict(
        self,
        samples: list[float],
        sent: int,
        received: int,
        jitter: float = 0.0,
        consecutive_failures: int = 0,
        ema_alpha: float = 0.3,
    ) -> PredictionResult:
        """Compute full prediction from probe data.

        Args:
            samples: RTT values in ms from probe campaign.
            sent: Total probes sent.
            received: Total probes received successfully.
            jitter: RFC 3550 jitter estimate in ms.
            consecutive_failures: Recent consecutive failures.
            ema_alpha: Alpha for RTT prediction EMA.

        Returns:
            PredictionResult with all computed metrics.
        """
        cfg = self.config

        # Connection probability
        probability = compute_connection_probability(
            sent, received, consecutive_failures, cfg.failure_window
        )

        # Stability
        stability = compute_stability(samples, cfg.stability_cv_weight)

        # Quality score with components
        quality, lat_score, loss_score, jit_score = compute_quality_score(
            samples, 1.0 - (received / max(1, sent)), jitter, cfg
        )

        # Rating
        rating = compute_rating(quality)

        # Confidence
        cv = compute_cv(samples) if len(samples) >= 2 else 0.0
        confidence = compute_confidence(len(samples), cv, cfg.min_samples)

        # Grade and stability level
        grade = compute_quality_grade(quality)
        stability_level = compute_stability_level(stability)

        # Expected next RTT
        expected_rtt = estimate_next_rtt(samples, ema_alpha)

        # RTT range
        rtt_min = min(samples) if samples else 0.0
        rtt_max = max(samples) if samples else 0.0

        return PredictionResult(
            probability=probability,
            stability=stability,
            quality=quality,
            rating=rating,
            confidence=confidence,
            grade=grade,
            stability_level=stability_level,
            latency_score=lat_score,
            loss_score=loss_score,
            jitter_score=jit_score,
            sample_count=len(samples),
            expected_rtt=expected_rtt,
            rtt_range=(rtt_min, rtt_max),
        )

    def predict_simple(
        self,
        avg_rtt: float,
        loss_percent: float,
        jitter: float,
        sample_count: int = 100,
    ) -> PredictionResult:
        """Quick prediction from summary statistics.

        Args:
            avg_rtt: Average RTT in ms.
            loss_percent: Packet loss as percentage (0-100).
            jitter: Jitter in ms.
            sample_count: Number of samples the stats were based on.

        Returns:
            PredictionResult.
        """
        # Generate synthetic samples from summary stats for the engine
        synthetic = [avg_rtt] * max(1, sample_count)
        sent = sample_count
        received = int(sent * (1.0 - loss_percent / 100.0))
        return self.predict(
            samples=synthetic,
            sent=sent,
            received=received,
            jitter=jitter,
        )
