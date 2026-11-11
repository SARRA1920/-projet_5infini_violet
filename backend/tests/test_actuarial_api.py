"""Tests d'intégration des routes /api/actuarial (base SQLite en mémoire)."""
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.models import Portfolio, PriceHistory, TransactionSide, User, UserRole
from app.services.trading import place_order

DAYS = 80


@pytest.fixture
def market(db, seed_data):
    """80 jours de cours pour AAPL et TLT (marche aléatoire à graine fixe).

    seed_data a déjà un cours daté d'aujourd'hui : on ajoute les jours précédents.
    """
    rng = np.random.default_rng(0)
    today = date.today()
    for asset, start in ((seed_data["aapl"], 150.0), (seed_data["tlt"], 90.0)):
        price = start
        for offset in range(DAYS, 0, -1):
            price *= 1 + rng.normal(0, 0.01)
            close = Decimal(str(round(price, 4)))
            db.add(PriceHistory(asset_id=asset.id, date=today - timedelta(days=offset),
                                open=close, high=close, low=close, close=close, volume=1000))
    db.commit()
    return seed_data


@pytest.fixture
def client(db):
    """Client HTTP branché sur la session de test ; l'utilisateur courant est réglable."""
    state = {}
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    test_client = TestClient(app)
    test_client.state = state
    yield test_client
    app.dependency_overrides.clear()


def _other_user(db) -> tuple[User, Portfolio]:
    user = User(email="other@example.com", username="other", hashed_password="x", role=UserRole.USER)
    db.add(user)
    db.flush()
    portfolio = Portfolio(user_id=user.id, cash_balance=Decimal("100000.00"))
    db.add(portfolio)
    db.commit()
    return user, portfolio


class TestDashboard:
    def test_requires_authentication(self, db):
        app.dependency_overrides[get_db] = lambda: db
        try:
            response = TestClient(app).get("/api/actuarial/dashboard")
        finally:
            app.dependency_overrides.clear()
        assert response.status_code in (401, 403)

    def test_cash_only_portfolio_has_no_metrics(self, client, seed_data):
        client.state["user"] = seed_data["user"]
        body = client.get("/api/actuarial/dashboard").json()
        assert body["metrics"] is None
        assert body["total_value"] == 100000.0
        assert body["exposure"] == [{"asset_class": "cash", "value": 100000.0, "weight": 1.0}]
        assert body["warnings"]

    def test_metrics_with_positions(self, client, db, market):
        portfolio = market["portfolio"]
        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("100"))
        place_order(db, portfolio.id, "TLT", TransactionSide.BUY, quantity=Decimal("200"))
        db.commit()
        client.state["user"] = market["user"]

        body = client.get("/api/actuarial/dashboard", params={"confidence": 0.99, "horizon": 10}).json()
        metrics = body["metrics"]
        assert body["data_source"] == "real_market_data"
        assert body["observations"] == DAYS
        assert metrics["expected_shortfall"] >= metrics["var"]
        assert metrics["var_amount"] == pytest.approx(metrics["var"] * body["total_value"], abs=0.01)
        assert sum(row["risk_share"] for row in body["risk_contributions"]) == pytest.approx(1.0)
        assert sum(row["weight"] for row in body["exposure"]) == pytest.approx(1.0)
        assert body["value_curve"][-1]["value"] == pytest.approx(body["total_value"], abs=0.01)
        assert body["transactions_count"] == 2

    def test_lookback_limits_observations(self, client, db, market):
        place_order(db, market["portfolio"].id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()
        client.state["user"] = market["user"]
        body = client.get("/api/actuarial/dashboard", params={"lookback": 40}).json()
        assert body["observations"] == 40

    def test_rejects_unsupported_parameters(self, client, seed_data):
        client.state["user"] = seed_data["user"]
        assert client.get("/api/actuarial/dashboard", params={"confidence": 0.9}).status_code == 422
        assert client.get("/api/actuarial/dashboard", params={"horizon": 5}).status_code == 422


class TestIsolation:
    def test_cannot_read_another_users_portfolio(self, client, db, seed_data):
        other, other_portfolio = _other_user(db)
        client.state["user"] = seed_data["user"]
        response = client.get("/api/actuarial/dashboard", params={"portfolio_id": other_portfolio.id})
        assert response.status_code == 404

        client.state["user"] = other
        assert client.get("/api/actuarial/dashboard", params={"portfolio_id": other_portfolio.id}).status_code == 200

    def test_portfolio_list_is_per_user(self, client, db, seed_data):
        other, other_portfolio = _other_user(db)
        client.state["user"] = seed_data["user"]
        ids = [row["id"] for row in client.get("/api/actuarial/portfolios").json()]
        assert ids == [seed_data["portfolio"].id]
        assert other_portfolio.id not in ids


class TestAssets:
    def test_lists_history_extent(self, client, market):
        client.state["user"] = market["user"]
        rows = {row["symbol"]: row for row in client.get("/api/actuarial/assets").json()}
        assert rows["AAPL"]["observations"] == DAYS + 1
        assert rows["EUR/USD"]["observations"] == 1
