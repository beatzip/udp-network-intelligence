"""Tests for the Ranking Engine."""

from __future__ import annotations

import pytest

from uni.core.analysis.ranking import (
    RankingConfig,
    RankingEngine,
    ServerScore,
    compute_confidence_score,
    normalize_history,
    normalize_jitter,
    normalize_loss,
    normalize_rtt,
    normalize_success,
)

# ---------------------------------------------------------------------------
# normalize_rtt
# ---------------------------------------------------------------------------


class TestNormalizeRTT:
    def test_low_rtt(self) -> None:
        assert normalize_rtt(5.0) > 0.9

    def test_high_rtt(self) -> None:
        assert normalize_rtt(200.0) < 0.2

    def test_at_midpoint(self) -> None:
        assert normalize_rtt(60.0, midpoint=60.0) == pytest.approx(0.5, abs=0.01)

    def test_zero_scale(self) -> None:
        assert normalize_rtt(50.0, scale=0.0) == 0.0


# ---------------------------------------------------------------------------
# normalize_loss
# ---------------------------------------------------------------------------


class TestNormalizeLoss:
    def test_no_loss(self) -> None:
        assert normalize_loss(0.0) == 1.0

    def test_total_loss(self) -> None:
        assert normalize_loss(1.0) == 0.0

    def test_50_percent(self) -> None:
        assert normalize_loss(0.5) == pytest.approx(0.25)

    def test_high_exponent(self) -> None:
        # Higher exponent = more punishing = lower score for same loss
        assert normalize_loss(0.1, exponent=3.0) < normalize_loss(0.1, exponent=1.0)


# ---------------------------------------------------------------------------
# normalize_jitter
# ---------------------------------------------------------------------------


class TestNormalizeJitter:
    def test_low_jitter(self) -> None:
        assert normalize_jitter(1.0) > 0.9

    def test_high_jitter(self) -> None:
        assert normalize_jitter(50.0) < 0.3

    def test_at_midpoint(self) -> None:
        assert normalize_jitter(12.0, midpoint=12.0) == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# normalize_success
# ---------------------------------------------------------------------------


class TestNormalizeSuccess:
    def test_perfect(self) -> None:
        assert normalize_success(1.0) == 1.0

    def test_zero(self) -> None:
        assert normalize_success(0.0) == 0.0

    def test_clamped(self) -> None:
        assert normalize_success(1.5) == 1.0


# ---------------------------------------------------------------------------
# normalize_history
# ---------------------------------------------------------------------------


class TestNormalizeHistory:
    def test_all_success(self) -> None:
        hist = [(0, True), (1, True), (7, True)]
        assert normalize_history(hist) == 1.0

    def test_all_failure(self) -> None:
        hist = [(0, False), (1, False)]
        assert normalize_history(hist) == 0.0

    def test_empty(self) -> None:
        assert normalize_history([]) == 0.5

    def test_recent_matters_more(self) -> None:
        h1 = [(0, True), (30, False)]
        h2 = [(0, False), (30, True)]
        assert normalize_history(h1) > normalize_history(h2)

    def test_half_life(self) -> None:
        # Longer half-life means old failures matter MORE (less decay)
        h = [(0, True), (14, False)]
        s1 = normalize_history(h, half_life=7)
        s2 = normalize_history(h, half_life=30)
        # With short half_life, old failure decays more → higher score
        assert s1 > s2


# ---------------------------------------------------------------------------
# compute_confidence_score
# ---------------------------------------------------------------------------


class TestConfidenceScore:
    def test_many_samples(self) -> None:
        assert compute_confidence_score(1000, 0.05) > 0.95

    def test_few_samples(self) -> None:
        c = compute_confidence_score(3, 0.5)
        assert c < 0.95

    def test_zero_samples(self) -> None:
        assert compute_confidence_score(0, 0.0) == 0.0

    def test_high_cv(self) -> None:
        c1 = compute_confidence_score(100, 0.0)
        c2 = compute_confidence_score(100, 1.0)
        assert c1 > c2


# ---------------------------------------------------------------------------
# RankingConfig
# ---------------------------------------------------------------------------


