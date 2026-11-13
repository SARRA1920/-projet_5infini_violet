"""Tests d'intégration des routes de la phase 3 : Risk Analytics, stochastique, obligations, Markowitz."""
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.actuarial.models import ActuarialRun, BondTerms
from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.models import Portfolio, PriceHistory, Transaction, TransactionSide, User, UserRole
from app.services.trading import place_order

DAYS = 160


@pytest.fixture
def market(db, seed_data):
    """160 jours de cours (graine fixe) pour AAPL, TLT et EUR/USD, avant le cours du jour de seed_data."""
    rng = np.random.default_rng(1)
    today = date.today()
    for asset, start, vol in ((seed_data["aapl"], 150.0, 0.015), (seed_data["tlt"], 90.0, 0.008),
                              (seed_data["eurusd"], 1.08, 0.004)):
        price = start
        for offset in range(DAYS, 0, -1):
            price *= 1 + rng.normal(0.0003, vol)
            close = Decimal(str(round(price, 4)))
            db.add(PriceHistory(asset_id=asset.id, date=today - timedelta(days=offset),
                                open=close, high=close, low=close, close=close, volume=None))
    db.commit()
    return seed_data


@pytest.fixture
def invested(db, market):
    portfolio = market["portfolio"]
    place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("100"))
    place_order(db, portfolio.id, "TLT", TransactionSide.BUY, quantity=Decimal("200"))
    db.commit()
    return market


@pytest.fixture
def client(db):
    state = {}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    test_client = TestClient(app)
    test_client.state = state
    yield test_client
    app.dependency_overrides.clear()


def runs(db) -> int:
    return db.scalar(select(func.count(ActuarialRun.id)))


class TestPortfolioRisk:
    def test_full_report(self, client, invested):
        client.state["user"] = invested["user"]
        pid = invested["portfolio"].id
        body = client.get(f"/api/actuarial/portfolio-risk/{pid}", params={"n_simulations": 2000}).json()
        assert len(body["var_table"]) == 18  # 3 méthodes x 2 niveaux x 3 horizons
        for row in body["var_table"]:
            assert row["expected_shortfall"] >= row["var"] - 1e-12
        matrix = np.array(body["correlation"]["matrix"])
        np.testing.assert_allclose(np.diag(matrix), 1.0)
        np.testing.assert_allclose(matrix, matrix.T)
        assert body["backtest"]["observations"] == DAYS - 100
        assert sum(b["count"] for b in body["monte_carlo_distribution"]) == 2000

    def test_seed_makes_monte_carlo_reproducible(self, client, invested):
        client.state["user"] = invested["user"]
        url = f"/api/actuarial/portfolio-risk/{invested['portfolio'].id}"
        first = client.get(url, params={"n_simulations": 1000, "seed": 7}).json()["var_table"]
        second = client.get(url, params={"n_simulations": 1000, "seed": 7}).json()["var_table"]
        assert first == second

    def test_other_users_portfolio_is_hidden(self, client, db, invested):
        intruder = User(email="x@example.com", username="x", hashed_password="x", role=UserRole.USER)
        db.add(intruder)
        db.commit()
        client.state["user"] = intruder
        assert client.get(f"/api/actuarial/portfolio-risk/{invested['portfolio'].id}").status_code == 404

    def test_cash_portfolio_is_rejected_with_message(self, client, market):
        client.state["user"] = market["user"]
        response = client.get(f"/api/actuarial/portfolio-risk/{market['portfolio'].id}")
        assert response.status_code == 422
        assert "Aucune position" in response.json()["detail"]


class TestBasket:
    def test_basket_var_and_run_recorded(self, client, db, market):
        client.state["user"] = market["user"]
        payload = {"symbols": ["AAPL", "TLT"], "weights": [3, 1], "notional": 50000, "confidence": 0.99,
                   "horizon": 10, "n_simulations": 1000}
        body = client.post("/api/actuarial/risk/var", json=payload).json()
        assert [a["weight"] for a in body["assets"]] == pytest.approx([0.75, 0.25])
        assert body["total_value"] == 50000
        assert runs(db) == 1
        assert client.post("/api/actuarial/risk/expected-shortfall", json=payload).status_code == 200

    def test_unknown_symbol(self, client, market):
        client.state["user"] = market["user"]
        response = client.post("/api/actuarial/risk/var", json={"symbols": ["ZZZ"], "n_simulations": 1000})
        assert response.status_code == 422


