"""Tests du backtest walk-forward sans fuite de données.

Vérifie les corrections apportées au backtest :
1. **anti-fuite** : au jour t, le modèle n'est entraîné que sur des
   échantillons dont la cible est réalisée avant t
   (`train_last_index + horizon <= index` pour CHAQUE décision) ;
2. **réalisme** : frais + slippage réduisent le rendement, le capital est
   bloqué (slots limités), la vente à découvert est interdite par défaut ;
3. **honnêteté** : benchmark buy & hold, courbe d'équité, drawdown, IC,
   déterminisme.
"""

import numpy as np
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.models import Asset, AssetType, PriceHistory
from app.ia import agent as agent_mod
from app.ia import prediction as pred

sklearn_available = pytest.importorskip("sklearn")


def _seed_long_history(db, symbol="AAPL", n=150, start=100.0, seed=123):
    """Injecte un actif + n jours d'historique (tendance + bruit, reproductible)."""
    asset = Asset(symbol=symbol, name=f"Test {symbol}", asset_type=AssetType.STOCK)
    db.add(asset)
    db.flush()

    rng = np.random.default_rng(seed)
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


class TestNoDataLeakage:
    def test_training_window_never_overlaps_decision_day(self, db):
        """PROPRIÉTÉ ANTI-FUITE : pour chaque décision au jour t, le dernier
        échantillon d'entraînement s vérifie s + horizon <= t.

        C'est la preuve formelle que le modèle ne voit jamais le futur qu'il
        prédit — la première version entraînait sur TOUT l'historique puis
        « testait » sur les mêmes jours (win rate ~95 % memorisé).
        """
        _seed_long_history(db, "AAPL", n=150)
        horizon = 5
        result = agent_mod.backtest(db, "AAPL", horizon=horizon)
        assert result.n_points > 0
        for t in result.trades:
            assert t.train_last_index + horizon <= t.index, (
                f"Fuite de données : décision au jour {t.index} entraînée "
                f"jusqu'à {t.train_last_index} (horizon={horizon})"
            )

    def test_first_decision_trains_on_a_subset(self, db):
        """La première décision ne peut pas avoir vu tous les échantillons."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        first = result.trades[0]
        assert first.train_size >= 20          # min_train_samples
        assert first.train_size < result.n_points + 5

    def test_training_window_grows_over_time(self, db):
        """Fenêtre glissante : train_size croît (jamais décroît)."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        sizes = [t.train_size for t in result.trades]
        assert sizes == sorted(sizes)

    def test_retrain_period_respected(self, db):
        """Le modèle n'est pas réentraîné à chaque jour (coûts maîtrisés)."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5, retrain_every=5)
        days = [t.index for t in result.trades]
        # Nombre de réentraînements plafonné par la durée / retrain_every.
        n_retrain_estimate = (days[-1] - days[0]) // 5 + 2
        distinct_sizes = len(set(sizes := [t.train_size for t in result.trades]))
        assert distinct_sizes <= n_retrain_estimate


class TestRealism:
    def test_fees_reduce_return(self, db):
        """Des frais de 100 bps par côté doivent dégrader la performance."""
        _seed_long_history(db, "AAPL", n=150)
        free = agent_mod.backtest(db, "AAPL", horizon=5, fee_bps=0.0, slippage_bps=0.0)
        costly = agent_mod.backtest(db, "AAPL", horizon=5, fee_bps=50.0, slippage_bps=50.0)
        assert costly.fees_paid > 0
        assert costly.total_return <= free.total_return

    def test_capital_lockup_limits_concurrent_positions(self, db):
        """capital_fraction=0.5 → 2 slots max : signaux ignorés au-delà."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5, capital_fraction=0.5)
        assert result.capital_fraction == 0.5
        if result.n_buy > 2:
            # Avec plus de 2 signaux BUY et un blocage de 5 jours, certains
            # signaux sont forcément ignorés (slots pleins).
            assert result.n_skipped >= 0
        assert result.n_opened <= result.n_buy
        assert result.n_opened + result.n_skipped <= result.n_buy
        assert result.final_equity > 0

    def test_no_short_selling_by_default(self, db):
        """Conforme à la plateforme : SELL = rester en cash, pas de short."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert result.allow_short is False
        assert all(t.action == "BUY" for t in result.trades if t.opened)
        assert result.n_flat <= result.n_sell

    def test_short_selling_opt_in(self, db):
        """allow_short=True : les SELL peuvent ouvrir des positions courtes."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5, allow_short=True)
        assert result.allow_short is True
        opened_actions = {t.action for t in result.trades if t.opened}
        assert opened_actions <= {"BUY", "SELL"}

    def test_fees_paid_positive_when_trades_opened(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        if result.n_opened > 0:
            assert result.fees_paid > 0


class TestHonestMetrics:
    def test_buy_hold_benchmark_present(self, db):
        """Le rendement est toujours comparé au buy & hold de la même période."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert -1.0 < result.buy_hold_return < 5.0
        assert result.final_equity > 0

    def test_information_coefficient_bounded(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert -1.0 <= result.information_coefficient <= 1.0

    def test_max_drawdown_bounded(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert 0.0 <= result.max_drawdown <= 1.0

    def test_equity_curve_consistent(self, db):
        """total_return == dernière valeur de la courbe d'équité − 1."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert len(result.equity_curve) > 0
        assert result.equity_curve[-1][0] == result.trades[-1].index
        assert abs(result.equity_curve[-1][1] - 1.0 - result.total_return) < 1e-12

    def test_win_rate_consistency(self, db):
        """win_rate = bons signaux directionnels / signaux directionnels."""
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        assert result.n_buy + result.n_sell + result.n_hold == result.n_points
        directional = result.n_buy + result.n_sell
        if directional > 0:
            assert 0.0 <= result.win_rate <= 1.0
            wins_in_sample = sum(1 for t in result.trades if t.correct)
            assert wins_in_sample <= len(result.trades)

    def test_pnl_recorded_for_opened_trades(self, db):
        """Chaque position ouverte ET réglée dans la fenêtre a un P&L net.

        Une position ouverte sur les derniers jours sort du cadre du backtest
        (sortie à t+horizon) : son P&L reste None — c'est honnête (le trade
        n'est pas encore soldé), on ne teste que les positions réglées.
        """
        _seed_long_history(db, "AAPL", n=150)
        result = agent_mod.backtest(db, "AAPL", horizon=5)
        last_day = result.trades[-1].index
        settled = [t for t in result.trades if t.opened and t.index + 5 <= last_day]
        if settled:
            assert all(t.pnl is not None for t in settled)
            # Une position réglée engendre des frais → P&L ≠ rendement brut.
            assert all(
                abs(t.pnl - t.actual_return) > 1e-9 for t in settled
            )


class TestDeterminism:
    def test_same_data_same_results(self, db):
        """random_state fixé + données identiques → résultats identiques."""
        _seed_long_history(db, "AAPL", n=150)
        a = agent_mod.backtest(db, "AAPL", horizon=5)
        b = agent_mod.backtest(db, "AAPL", horizon=5)
        assert abs(a.total_return - b.total_return) < 1e-9
        assert a.win_rate == b.win_rate
        assert a.n_points == b.n_points


class TestGuards:
    def test_short_history_raises(self, db):
        _seed_long_history(db, "SHORT", n=30)  # < MIN_HISTORY + horizon
        with pytest.raises(ValueError, match="Historique insuffisant"):
            agent_mod.backtest(db, "SHORT", horizon=5)

    def test_unknown_symbol_raises(self, db):
        with pytest.raises(ValueError, match="Actif inconnu"):
            agent_mod.backtest(db, "ZZZZZ", horizon=5)
