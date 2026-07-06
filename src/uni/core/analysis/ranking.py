"""Ranking Engine — multi-criteria server ranking with mathematical scoring.

Provides :class:`RankingEngine` for comparing and ranking game servers
based on weighted metrics: RTT, loss, jitter, success rate, history,
and confidence.

Mathematical Model
==================

**Composite Score (CS):**

    CS = Σ(wᵢ × normalize(metricᵢ))

    Where each metric is normalized to [0, 1] and weights sum to 1.0.

**Metric Normalization:**

    RTT Score:      S_rtt  = 1 / (1 + exp(k × (rtt - midpoint) / scale))
    Loss Score:     S_loss = (1 - loss_rate) ^ exponent
    Jitter Score:   S_jit  = 1 / (1 + exp(k × (jitter - midpoint) / scale))
    Success Score:  S_succ = success_rate
    History Score:  S_hist = Σ(2^(-age_days / half_life)) / N
    Confidence:     C      = 1 - (1/√n) × min(1, CV)

**Final Ranking Score:**

    R = CS × C

    Where CS is the composite score and C is the confidence multiplier.
    Servers with more reliable data rank higher.

**Default Weights (calibrated for gaming):**

    w_rtt     = 0.30   (latency is king)
    w_loss    = 0.25   (loss kills gameplay)
    w_jitter  = 0.15   (jitter causes rubber-banding)
    w_success = 0.15   (reliability matters)
    w_history = 0.10   (historical consistency)

**History Decay:**

    Each historical measurement's contribution decays exponentially
    with age. Recent measurements matter more:

    weight(day) = 2^(-day / half_life)

    Default half_life = 7 days. A measurement from 7 days ago
    counts as 50% of a fresh one. 14 days ago = 25%. 30 days ≈ 3%.

Example::

    engine = RankingEngine()
    servers = [
        ServerScore(host="1.1.1.1", avg_rtt=15.0, loss=0.01, jitter=2.0,
                    success_rate=0.99, samples=200, cv=0.05),
        ServerScore(host="2.2.2.2", avg_rtt=45.0, loss=0.05, jitter=8.0,
                    success_rate=0.95, samples=50, cv=0.2),
    ]
    ranked = engine.rank(servers)
    print(f"Best: {ranked[0].host} (score={ranked[0].final_score:.3f})")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RankingConfig:
    """Configuration for the ranking engine.

    Attributes:
        w_rtt: Weight for RTT score.
        w_loss: Weight for loss score.
        w_jitter: Weight for jitter score.
        w_success: Weight for success rate score.
        w_history: Weight for history score.
        rtt_midpoint: RTT value where score = 0.5 (ms).
        rtt_scale: Sigmoid scale for RTT mapping.
        jitter_midpoint: Jitter value where score = 0.5 (ms).
        jitter_scale: Sigmoid scale for jitter mapping.
        loss_exponent: Exponent for loss function.
        sigmoid_k: Steepness of sigmoid function.
        history_half_life: Days for history decay half-life.
        min_samples: Minimum samples for meaningful ranking.
    """

    w_rtt: float = 0.30
    w_loss: float = 0.25
    w_jitter: float = 0.15
    w_success: float = 0.15
    w_history: float = 0.15
    rtt_midpoint: float = 60.0
    rtt_scale: float = 50.0
    jitter_midpoint: float = 12.0
    jitter_scale: float = 15.0
    loss_exponent: float = 2.0
    sigmoid_k: float = 4.0
    history_half_life: float = 7.0
    min_samples: int = 5

    def __post_init__(self) -> None:
        """Validate configuration."""
        w_sum = (
            self.w_rtt + self.w_loss + self.w_jitter
            + self.w_success + self.w_history
        )
        if abs(w_sum - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {w_sum:.3f}")


# ---------------------------------------------------------------------------
# Server score input
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ServerScore:
    """Input data for ranking a single server.

    Attributes:
        host: Server IP or hostname.
        port: Server port.
        avg_rtt: Average RTT in ms.
        loss_rate: Packet loss rate (0.0-1.0).
        jitter: Jitter in ms.
        success_rate: Success rate (0.0-1.0).
        samples: Number of probe samples.
        cv: Coefficient of variation (stddev/mean).
        history: List of (age_days, success_bool) tuples.
        label: Optional display label.
    """

    host: str
    port: int = 27015
    avg_rtt: float = 0.0
    loss_rate: float = 0.0
    jitter: float = 0.0
    success_rate: float = 1.0
    samples: int = 0
    cv: float = 0.0
    history: list[tuple[float, bool]] = field(default_factory=list)
    label: str = ""


# ---------------------------------------------------------------------------
# Ranked result
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class RankedServer:
    """A server with its computed ranking score.

    Attributes:
        host: Server IP/hostname.
        port: Server port.
        label: Display label.
        rtt_score: Normalized RTT score (0.0-1.0).
        loss_score: Normalized loss score (0.0-1.0).
        jitter_score: Normalized jitter score (0.0-1.0).
        success_score: Normalized success rate (0.0-1.0).
        history_score: Normalized history score (0.0-1.0).
        composite_score: Weighted sum of component scores.
        confidence: Confidence multiplier (0.0-1.0).
        final_score: Final ranking score (composite × confidence).
        rank: Position in the ranked list (1-based).
    """

    host: str
    port: int = 27015
    label: str = ""
    rtt_score: float = 0.0
    loss_score: float = 0.0
    jitter_score: float = 0.0
    success_score: float = 0.0
    history_score: float = 0.0
    composite_score: float = 0.0
    confidence: float = 0.0
    final_score: float = 0.0
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "host": self.host,
            "port": self.port,
            "label": self.label,
            "rtt_score": round(self.rtt_score, 4),
            "loss_score": round(self.loss_score, 4),
            "jitter_score": round(self.jitter_score, 4),
            "success_score": round(self.success_score, 4),
            "history_score": round(self.history_score, 4),
            "composite_score": round(self.composite_score, 4),
            "confidence": round(self.confidence, 4),
            "final_score": round(self.final_score, 4),
            "rank": self.rank,
        }


# ---------------------------------------------------------------------------
# Sigmoid helper
# ---------------------------------------------------------------------------

def _sigmoid(x: float, k: float = 4.0) -> float:
    """Sigmoid: 1 / (1 + exp(-k * x))."""
    try:
        return 1.0 / (1.0 + math.exp(-k * x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


# ---------------------------------------------------------------------------
# Normalization functions
# ---------------------------------------------------------------------------

def normalize_rtt(
    avg_rtt: float,
    midpoint: float = 60.0,
    scale: float = 50.0,
    k: float = 4.0,
) -> float:
    """Normalize RTT to [0, 1] using inverted sigmoid.

    **Formula:** S = 1 / (1 + exp(k × (rtt - midpoint) / scale))

    Low RTT → high score. High RTT → low score.

    Args:
        avg_rtt: Average RTT in ms.
        midpoint: Value where score = 0.5.
        scale: Transition width.
        k: Steepness.

    Returns:
        Score in [0.0, 1.0].
    """
    if scale <= 0:
        return 0.0
    x = k * (avg_rtt - midpoint) / scale
    return _sigmoid(-x, k=1.0)


def normalize_loss(loss_rate: float, exponent: float = 2.0) -> float:
    """Normalize packet loss to [0, 1].

    **Formula:** S = (1 - loss_rate) ^ exponent

    Args:
        loss_rate: Loss rate (0.0-1.0).
        exponent: Power factor (higher = more punishing).

    Returns:
        Score in [0.0, 1.0].
    """
    return float(max(0.0, min(1.0, (1.0 - loss_rate) ** exponent)))


def normalize_jitter(
    jitter: float,
    midpoint: float = 12.0,
    scale: float = 15.0,
    k: float = 4.0,
) -> float:
    """Normalize jitter to [0, 1] using inverted sigmoid.

    **Formula:** S = 1 / (1 + exp(k × (jitter - midpoint) / scale))

    Args:
        jitter: Jitter in ms.
        midpoint: Value where score = 0.5.
        scale: Transition width.
        k: Steepness.

    Returns:
        Score in [0.0, 1.0].
    """
    if scale <= 0:
        return 0.0
    x = k * (jitter - midpoint) / scale
    return _sigmoid(-x, k=1.0)


def normalize_success(success_rate: float) -> float:
    """Normalize success rate to [0, 1] (identity).

    **Formula:** S = success_rate

    Args:
        success_rate: Success rate (0.0-1.0).

    Returns:
        Score in [0.0, 1.0].
    """
    return max(0.0, min(1.0, success_rate))


def normalize_history(
    history: list[tuple[float, bool]],
    half_life: float = 7.0,
) -> float:
    """Normalize measurement history to [0, 1] with exponential decay.

    **Formula:**

        S = Σ(w_i) / Σ(w_i_max)

        where:
        w_i      = 2^(-age_days / half_life) if success else 0
        w_i_max  = 2^(-age_days / half_life)  (maximum possible weight)

    Recent successful measurements contribute more. Failed measurements
    contribute zero. The score is the fraction of "earned" weight
    versus maximum possible weight.

    Args:
        history: List of (age_in_days, was_successful) tuples.
        half_life: Days for weight to halve.

    Returns:
        Score in [0.0, 1.0].

    Example::

        >>> normalize_history([(0, True), (1, True), (7, False)])
        0.75
    """
    if not history:
        return 0.5  # neutral when no history

    earned = 0.0
    maximum = 0.0
    for age_days, success in history:
        weight = 2.0 ** (-age_days / half_life)
        maximum += weight
        if success:
            earned += weight

    if maximum <= 0:
        return 0.5
    return earned / maximum


def compute_confidence_score(samples: int, cv: float) -> float:
    """Compute confidence multiplier for ranking.

    **Formula:** C = 1 - (1 / sqrt(n)) × min(1, CV)

    More samples → higher confidence. Higher variance → lower confidence.

    Args:
        samples: Number of probe samples.
        cv: Coefficient of variation.

    Returns:
        Confidence in [0.0, 1.0].
    """
    if samples <= 0:
        return 0.0
    sample_factor = 1.0 / math.sqrt(max(1, samples))
    volatility = min(1.0, cv)
    return max(0.0, min(1.0, 1.0 - sample_factor * volatility))


# ---------------------------------------------------------------------------
# Ranking Engine
# ---------------------------------------------------------------------------

class RankingEngine:
    """Multi-criteria server ranking engine.

    Compares game servers using weighted normalization of RTT, loss,
    jitter, success rate, and historical consistency. Applies a
    confidence multiplier to penalize servers with sparse data.

    The final ranking score is:

        R = CS × C

        where CS = Σ(wᵢ × metricᵢ)  and  C = confidence

    Example::

        engine = RankingEngine()
        servers = [
            ServerScore("10.0.0.1", avg_rtt=12.0, loss_rate=0.01,
                        jitter=1.5, success_rate=0.99, samples=500),
            ServerScore("10.0.0.2", avg_rtt=30.0, loss_rate=0.03,
                        jitter=5.0, success_rate=0.97, samples=200),
        ]
        ranked = engine.rank(servers)
        best = ranked[0]
    """

    def __init__(self, config: RankingConfig | None = None) -> None:
        """Initialize the ranking engine.

        Args:
            config: Ranking configuration. Uses defaults if None.
        """
        self.config = config or RankingConfig()

    def rank(
        self,
        servers: list[ServerScore],
        *,
        top_n: int | None = None,
    ) -> list[RankedServer]:
        """Rank a list of servers by composite score.

        Args:
            servers: List of server scores to rank.
            top_n: Limit output to top N servers. None = all.

        Returns:
            List of RankedServer sorted by final_score descending.
        """
        cfg = self.config
        scored: list[RankedServer] = []

        for server in servers:
            # Normalize each metric
            rtt_s = normalize_rtt(
                server.avg_rtt, cfg.rtt_midpoint, cfg.rtt_scale, cfg.sigmoid_k
            )
            loss_s = normalize_loss(server.loss_rate, cfg.loss_exponent)
            jit_s = normalize_jitter(
                server.jitter, cfg.jitter_midpoint, cfg.jitter_scale,
                cfg.sigmoid_k,
            )
            succ_s = normalize_success(server.success_rate)
            hist_s = normalize_history(server.history, cfg.history_half_life)

            # Weighted composite
            composite = (
                cfg.w_rtt * rtt_s
                + cfg.w_loss * loss_s
                + cfg.w_jitter * jit_s
                + cfg.w_success * succ_s
                + cfg.w_history * hist_s
            )

            # Confidence
            conf = compute_confidence_score(server.samples, server.cv)

            # Final score
            final = composite * conf

            scored.append(RankedServer(
                host=server.host,
                port=server.port,
                label=server.label,
                rtt_score=rtt_s,
                loss_score=loss_s,
                jitter_score=jit_s,
                success_score=succ_s,
                history_score=hist_s,
                composite_score=composite,
                confidence=conf,
                final_score=final,
            ))

        # Sort by final_score descending
        scored.sort(key=lambda s: s.final_score, reverse=True)

        # Assign ranks
        result = []
        for i, s in enumerate(scored[:top_n] if top_n else scored, 1):
            result.append(RankedServer(
                host=s.host,
                port=s.port,
                label=s.label,
                rtt_score=s.rtt_score,
                loss_score=s.loss_score,
                jitter_score=s.jitter_score,
                success_score=s.success_score,
                history_score=s.history_score,
                composite_score=s.composite_score,
                confidence=s.confidence,
                final_score=s.final_score,
                rank=i,
            ))

        return result

    def get_best(self, servers: list[ServerScore]) -> RankedServer | None:
        """Get the single best server.

        Args:
            servers: List of server scores.

        Returns:
            RankedServer with rank=1, or None if empty list.
        """
        ranked = self.rank(servers, top_n=1)
        return ranked[0] if ranked else None

    def score_server(self, server: ServerScore) -> RankedServer:
        """Score a single server without ranking context.

        Args:
            server: Server to score.

        Returns:
            RankedServer with rank=0 (no ranking context).
        """
        ranked = self.rank([server])
        return ranked[0] if ranked else RankedServer(host=server.host, port=server.port)

    def compare(
        self, server_a: ServerScore, server_b: ServerScore
    ) -> tuple[RankedServer, RankedServer, RankedServer]:
        """Compare two servers head-to-head.

        Returns:
            Tuple of (ranked_a, ranked_b, winner).
        """
        ranked = self.rank([server_a, server_b])
        return ranked[0], ranked[1], ranked[0]

    def explain(self, server: ServerScore) -> dict[str, Any]:
        """Get a detailed breakdown of how a server is scored.

        Args:
            server: Server to analyze.

        Returns:
            Dictionary with all component scores and their contributions.
        """
        cfg = self.config
        rtt_s = normalize_rtt(
            server.avg_rtt, cfg.rtt_midpoint, cfg.rtt_scale, cfg.sigmoid_k
        )
        loss_s = normalize_loss(server.loss_rate, cfg.loss_exponent)
        jit_s = normalize_jitter(
            server.jitter, cfg.jitter_midpoint, cfg.jitter_scale, cfg.sigmoid_k
        )
        succ_s = normalize_success(server.success_rate)
        hist_s = normalize_history(server.history, cfg.history_half_life)
        conf = compute_confidence_score(server.samples, server.cv)

        composite = (
            cfg.w_rtt * rtt_s
            + cfg.w_loss * loss_s
            + cfg.w_jitter * jit_s
            + cfg.w_success * succ_s
            + cfg.w_history * hist_s
        )

        return {
            "host": server.host,
            "port": server.port,
            "components": {
                "rtt": {
                    "raw": server.avg_rtt,
                    "score": round(rtt_s, 4),
                    "weight": cfg.w_rtt,
                    "contribution": round(cfg.w_rtt * rtt_s, 4),
                },
                "loss": {
                    "raw": server.loss_rate,
                    "score": round(loss_s, 4),
                    "weight": cfg.w_loss,
                    "contribution": round(cfg.w_loss * loss_s, 4),
                },
                "jitter": {
                    "raw": server.jitter,
                    "score": round(jit_s, 4),
                    "weight": cfg.w_jitter,
                    "contribution": round(cfg.w_jitter * jit_s, 4),
                },
                "success_rate": {
                    "raw": server.success_rate,
                    "score": round(succ_s, 4),
                    "weight": cfg.w_success,
                    "contribution": round(cfg.w_success * succ_s, 4),
                },
                "history": {
                    "raw_count": len(server.history),
                    "score": round(hist_s, 4),
                    "weight": cfg.w_history,
                    "contribution": round(cfg.w_history * hist_s, 4),
                },
            },
            "composite_score": round(composite, 4),
            "confidence": round(conf, 4),
            "final_score": round(composite * conf, 4),
        }