class TestRankingConfig:
    def test_defaults(self) -> None:
        cfg = RankingConfig()
        assert cfg.w_rtt == 0.30
        assert cfg.w_loss == 0.25
        assert cfg.w_jitter == 0.15
        assert cfg.w_success == 0.15
        assert cfg.w_history == 0.15

    def test_weights_validation(self) -> None:
        with pytest.raises(ValueError, match="sum to 1.0"):
            RankingConfig(
                w_rtt=0.5, w_loss=0.5, w_jitter=0.5, w_success=0.5, w_history=0.5
            )


# ---------------------------------------------------------------------------
# RankingEngine
# ---------------------------------------------------------------------------


class TestRankingEngine:
    @pytest.fixture
    def engine(self) -> RankingEngine:
        return RankingEngine()

    def test_rank_basic(self, engine: RankingEngine) -> None:
        servers = [
            ServerScore(
                "10.0.0.1",
                avg_rtt=10.0,
                loss_rate=0.01,
                jitter=1.0,
                success_rate=0.99,
                samples=500,
            ),
            ServerScore(
                "10.0.0.2",
                avg_rtt=50.0,
                loss_rate=0.10,
                jitter=10.0,
                success_rate=0.90,
                samples=100,
            ),
        ]
        ranked = engine.rank(servers)
        assert len(ranked) == 2
        assert ranked[0].host == "10.0.0.1"
        assert ranked[0].rank == 1
        assert ranked[1].rank == 2
        assert ranked[0].final_score > ranked[1].final_score

    def test_rank_ordering(self, engine: RankingEngine) -> None:
        servers = [
            ServerScore(
                "bad",
                avg_rtt=100.0,
                loss_rate=0.3,
                jitter=20.0,
                success_rate=0.7,
                samples=10,
            ),
            ServerScore(
                "good",
                avg_rtt=15.0,
                loss_rate=0.01,
                jitter=2.0,
                success_rate=0.99,
                samples=500,
            ),
            ServerScore(
                "mid",
                avg_rtt=40.0,
                loss_rate=0.05,
                jitter=5.0,
                success_rate=0.95,
                samples=200,
            ),
        ]
        ranked = engine.rank(servers)
        assert ranked[0].host == "good"
        assert ranked[1].host == "mid"
        assert ranked[2].host == "bad"

    def test_top_n(self, engine: RankingEngine) -> None:
        servers = [
            ServerScore(
                f"srv{i}",
                avg_rtt=float(i * 10),
                loss_rate=0.01,
                success_rate=0.99,
                samples=100,
            )
            for i in range(10)
        ]
        ranked = engine.rank(servers, top_n=3)
        assert len(ranked) == 3
        assert all(s.rank <= 3 for s in ranked)

    def test_get_best(self, engine: RankingEngine) -> None:
        servers = [
            ServerScore(
                "a", avg_rtt=10.0, loss_rate=0.01, success_rate=0.99, samples=100
            ),
            ServerScore(
                "b", avg_rtt=50.0, loss_rate=0.10, success_rate=0.80, samples=100
            ),
        ]
        best = engine.get_best(servers)
        assert best is not None
        assert best.host == "a"
        assert best.rank == 1

    def test_get_best_empty(self, engine: RankingEngine) -> None:
        assert engine.get_best([]) is None

    def test_score_server(self, engine: RankingEngine) -> None:
        server = ServerScore(
            "test", avg_rtt=15.0, loss_rate=0.02, success_rate=0.98, samples=200
        )
        scored = engine.score_server(server)
        assert scored.host == "test"
        assert 0.0 < scored.final_score <= 1.0

    def test_compare(self, engine: RankingEngine) -> None:
        a = ServerScore(
            "a", avg_rtt=10.0, loss_rate=0.01, success_rate=0.99, samples=200
        )
        b = ServerScore(
            "b", avg_rtt=50.0, loss_rate=0.10, success_rate=0.85, samples=200
        )
        ra, rb, winner = engine.compare(a, b)
        assert winner.host == "a"

    def test_explain(self, engine: RankingEngine) -> None:
        server = ServerScore(
            "test",
            avg_rtt=15.0,
            loss_rate=0.02,
            jitter=3.0,
            success_rate=0.98,
            samples=200,
        )
        explanation = engine.explain(server)
        assert "components" in explanation
        assert "rtt" in explanation["components"]
        assert "loss" in explanation["components"]
        assert "final_score" in explanation
        # Contributions should sum to composite
        contribs = sum(c["contribution"] for c in explanation["components"].values())
        assert contribs == pytest.approx(explanation["composite_score"], abs=0.01)

    def test_confidence_affects_ranking(self, engine: RankingEngine) -> None:
        """Same metrics but different sample counts should differ."""
        a = ServerScore(
            "confident",
            avg_rtt=15.0,
            loss_rate=0.02,
            success_rate=0.98,
            samples=1000,
            cv=0.05,
        )
        b = ServerScore(
            "uncertain",
            avg_rtt=15.0,
            loss_rate=0.02,
            success_rate=0.98,
            samples=5,
            cv=0.3,
        )
        ra = engine.score_server(a)
        rb = engine.score_server(b)
        assert ra.final_score > rb.final_score

    def test_history_affects_ranking(self, engine: RankingEngine) -> None:
        """Server with good history should rank higher."""
        a = ServerScore(
            "stable",
            avg_rtt=20.0,
            loss_rate=0.05,
            success_rate=0.95,
            samples=100,
            history=[(0, True), (1, True), (3, True), (7, True)],
        )
        b = ServerScore(
            "unstable",
            avg_rtt=20.0,
            loss_rate=0.05,
            success_rate=0.95,
            samples=100,
            history=[(0, False), (1, True), (3, False), (7, True)],
        )
        ra = engine.score_server(a)
        rb = engine.score_server(b)
        assert ra.final_score > rb.final_score

    def test_scores_in_range(self, engine: RankingEngine) -> None:
        servers = [
            ServerScore(
                "a",
                avg_rtt=15.0,
                loss_rate=0.02,
                jitter=3.0,
                success_rate=0.98,
                samples=200,
            ),
        ]
        ranked = engine.rank(servers)
        s = ranked[0]
        assert 0.0 <= s.rtt_score <= 1.0
        assert 0.0 <= s.loss_score <= 1.0
        assert 0.0 <= s.jitter_score <= 1.0
        assert 0.0 <= s.success_score <= 1.0
        assert 0.0 <= s.history_score <= 1.0
        assert 0.0 <= s.composite_score <= 1.0
        assert 0.0 <= s.confidence <= 1.0
        assert 0.0 <= s.final_score <= 1.0

    def test_ranked_server_to_dict(self, engine: RankingEngine) -> None:
        server = ServerScore("test", avg_rtt=15.0, success_rate=0.98, samples=100)
        ranked = engine.rank([server])
        d = ranked[0].to_dict()
        assert d["host"] == "test"
        assert d["rank"] == 1
        assert "final_score" in d

    def test_equal_servers(self, engine: RankingEngine) -> None:
        """Two identical servers should have equal scores."""
        s1 = ServerScore(
            "a", avg_rtt=20.0, loss_rate=0.05, success_rate=0.95, samples=100
        )
        s2 = ServerScore(
            "b", avg_rtt=20.0, loss_rate=0.05, success_rate=0.95, samples=100
        )
        ranked = engine.rank([s1, s2])
        assert ranked[0].final_score == pytest.approx(ranked[1].final_score)

    def test_custom_config(self) -> None:
        # Make RTT dominant by giving it 70% weight
        cfg = RankingConfig(
            w_rtt=0.70, w_loss=0.10, w_jitter=0.05, w_success=0.05, w_history=0.10
        )
        engine = RankingEngine(config=cfg)
        servers = [
            ServerScore(
                "fast", avg_rtt=5.0, loss_rate=0.10, success_rate=0.90, samples=100
            ),
            ServerScore(
                "reliable", avg_rtt=50.0, loss_rate=0.01, success_rate=0.99, samples=100
            ),
        ]
        ranked = engine.rank(servers)
        # With 70% RTT weight, fast server should win
        assert ranked[0].host == "fast"
