"""Tests du pipeline de prédiction (module IA).

Ces tests utilisent un historique de prix synthétique long (120+ points)
injecté dans une session SQLite en mémoire, puis vérifient que le pipeline
train → predict fonctionne et renvoie des résultats cohérents.

Skippés si scikit-learn n'est pas installé (le reste du projet n'en a pas
besoin ; seul le module IA l'utilise).
"""

import numpy as np
import pytest
from datetime import date, timedelta
from decimal import Decimal

from app.models.models import Asset, AssetType, PriceHistory
from app.ia import prediction as pred


sklearn_available = pytest.importorskip("sklearn")


def _seed_long_history(db, symbol="AAPL", n=150, start=100.0):
    """Injecte un actif + n jours d'historique avec une tendance + bruit."""
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
    """Vide le cache des modèles avant chaque test."""
    pred.clear_cache()
    yield
    pred.clear_cache()


class TestPrediction:
    def test_predict_returns_result(self, db):
        _seed_long_history(db, "AAPL", n=150)
        result = pred.predict(db, "AAPL", horizon=5)
        assert result.symbol == "AAPL"
        assert result.horizon == 5
        assert result.last_close > 0
        assert result.n_samples >= 20
        # Le prix projeté doit être positif.
        assert result.predicted_close > 0
        # Intervalles ordonnés : low <= predicted <= high (en rendement).
        assert result.interval_low <= result.predicted_return <= result.interval_high
        # Confiance bornée.
        assert 0.0 <= result.confidence <= 1.0

    def test_predict_caches_model(self, db):
        _seed_long_history(db, "AAPL", n=150)
        pred.predict(db, "AAPL", horizon=5)
        assert "AAPL:5" in pred._model_cache
        # Deuxième appel : le modèle est réutilisé (même n_samples).
        first = pred.predict(db, "AAPL", horizon=5)
        second = pred.predict(db, "AAPL", horizon=5)
        assert first.n_samples == second.n_samples

    def test_predict_unknown_symbol(self, db):
        with pytest.raises(ValueError, match="Actif inconnu"):
            pred.predict(db, "ZZZZZ", horizon=5)

    def test_predict_short_history(self, db):
        _seed_long_history(db, "SHORT", n=30)  # < MIN_HISTORY (120)
        with pytest.raises(ValueError, match="Historique insuffisant"):
            pred.predict(db, "SHORT", horizon=5)

    def test_min_history_raised_to_120(self, db):
        # Recommandation « expand training data » : le seuil est passé de 60
        # à 120 points (deux régimes de marché au minimum).
        assert pred.MIN_HISTORY == 120
        # 100 points ne suffisent plus (ça suffisait avant).
        _seed_long_history(db, "MID", n=100)
        with pytest.raises(ValueError, match=r"minimum 120"):
            pred.predict(db, "MID", horizon=5)

    def test_predict_invalid_horizon(self, db):
        _seed_long_history(db, "AAPL", n=150)
        with pytest.raises(ValueError, match="horizon"):
            pred.predict(db, "AAPL", horizon=0)
        with pytest.raises(ValueError, match="horizon"):
            pred.predict(db, "AAPL", horizon=50)

    def test_retrain(self, db):
        _seed_long_history(db, "AAPL", n=150)
        n = pred.retrain(db, "AAPL", horizon=5)
        assert n >= 20
        assert "AAPL:5" in pred._model_cache


class TestModelDiagnostics:
    """Diagnostic « pourquoi prédit-il toujours du positif ? » (v3)."""

    def test_diagnostics_shape(self, db):
        _seed_long_history(db, "AAPL", n=150)
        diag = pred.model_diagnostics(db, "AAPL", horizon=5)
        assert diag.symbol == "AAPL"
        assert diag.n_samples >= 20
        # Une ligne par feature, noms uniques, IC borné, tri par |IC| décroissant.
        names = [f["name"] for f in diag.feature_ic]
        assert len(names) == 12 and len(set(names)) == 12
        assert all(-1.0 <= f["ic"] <= 1.0 for f in diag.feature_ic)
        ics = [abs(f["ic"]) for f in diag.feature_ic]
        assert ics == sorted(ics, reverse=True)
        # Biais de signe : parts bornées 0-1.
        assert 0.0 <= diag.pct_predicted_positive <= 1.0
        assert 0.0 <= diag.pct_actual_positive <= 1.0
        # Calibration : 5 quintiles (Q1..Q5), non vides.
        assert [b.bucket for b in diag.calibration] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
        assert all(b.n > 0 for b in diag.calibration)
        # Moyennes cohérentes : moyenne des prédictions ≈ moyenne pondérée
        # des buckets (même échantillon).
        weighted = sum(b.mean_predicted * b.n for b in diag.calibration) / sum(
            b.n for b in diag.calibration
        )
        assert np.isclose(weighted, diag.mean_predicted, atol=1e-9)

    def test_calibration_ranks_trending_data(self, db):
        # Sur une série à tendance nette, le classement du modèle doit être
        # informatif : le quintile Q5 (prédictions les plus hautes) a un
        # rendement réel moyen supérieur au quintile Q1. C'est exactement ce
        # que le diagnostic doit montrer : le classement peut être utile même
        # quand le niveau (biais de signe) est décalé.
        _seed_long_history(db, "AAPL", n=150)
        diag = pred.model_diagnostics(db, "AAPL", horizon=5)
        assert diag.calibration[-1].mean_actual > diag.calibration[0].mean_actual

    def test_bias_reflects_positive_target_mean(self, db):
        # La cause racine du « toujours positif » : sur une série montante,
        # la moyenne des cibles est positive → la part de prédictions
        # positives dépasse largement 50 %.
        _seed_long_history(db, "AAPL", n=150)  # drift +0.05 %/jour
        diag = pred.model_diagnostics(db, "AAPL", horizon=5)
        assert diag.mean_actual > 0
        assert diag.pct_actual_positive > 0.5

    def test_unknown_symbol_raises(self, db):
        with pytest.raises(ValueError, match="Actif inconnu"):
            pred.model_diagnostics(db, "ZZZZZ", horizon=5)
