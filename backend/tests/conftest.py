"""Pytest fixtures: in-memory SQLite database + seed data."""
import pytest
from datetime import date
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.models.models import (
    Asset, AssetType, Portfolio, Position, PriceHistory,
    Transaction, TransactionSide, User, UserRole,
)


@pytest.fixture
def engine():
    """In-memory SQLite engine (single DB for the entire test)."""
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db(engine):
    """Fresh session for each test."""
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def seed_data(db):
    """Injects a user, portfolio, assets, and prices."""
    # --- Assets ---
    aapl = Asset(symbol="AAPL", name="Apple Inc.", asset_type=AssetType.STOCK)
    tlt = Asset(symbol="TLT", name="iShares 20+ Year Treasury Bond ETF", asset_type=AssetType.BOND)
    eurusd = Asset(symbol="EUR/USD", name="Euro / Dollar", asset_type=AssetType.FOREX)
    db.add_all([aapl, tlt, eurusd])
    db.flush()

    # --- Price history (required by get_current_price) ---
    today = date.today()
    db.add(PriceHistory(asset_id=aapl.id, date=today,
                        open=Decimal("170"), high=Decimal("175"),
                        low=Decimal("169"), close=Decimal("172"), volume=1000000))
    db.add(PriceHistory(asset_id=tlt.id, date=today,
                        open=Decimal("95"), high=Decimal("96"),
                        low=Decimal("94"), close=Decimal("95"), volume=500000))
    db.add(PriceHistory(asset_id=eurusd.id, date=today,
                        open=Decimal("1.0800"), high=Decimal("1.0900"),
                        low=Decimal("1.0700"), close=Decimal("1.0850"), volume=None))
    db.flush()

    # --- User + portfolio ---
    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password="fakehash",
        role=UserRole.USER,
    )
    db.add(user)
    db.flush()

    portfolio = Portfolio(
        user_id=user.id,
        cash_balance=Decimal("100000.00"),
    )
    db.add(portfolio)
    db.flush()

    return {
        "user": user,
        "portfolio": portfolio,
        "aapl": aapl,
        "tlt": tlt,
        "eurusd": eurusd,
    }