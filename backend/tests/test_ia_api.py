"""Tests d'intégration des routes /api/ia modifiées (SQLite en mémoire).

Vérifie le contrat HTTP du backtest walk-forward (nouveaux paramètres et
métriques) et du sentiment multilingue. Suit le même pattern que
test_actuarial_api.py (dépendances surchargées, base SQLite en mémoire).
"""
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.models import Asset, AssetType, PriceHistory, User, UserRole
from app.ia import prediction as pred

sklearn_available = pytest.importorskip("sklearn")


@pytest.fixture
def market(db):
    """150 jours de cours pour AAPL (tendance + bruit à graine fixe)."""
    asset = Asset(symbol="AAPL", name="Apple Inc.", asset_type=AssetType.STOCK)
    db.add(asset)
    db.flush()
    rng = np.random.default_rng(123)
    price = 100.0
    today = date.today()
    for i in range(150):
        price *= 1.0 + 0.0005 + rng.normal(0, 0.015)
        db.add(PriceHistory(
            asset_id=asset.id,
            date=today - timedelta(days=150 - 1 - i),
            open=Decimal(str(round(price * 0.99, 4))),
            high=Decimal(str(round(price * 1.01, 4))),
            low=Decimal(str(round(price * 0.98, 4))),
            close=Decimal(str(round(price, 4))),
            volume=int(rng.integers(500000, 2000000)),
        ))
    db.flush()
    return {"asset": asset}


@pytest.fixture
def client(db):
    """Client HTTP branché sur la session de test, utilisateur authentifié."""
    user = User(email="ia@example.com", username="iauser",
                hashed_password="x", role=UserRole.USER)
    db.add(user)
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _clear_cache():
    pred.clear_cache()
    yield
    pred.clear_cache()


