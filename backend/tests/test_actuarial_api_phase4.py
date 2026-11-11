"""Tests d'intégration de la phase 4 : modèles de pertes, capital économique, laboratoire."""
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.models import PriceHistory, TransactionSide, User, UserRole
from app.services.trading import place_order

DAYS = 300


@pytest.fixture
def market(db, seed_data):
    """300 jours de cours (graine fixe, rendements à queue épaisse) pour AAPL et TLT."""
    rng = np.random.default_rng(5)
    today = date.today()
    for asset, start in ((seed_data["aapl"], 150.0), (seed_data["tlt"], 90.0)):
        price = start
        for offset in range(DAYS, 0, -1):
            price *= 1 + 0.012 * rng.standard_t(4)
            close = Decimal(str(round(price, 4)))
            db.add(PriceHistory(asset_id=asset.id, date=today - timedelta(days=offset),
                                open=close, high=close, low=close, close=close, volume=None))
    db.commit()
    return seed_data


@pytest.fixture
def client(db):
    state = {}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    test_client = TestClient(app)
    test_client.state = state
    yield test_client
    app.dependency_overrides.clear()


SIMULATION = {
    "frequency_model": "poisson", "frequency_params": {"lam": 2.0}, "periods_per_year": 12,
    "severity_model": "lognormal", "severity_params": {"mu": 7.0, "sigma": 1.0},
    "n_years": 5000, "seed": 1,
}


class TestLossData:
    def test_market_events_from_real_prices(self, client, market):
        client.state["user"] = market["user"]
        body = client.post("/api/actuarial/loss-model/fit",
                           json={"source": "market", "symbol": "AAPL", "threshold": 0.015, "notional": 10_000}).json()
        dataset = body["dataset"]
        assert dataset["data_source"] == "real_market_data"
        assert dataset["periods_per_year"] == 12
        assert sum(r["count"] for r in dataset["counts_by_period"]) == dataset["events"]
        assert dataset["amounts"]["min"] >= 150  # seuil de 1,5 % de 10 000
        pareto = next(f for f in body["severity_fits"] if f["model"] == "pareto")
        assert pareto["params"]["xm"] == pytest.approx(150)

    def test_portfolio_events_use_owned_portfolio(self, client, db, market):
        place_order(db, market["portfolio"].id, "AAPL", TransactionSide.BUY, quantity=Decimal("200"))
        db.commit()
        client.state["user"] = market["user"]
        body = client.post("/api/actuarial/loss-model/fit", json={"source": "market", "threshold": 0.005}).json()
        assert body["dataset"]["events"] > 0

    def test_synthetic_data_is_labelled_and_recovers_parameters(self, client, market):
        client.state["user"] = market["user"]
        payload = {"source": "synthetic", "frequency_model": "poisson", "frequency_params": {"lam": 4},
                   "severity_model": "gamma", "severity_params": {"shape": 2, "scale": 1000}, "periods": 2000}
        body = client.post("/api/actuarial/loss-model/fit", json=payload).json()
        assert body["dataset"]["data_source"] == "synthetic"
        poisson = next(f for f in body["frequency_fits"] if f["model"] == "poisson")
        assert poisson["params"]["lam"] == pytest.approx(4, rel=0.05)
        assert body["best_severity"] == "gamma"

    def test_manual_data_and_validation(self, client, market):
        client.state["user"] = market["user"]
        payload = {"source": "manual", "counts": [1, 3, 0, 2, 4, 1], "amounts": [100, 250, 80, 1200, 300, 90, 55, 410]}
        body = client.post("/api/actuarial/loss-model/fit", json=payload).json()
        assert body["dataset"]["data_source"] == "user_assumption"
        assert body["warnings"]
        assert client.post("/api/actuarial/loss-model/fit", json={"source": "manual"}).status_code == 422

    def test_unknown_asset(self, client, market):
        client.state["user"] = market["user"]
        response = client.post("/api/actuarial/loss-model/fit", json={"source": "market", "symbol": "ZZZ"})
        assert response.status_code == 404


