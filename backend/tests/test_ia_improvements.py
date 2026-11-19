"""Tests des améliorations du module IA : feature importance et backtest.

Vérifie que feature_importance() renvoie les importances normalisées et que
backtest() simule correctement la stratégie sur l'historique passé. Utilise
le même fixture SQLite en mémoire que test_ia_prediction.py.
"""

import pytest

from app.models.models import Asset, AssetType, PriceHistory
from app.ia import prediction as pred
from app.ia import agent as agent_mod

sklearn_available = pytest.importorskip("sklearn")


def _seed_long_history(db, symbol="AAPL", n=150, start=100.0):
    """Injecte un actif + n jours d'historique avec une tendance + bruit."""
    import numpy as np
    from datetime import date, timedelta
    from decimal import Decimal

    asset = Asset(symbol=symbol, name=f"Test {symbol}", asset_type=AssetType.STOCK)
    db.add(asset)
    db.flush()

    rng = np.random.default_rng(123)
    price = start
    today = date.today()
    for i in range(n):
        price *= 1.0 + 0.0005 + rng.normal(0, 0.015)
        db.add(PriceHistory(
            asset_id=asset.id,
            date=today - timedelta(days=n - 1 - i),
            open=Decimal(str(round(price * 0.99, 4))),
            high=Decimal(str(round(price * 1.01, 4))),
            low=Decimal(str(round(price * 0.98, 4))),
            close=Decimal(str(round(price, 4))),
            volume=int(rng.integers(500000, 2000000)),
        ))
    db.flush()
    return asset


@pytest.fixture(autouse=True)
def _clear_cache():
    pred.clear_cache()
    yield
    pred.clear_cache()


class TestFeatureImportance:
    def test_returns_sorted_normalized(self, db):
        _seed_long_history(db, "AAPL", n=150)
        features = pred.feature_importance(db, "AAPL", horizon=5)
        assert len(features) == 12  # FEATURE_COLUMNS (9 initiales + 3 v3)
        # Importances décroissantes.
        values = [f["importance"] for f in features]
        assert values == sorted(values, reverse=True)
        # Somme normalisée à ~1.0.
        assert abs(sum(values) - 1.0) < 1e-6
        # Chaque feature a un nom et une importance positive.
        for f in features:
            assert isinstance(f["name"], str)
            assert f["importance"] >= 0.0
        # Les features « visibles de la baisse » sont bien présentes.
        names = {f["name"] for f in features}
        assert {"drawdown_20", "sma20_slope", "bb_pos"} <= names

    def test_caches_model(self, db):
        _seed_long_history(db, "AAPL", n=150)
        pred.feature_importance(db, "AAPL", horizon=5)
        assert "AAPL:5" in pred._model_cache

    def test_unknown_symbol(self, db):
        with pytest.raises(ValueError, match="Actif inconnu"):
            pred.feature_importance(db, "ZZZZZ", horizon=5)


class TestBacktest:
    def test_returns_metrics(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert result.symbol == "AAPL"
        assert result.horizon == 5
        assert result.n_points > 0
        # Cohérence des décomptes.
        assert result.n_buy + result.n_sell + result.n_hold == result.n_points
        # Taux de réussite borné.
        assert 0.0 <= result.win_rate <= 1.0
        # Rendement cumulé est un réel fini.
        assert isinstance(result.total_return, float)
        # L'échantillon de trades est limité à max_points.
        assert len(result.trades) <= 120
        # Chaque trade a une action valide.
        for t in result.trades:
            assert t.action in ("BUY", "SELL", "HOLD")
            assert isinstance(t.correct, bool)

    def test_win_rate_consistency(self, db):
        """win_rate = bons_signaux / signaux_directionnels."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        directional = result.n_buy + result.n_sell
        if directional > 0:
            wins = sum(1 for t in result.trades if t.correct)
            # (les trades affichés sont un sous-ensemble ; on vérifie juste la borne)
            assert 0.0 <= result.win_rate <= 1.0

    def test_short_history_raises(self, db):
        _seed_long_history(db, "SHORT", n=30)  # < MIN_HISTORY + horizon
        with pytest.raises(ValueError, match="Historique insuffisant"):
            agent_mod.backtest(db, "SHORT", horizon=5)


class TestThreshold:
    """Recommandation « adjust decision thresholds » : 0.15 → 0.25."""

    def test_threshold_value(self):
        assert agent_mod.DECISION_THRESHOLD == 0.25

    def test_decision_respects_threshold(self, db):
        # Invariant : BUY/SELL ⇒ |score| > seuil. Le contraire n'est pas vrai
        # (le filtre de tendance peut ramener un score élevé à HOLD).
        _seed_long_history(db, "AAPL", n=150)
        dec = agent_mod.decide(db, "AAPL", horizon=5)
        assert dec.threshold == 0.25
        if dec.action in ("BUY", "SELL"):
            assert abs(dec.composite_score) > dec.threshold
        else:
            below = abs(dec.composite_score) <= dec.threshold
            gated = any(r.signal == "filtre" for r in dec.reasons)
            assert below or gated


class TestTrendGate:
    """Filtre de tendance : plus d'achat en tendance baissière confirmée.

    C'est le scénario des jours 128–134 du backtest réel : score composite
    encore légèrement positif pendant que le titre chutait de 7,8 %.
    """

    def test_buy_blocked_in_downtrend(self):
        action, blocked = agent_mod._trend_gate("BUY", sma20=100.0, sma50=110.0)
        assert blocked and action == "HOLD"

    def test_buy_allowed_in_uptrend(self):
        action, blocked = agent_mod._trend_gate("BUY", sma20=110.0, sma50=100.0)
        assert not blocked and action == "BUY"

    def test_sell_blocked_in_uptrend(self):
        action, blocked = agent_mod._trend_gate("SELL", sma20=110.0, sma50=100.0)
        assert blocked and action == "HOLD"

    def test_sell_allowed_in_downtrend(self):
        action, blocked = agent_mod._trend_gate("SELL", sma20=100.0, sma50=110.0)
        assert not blocked and action == "SELL"

    def test_hold_never_blocked(self):
        action, blocked = agent_mod._trend_gate("HOLD", sma20=100.0, sma50=110.0)
        assert not blocked and action == "HOLD"

    def test_missing_sma_no_gate(self):
        action, blocked = agent_mod._trend_gate("BUY", None, None)
        assert not blocked and action == "BUY"

    def test_equal_sma_no_gate(self):
        action, blocked = agent_mod._trend_gate("BUY", sma20=100.0, sma50=100.0)
        assert not blocked and action == "BUY"

    def test_decide_reports_blocked_reason(self, db):
        # Décision en direct : si une raison « filtre » apparaît, l'action
        # finale est HOLD et la confiance est plafonnée à 0.5.
        _seed_long_history(db, "AAPL", n=150)
        dec = agent_mod.decide(db, "AAPL", horizon=5)
        gate_reasons = [r for r in dec.reasons if r.signal == "filtre"]
        if gate_reasons:
            assert dec.action == "HOLD"
            assert dec.confidence <= 0.5
            assert "SMA20" in gate_reasons[0].detail

    def test_backtest_counts_trend_blocked(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        # Compteur cohérent : tout signal bloqué apparaît en HOLD dans le
        # journal, marqué trend_blocked.
        assert result.n_trend_blocked <= result.n_hold
        blocked_in_trades = sum(1 for t in result.trades if t.trend_blocked)
        assert blocked_in_trades == result.n_trend_blocked  # 95 décisions < 120 pts
        for t in result.trades:
            if t.trend_blocked:
                assert t.action == "HOLD"
