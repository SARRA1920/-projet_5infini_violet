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
        _seed_long_history(db, "SHORT", n=30)  # < MIN_HISTORY (60)
        with pytest.raises(ValueError, match="Historique insuffisant"):
            pred.predict(db, "SHORT", horizon=5)

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