class TestLossSimulation:
    def test_capital_and_stress(self, client, market):
        client.state["user"] = market["user"]
        body = client.post("/api/actuarial/loss-model/simulate", json=SIMULATION).json()
        assert body["annual_frequency_params"]["lam"] == pytest.approx(24)
        assert body["aggregate"]["mean"] == pytest.approx(body["analytic"]["mean"], rel=0.03)
        capital = body["economic_capital"]
        assert capital["capital"] == pytest.approx(capital["var"] - capital["expected_loss"])
        stress = {row["name"]: row for row in body["stress"]}
        assert stress["Central"]["capital_change"] == pytest.approx(0.0, abs=1e-9)
        assert stress["Combiné adverse"]["capital"] > stress["Central"]["capital"]

    def test_custom_scenarios_and_reproducibility(self, client, market):
        client.state["user"] = market["user"]
        payload = {**SIMULATION, "scenarios": [{"name": "Double fréquence", "frequency_multiplier": 2}]}
        first = client.post("/api/actuarial/loss-model/simulate", json=payload).json()
        second = client.post("/api/actuarial/loss-model/simulate", json=payload).json()
        assert [r["name"] for r in first["stress"]] == ["Double fréquence"]
        assert first["risk_measures"] == second["risk_measures"]

    def test_invalid_parameters(self, client, market):
        client.state["user"] = market["user"]
        bad = {**SIMULATION, "severity_model": "pareto", "severity_params": {"alpha": 2.0}}
        assert client.post("/api/actuarial/loss-model/simulate", json=bad).status_code == 422


class TestLab:
    def test_catalog_lists_all_models_without_ml(self, client, market):
        client.state["user"] = market["user"]
        ids = {m["id"] for m in client.get("/api/actuarial/lab/catalog").json()}
        assert ids == {"var_historical", "var_parametric", "var_monte_carlo", "gbm", "vasicek", "cir", "hull_white",
                       "markowitz", "poisson", "negative_binomial", "gamma", "lognormal", "pareto"}

    def test_compare_var_methods_on_a_basket(self, client, market):
        client.state["user"] = market["user"]
        base = {"symbols": ["AAPL", "TLT"], "confidence": 0.99, "n_simulations": 2000}
        runs = [{**base, "model": m} for m in ("var_historical", "var_parametric", "var_monte_carlo")]
        items = client.post("/api/actuarial/lab/compare", json={"runs": runs}).json()
        assert all(item["ok"] for item in items)
        sources = [item["result"]["data_source"] for item in items]
        assert sources == ["real_market_data", "real_market_data", "simulated"]
        for item in items:
            metrics = {m["key"]: m["value"] for m in item["result"]["metrics"]}
            assert metrics["es"] >= metrics["var"]

    def test_gbm_calibrates_when_params_missing(self, client, market):
        client.state["user"] = market["user"]
        body = client.post("/api/actuarial/lab/run", json={"model": "gbm", "symbols": ["AAPL"], "n_simulations": 1000}).json()
        assert body["params_used"]["s0"] == pytest.approx(172.0)
        assert body["notes"]

    def test_distribution_models_and_errors_are_isolated(self, client, market):
        client.state["user"] = market["user"]
        runs = [{"model": "pareto", "params": {"alpha": 3, "xm": 100}, "n_simulations": 1000},
                {"model": "negative_binomial", "params": {"r": 2, "p": 0.4}, "n_simulations": 1000},
                {"model": "inconnu"}]
        items = client.post("/api/actuarial/lab/compare", json={"runs": runs}).json()
        assert [i["ok"] for i in items] == [True, True, False]
        pareto = {m["key"]: m["value"] for m in items[0]["result"]["metrics"]}
        assert pareto["mean"] == pytest.approx(150.0)

    def test_history_is_per_user(self, client, db, market):
        client.state["user"] = market["user"]
        client.post("/api/actuarial/lab/run", json={"model": "poisson", "params": {"lam": 3}, "n_simulations": 500})
        assert len(client.get("/api/actuarial/lab/runs").json()) == 1
        other = User(email="z@example.com", username="z", hashed_password="x", role=UserRole.USER)
        db.add(other)
        db.commit()
        client.state["user"] = other
        assert client.get("/api/actuarial/lab/runs").json() == []