class TestBacktestEndpoint:
    def test_backtest_returns_walk_forward_metrics(self, client, market):
        resp = client.get("/api/ia/backtest/AAPL", params={"horizon": 5})
        assert resp.status_code == 200
        data = resp.json()
        # Nouvelles métriques présentes et cohérentes.
        assert data["n_points"] > 0
        assert 0.0 <= data["win_rate"] <= 1.0
        assert data["final_equity"] > 0
        assert -1.0 <= data["buy_hold_return"] <= 5.0
        assert 0.0 <= data["max_drawdown"] <= 1.0
        assert -1.0 <= data["information_coefficient"] <= 1.0
        assert data["n_opened"] + data["n_skipped"] <= data["n_buy"]
        assert data["allow_short"] is False
        assert data["capital_fraction"] == 0.25
        assert data["fee_bps"] == 10.0
        # Courbe d'équité : stratégie et buy & hold alignés jour par jour.
        curve = data["equity_curve"]
        assert len(curve) == data["n_points"] + (
            data["horizon"] - 1
        ) or len(curve) >= data["n_points"]
        assert curve[0]["buy_hold"] == pytest.approx(1.0)
        assert curve[-1]["strategy"] == pytest.approx(data["final_equity"])
        # Trades : garanties anti-fuite et champs d'exécution.
        trades = data["trades"]
        assert trades, "au moins une décision attendue"
        for t in trades:
            assert t["train_last_index"] + data["horizon"] <= t["index"]
            assert t["train_size"] >= 20
            if t["opened"]:
                assert t["action"] == "BUY"  # short interdit par défaut
        # Compteur du filtre de tendance (v3) cohérent avec le journal.
        assert data["n_trend_blocked"] == sum(
            1 for t in trades if t["trend_blocked"]
        )

    def test_backtest_params_are_honored(self, client, market):
        resp = client.get(
            "/api/ia/backtest/AAPL",
            params={
                "horizon": 5,
                "capital_fraction": 0.5,
                "fee_bps": 25,
                "slippage_bps": 10,
                "allow_short": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["capital_fraction"] == 0.5
        assert data["fee_bps"] == 25.0
        assert data["slippage_bps"] == 10.0
        assert data["allow_short"] is True

    def test_backtest_rejects_out_of_range_params(self, client, market):
        resp = client.get("/api/ia/backtest/AAPL", params={"capital_fraction": 2.0})
        assert resp.status_code == 422
        resp = client.get("/api/ia/backtest/AAPL", params={"fee_bps": 500})
        assert resp.status_code == 422

    def test_backtest_unknown_symbol(self, client, market):
        resp = client.get("/api/ia/backtest/ZZZZZ", params={"horizon": 5})
        assert resp.status_code == 400
        assert "inconnu" in resp.json()["detail"]


class TestSentimentEndpoint:
    def test_french_text_analyzed(self, client, market):
        resp = client.post("/api/ia/sentiment/analyze",
                           json={"text": "Apple annonce des bénéfices record"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "positif"
        assert data["score"] > 0.1
        # Le moteur réellement utilisé est exposé (affiché sous « Méthode »).
        assert data["source"] == "lexicon-fr"

    def test_english_text_analyzed(self, client, market):
        resp = client.post("/api/ia/sentiment/analyze",
                           json={"text": "Apple misses forecasts and warns of weak demand"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["label"] == "négatif"

    def test_symbol_sentiment_with_headlines(self, client, market, monkeypatch):
        """RÉGRESSION : GET /sentiment/{symbol} plantait en 500 (AttributeError
        sur details[0].source) dès que des titres pertinents étaient trouvés.

        Avec des titres réels (mockés), l'endpoint doit répondre 200, filtrer
        les titres hors sujet et exposer la source du moteur.
        """
        from app.ia import sentiment as sent

        raw = [
            "Prediction: SpaceX Will Be the Largest Company in the World by 2040",
            "Walmart, Costco see some panic-buying ahead of the holidays",
            "Apple beats earnings expectations",
        ]
        monkeypatch.setattr(sent, "_fetch_rss_titles", lambda url, limit=30: raw)
        sent.clear_headline_cache()
        try:
            resp = client.get("/api/ia/sentiment/AAPL")
        finally:
            sent.clear_headline_cache()
        assert resp.status_code == 200
        data = resp.json()
        assert data["aggregate_label"] == "positif"
        assert data["source"] in ("vader", "lexicon", "lexicon-fr")
        titles = [h["title"] for h in data["headlines"]]
        # Les titres SpaceX / Walmart (hors sujet) sont filtrés.
        assert titles == ["Apple beats earnings expectations"]
        assert data["headlines"][0]["source"] in ("vader", "lexicon")

    def test_symbol_sentiment_without_network(self, client, market, monkeypatch):
        """RSS injoignable → 200, score neutre, liste vide (jamais de 500)."""
        from app.ia import sentiment as sent

        def boom(url, limit=30):
            raise OSError("réseau indisponible")

        monkeypatch.setattr(sent, "_fetch_rss_titles", boom)
        sent.clear_headline_cache()
        try:
            resp = client.get("/api/ia/sentiment/AAPL")
        finally:
            sent.clear_headline_cache()
        assert resp.status_code == 200
        data = resp.json()
        assert data["aggregate_score"] == 0.0
        assert data["aggregate_label"] == "neutre"
        assert data["headlines"] == []


class TestAgentEndpoint:
    def test_decision_includes_threshold(self, client, market):
        resp = client.get("/api/ia/agent/AAPL", params={"horizon": 5})
        assert resp.status_code == 200
        data = resp.json()
        # Le seuil est exposé (le frontend l'affiche dynamiquement).
        assert data["threshold"] == 0.25
        assert data["action"] in ("BUY", "SELL", "HOLD")
        # Invariant : BUY/SELL ⇒ |score| > seuil (le filtre de tendance peut
        # ramener un score directionnel à HOLD, jamais l'inverse).
        if data["action"] in ("BUY", "SELL"):
            assert abs(data["composite_score"]) > data["threshold"]
        else:
            below = abs(data["composite_score"]) <= data["threshold"]
            gated = any(r["signal"] == "filtre" for r in data["reasons"])
            assert below or gated
        signals = [r["signal"] for r in data["reasons"]]
        assert "prediction" in signals and "technique" in signals


class TestDiagnosticsEndpoint:
    def test_diagnostics_contract(self, client, market):
        resp = client.get("/api/ia/diagnostics/AAPL", params={"horizon": 5})
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "AAPL"
        assert data["n_samples"] >= 20
        names = [f["name"] for f in data["feature_ic"]]
        assert len(names) == 12 and len(set(names)) == 12
        assert all(-1.0 <= f["ic"] <= 1.0 for f in data["feature_ic"])
        # Tri par |IC| décroissant.
        ics = [abs(f["ic"]) for f in data["feature_ic"]]
        assert ics == sorted(ics, reverse=True)
        # Biais de signe borné.
        assert 0.0 <= data["pct_predicted_positive"] <= 1.0
        assert 0.0 <= data["pct_actual_positive"] <= 1.0
        # Calibration : quintiles Q1..Q5 non vides.
        buckets = data["calibration"]
        assert [b["bucket"] for b in buckets] == ["Q1", "Q2", "Q3", "Q4", "Q5"]
        assert all(b["n"] > 0 for b in buckets)
        # Importance et IC portent sur les mêmes features.
        assert {f["name"] for f in data["feature_importance"]} == set(names)

    def test_diagnostics_unknown_symbol(self, client, market):
        resp = client.get("/api/ia/diagnostics/ZZZZZ", params={"horizon": 5})
        assert resp.status_code == 400