class TestStochastic:
    def test_calibrate_gbm_on_real_prices(self, client, market):
        client.state["user"] = market["user"]
        body = client.post("/api/actuarial/stochastic/calibrate", json={"model": "gbm", "symbol": "AAPL"}).json()
        assert body["data_source"] == "real_market_data"
        assert body["params"]["s0"] == pytest.approx(172.0)  # cours du jour de seed_data
        assert 0.05 < body["params"]["sigma"] < 0.5

    def test_rate_model_needs_a_series(self, client, market):
        client.state["user"] = market["user"]
        response = client.post("/api/actuarial/stochastic/calibrate", json={"model": "vasicek"})
        assert response.status_code == 422

    def test_simulate_vasicek(self, client, db, market):
        client.state["user"] = market["user"]
        payload = {"model": "vasicek", "params": {"r0": 0.03, "a": 0.8, "b": 0.04, "sigma": 0.01},
                   "horizon": 2, "steps": 24, "n_simulations": 4000, "seed": 3}
        body = client.post("/api/actuarial/stochastic/simulate", json=payload).json()
        assert body["data_source"] == "simulated"
        assert body["terminal"]["mean"] == pytest.approx(body["analytics"]["analytic_mean"], abs=0.001)
        assert len(body["sensitivity"]) == 5
        assert runs(db) == 1

    def test_hull_white_with_curve(self, client, market):
        client.state["user"] = market["user"]
        payload = {"model": "hull_white", "horizon": 3, "steps": 36, "n_simulations": 4000,
                   "params": {"a": 0.3, "sigma": 0.01, "curve_maturities": [1, 5, 10], "curve_rates": [0.03, 0.035, 0.04]}}
        body = client.post("/api/actuarial/stochastic/simulate", json=payload).json()
        assert body["analytics"]["zero_coupon_mc"] == pytest.approx(body["analytics"]["zero_coupon_analytic"], rel=5e-3)

    def test_missing_parameters(self, client, market):
        client.state["user"] = market["user"]
        response = client.post("/api/actuarial/stochastic/simulate", json={"model": "cir", "params": {"r0": 0.03}})
        assert response.status_code == 422


class TestFixedIncome:
    def test_etf_without_terms_gives_market_stats_only(self, client, market):
        client.state["user"] = market["user"]
        rows = {r["symbol"]: r for r in client.get("/api/actuarial/fixed-income/bonds").json()}
        assert rows["TLT"]["has_terms"] is False
        detail = client.get(f"/api/actuarial/fixed-income/{rows['TLT']['asset_id']}").json()
        assert detail["analysis"] is None
        assert "non disponibles" in detail["message"]
        assert detail["market"]["observations"] == DAYS + 1

    def test_non_bond_asset_is_not_found(self, client, market):
        client.state["user"] = market["user"]
        assert client.get(f"/api/actuarial/fixed-income/{market['aapl'].id}").status_code == 404

    def test_theoretical_bond(self, client, market):
        client.state["user"] = market["user"]
        payload = {"bond": {"face_value": 100, "coupon_rate": 0.05, "coupon_frequency": 1,
                            "maturity_date": "2029-01-15", "day_count": "30/360"},
                   "settlement_date": "2026-01-15", "ytm": 0.05}
        body = client.post("/api/actuarial/fixed-income/analyze", json=payload).json()
        assert body["clean_price"] == pytest.approx(100.0)
        assert len(body["cash_flows"]) == 3
        assert body["curve_source"] == "flat_at_ytm"

    def test_price_or_yield_required(self, client, market):
        client.state["user"] = market["user"]
        payload = {"bond": {"coupon_rate": 0.05, "maturity_date": "2030-01-01"}}
        assert client.post("/api/actuarial/fixed-income/analyze", json=payload).status_code == 422

    def test_terms_are_admin_only_then_used(self, client, db, market):
        tlt = market["tlt"]
        terms = {"face_value": 100, "coupon_rate": 0.04, "coupon_frequency": 2,
                 "maturity_date": "2045-05-15", "source": "Saisie de test"}
        client.state["user"] = market["user"]
        assert client.put(f"/api/actuarial/fixed-income/{tlt.id}/terms", json=terms).status_code == 403

        admin = User(email="adm@example.com", username="adm", hashed_password="x", role=UserRole.ADMIN)
        db.add(admin)
        db.commit()
        client.state["user"] = admin
        assert client.put(f"/api/actuarial/fixed-income/{tlt.id}/terms", json=terms).status_code == 200
        assert db.scalar(select(func.count(BondTerms.id))) == 1
        detail = client.get(f"/api/actuarial/fixed-income/{tlt.id}").json()
        assert detail["analysis"]["clean_price"] == pytest.approx(95.0)  # dernier cours de seed_data


class TestMarkowitz:
    def test_optimization_never_trades(self, client, db, invested):
        client.state["user"] = invested["user"]
        transactions_before = db.scalar(select(func.count(Transaction.id)))
        payload = {"extra_symbols": ["EUR/USD"], "max_weight": 0.6, "frontier_points": 8}
        body = client.post("/api/actuarial/optimization/markowitz", json=payload).json()
        assert body["symbols"] == ["AAPL", "TLT", "EUR/USD"]
        for allocation in body["optimized"].values():
            assert sum(allocation["weights"]) == pytest.approx(1.0)
            assert max(allocation["weights"]) <= 0.6 + 1e-6
        assert body["current"]["weights"][2] == 0.0
        assert db.scalar(select(func.count(Transaction.id))) == transactions_before
        assert runs(db) == 1

    def test_needs_two_assets(self, client, market):
        client.state["user"] = market["user"]
        response = client.post("/api/actuarial/optimization/markowitz", json={"extra_symbols": ["AAPL"]})
        assert response.status_code == 422

    def test_infeasible_cap(self, client, invested):
        client.state["user"] = invested["user"]
        response = client.post("/api/actuarial/optimization/markowitz", json={"max_weight": 0.3})
        assert response.status_code == 422
        assert "Infaisable" in response.json()["detail"]

    def test_foreign_portfolio(self, client, db, invested):
        other = User(email="o@example.com", username="o", hashed_password="x", role=UserRole.USER)
        db.add(other)
        db.flush()
        db.add(Portfolio(user_id=other.id, cash_balance=Decimal("1000")))
        db.commit()
        client.state["user"] = other
        response = client.post("/api/actuarial/optimization/markowitz",
                               json={"portfolio_id": invested["portfolio"].id})
        assert response.status_code == 404
