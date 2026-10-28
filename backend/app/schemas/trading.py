from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models.models import TransactionSide


class OrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    side: TransactionSide
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=6)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)


class TransactionOut(BaseModel):
    id: int
    symbol: str
    side: TransactionSide
    quantity: Decimal
    price: Decimal
    stop_loss: Decimal | None
    take_profit: Decimal | None
    realized_pnl: Decimal | None = None
    executed_at: datetime


class PositionOut(BaseModel):
    """Position ouverte valorisée au dernier cours.

    Si le cours est indisponible, les champs de valorisation valent null
    et price_error explique pourquoi.
    """

    symbol: str
    name: str
    quantity: Decimal
    average_buy_price: Decimal
    current_price: Decimal | None
    market_value: Decimal | None
    unrealized_pnl: Decimal | None
    unrealized_pnl_pct: Decimal | None
    price_error: str | None = None


class PortfolioOut(BaseModel):
    cash: Decimal
    positions: list[PositionOut]
    positions_value: Decimal
    total_value: Decimal
    valuation_complete: bool  # False si au moins une position n'a pas de cours


class RiskOut(BaseModel):
    """Performance et risque du portefeuille actuel (simulation historique).

    Les pourcentages sont en points de pourcentage (1.84 pour 1,84 %). Les champs de
    risque valent null si l'historique est insuffisant.
    """

    total_value: Decimal
    initial_capital: Decimal
    total_return_pct: Decimal
    realized_pnl_total: Decimal
    days_used: int
    volatility_pct: Decimal | None
    var_95_pct: Decimal | None
    var_95_amount: Decimal | None
    max_drawdown_pct: Decimal | None
    max_drawdown_amount: Decimal | None
