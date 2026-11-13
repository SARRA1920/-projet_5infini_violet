"""Risque du portefeuille d'un utilisateur, à partir des positions et des cours existants.

Lecture seule de portfolios, positions, transactions et price_history : aucune
opération de trading n'est déclenchée ni modifiée ici.

Hypothèse de calcul (identique à /trading/risk) : la composition actuelle du
portefeuille est appliquée à l'historique des cours (simulation historique).
Le cash a un rendement nul. Une position sans cours ou sans historique suffisant
est traitée comme du cash dans les mesures de risque, et signalée.
"""

import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actuarial.risk.expected_shortfall import historical_es
from app.actuarial.risk.risk_metrics import (
    TRADING_DAYS_PER_YEAR,
    annualized_return,
    annualized_volatility,
    cumulative_return,
    herfindahl_index,
    max_drawdown,
    risk_contributions,
    sharpe_ratio,
    sortino_ratio,
)
from app.actuarial.risk.var import MIN_OBSERVATIONS, historical_var
from app.actuarial.services.market_data_service import ReturnsMatrix, returns_matrix
from app.models.models import Asset, Portfolio, Position, Transaction, User
from app.services.prices import PriceUnavailableError, get_current_price
from app.services.risk import value_curve


class PortfolioAccessError(LookupError):
    """Portefeuille inexistant ou appartenant à un autre utilisateur (même réponse : 404)."""


@dataclass
class Holding:
    asset_id: int
    symbol: str
    name: str
    asset_type: str
    quantity: float
    price: float | None
    value: float | None


@dataclass
class Snapshot:
    portfolio: Portfolio
    cash: float
    holdings: list[Holding]

    @property
    def priced(self) -> list[Holding]:
        return [h for h in self.holdings if h.value is not None]

    @property
    def positions_value(self) -> float:
        return sum(h.value for h in self.priced)

    @property
    def total_value(self) -> float:
        return self.cash + self.positions_value


def list_user_portfolios(db: Session, user: User) -> list[Portfolio]:
    return list(db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)))


def get_owned_portfolio(db: Session, user: User, portfolio_id: int | None) -> Portfolio:
    """Portefeuille demandé s'il appartient à l'utilisateur ; sinon son premier portefeuille.

    Isolation : un identifiant appartenant à un autre utilisateur lève la même
    erreur qu'un identifiant inexistant, pour ne rien révéler.
    """
    if portfolio_id is None:
        portfolio = db.scalar(
            select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id).limit(1)
        )
    else:
        portfolio = db.scalar(
            select(Portfolio).where(Portfolio.id == portfolio_id, Portfolio.user_id == user.id)
        )
    if portfolio is None:
        raise PortfolioAccessError("Portefeuille introuvable")
    return portfolio


def portfolio_snapshot(db: Session, portfolio: Portfolio) -> Snapshot:
    """Positions ouvertes valorisées au dernier cours connu (comme /trading/portfolio)."""
    rows = db.execute(
        select(Position, Asset)
        .join(Asset, Position.asset_id == Asset.id)
        .where(Position.portfolio_id == portfolio.id, Position.is_open.is_(True))
        .order_by(Asset.symbol)
    ).all()
    holdings = []
    for position, asset in rows:
        try:
            price = float(get_current_price(db, asset.symbol))
        except PriceUnavailableError:
            price = None
        quantity = float(position.quantity)
        holdings.append(
            Holding(
                asset_id=asset.id,
                symbol=asset.symbol,
                name=asset.name,
                asset_type=asset.asset_type.value,
                quantity=quantity,
                price=price,
                value=None if price is None else quantity * price,
            )
        )
    return Snapshot(portfolio=portfolio, cash=float(portfolio.cash_balance), holdings=holdings)


def _weights(snapshot: Snapshot, matrix: ReturnsMatrix) -> np.ndarray:
    """Poids des actifs de la matrice, en fraction de la valeur totale (cash inclus)."""
    values = {h.asset_id: h.value for h in snapshot.priced}
    total = snapshot.total_value
    return np.array([values[a] / total for a in matrix.asset_ids], dtype=float)


def _exposure(snapshot: Snapshot) -> list[dict]:
    """Valeur et poids par classe d'actifs, liquidités comprises."""
    total = snapshot.total_value
    groups: dict[str, float] = {}
    for holding in snapshot.priced:
        groups[holding.asset_type] = groups.get(holding.asset_type, 0.0) + holding.value
    groups["cash"] = snapshot.cash
    return [
        {"asset_class": name, "value": round(value, 2), "weight": value / total if total else 0.0}
        for name, value in sorted(groups.items(), key=lambda item: -item[1])
    ]


@dataclass
class PortfolioReturns:
    """Tout ce qu'il faut pour mesurer le risque du portefeuille actuel."""

    snapshot: Snapshot
    matrix: ReturnsMatrix
    weights: np.ndarray  # poids des actifs de la matrice (fraction de la valeur totale)
    returns: np.ndarray  # rendements quotidiens du portefeuille, alignés sur matrix.dates
    symbols: dict[int, str]
    warnings: list[str]


def portfolio_returns(db: Session, portfolio: Portfolio, lookback: int | None) -> PortfolioReturns:
    """Composition actuelle, rendements des actifs détenus et rendements du portefeuille."""
    snapshot = portfolio_snapshot(db, portfolio)
    warnings: list[str] = []
    symbols = {h.asset_id: h.symbol for h in snapshot.holdings}

    unpriced = [h.symbol for h in snapshot.holdings if h.value is None]
    if unpriced:
        warnings.append(
            f"Cours indisponible pour {', '.join(unpriced)} : ces lignes ne sont pas valorisées."
        )

    matrix = returns_matrix(db, [h.asset_id for h in snapshot.priced], lookback)
    if matrix.excluded:
        names = ", ".join(symbols[a] for a in matrix.excluded)
        warnings.append(f"Historique insuffisant pour {names} : traité comme du cash dans le risque.")

    weights = _weights(snapshot, matrix) if matrix.asset_ids else np.empty(0)
    returns = matrix.values @ weights if matrix.asset_ids else np.empty(0)
    return PortfolioReturns(snapshot, matrix, weights, returns, symbols, warnings)


def build_dashboard(
    db: Session,
    portfolio: Portfolio,
    lookback: int | None,
    confidence: float,
    horizon: int,
    risk_free_rate: float,
) -> dict:
    """Indicateurs du tableau de bord actuariel, calculés à la demande."""
    data = portfolio_returns(db, portfolio, lookback)
    snapshot, matrix, weights, returns = data.snapshot, data.matrix, data.weights, data.returns
    warnings, symbols = data.warnings, data.symbols

    realized = db.scalar(
        select(func.coalesce(func.sum(Transaction.realized_pnl), 0)).where(
            Transaction.portfolio_id == portfolio.id
        )
    )
    transactions_count = db.scalar(
        select(func.count(Transaction.id)).where(Transaction.portfolio_id == portfolio.id)
    )

    result: dict = {
        "portfolio_id": portfolio.id,
        "portfolio_name": portfolio.name,
        "data_source": "real_market_data",
        "total_value": round(snapshot.total_value, 2),
        "cash": round(snapshot.cash, 2),
        "positions_value": round(snapshot.positions_value, 2),
        "realized_pnl_total": float(Decimal(realized)),
        "transactions_count": transactions_count,
        "confidence": confidence,
        "horizon_days": horizon,
        "lookback_days": lookback,
        "risk_free_rate": risk_free_rate,
        "observations": 0,
        "period_start": None,
        "period_end": None,
        "metrics": None,
        "exposure": _exposure(snapshot),
        "risk_contributions": [],
        "concentration_hhi": herfindahl_index([h.value for h in snapshot.priced]) if snapshot.priced else None,
        "value_curve": [],
        "daily_returns": [],
        "warnings": warnings,
    }

    if not matrix.asset_ids:
        warnings.append("Aucune position avec historique : le portefeuille n'a pas de risque de marché mesurable.")
        return result

    result["observations"] = int(returns.size)
    if returns.size:
        result["period_start"] = matrix.dates[0]
        result["period_end"] = matrix.dates[-1]
    if returns.size < MIN_OBSERVATIONS:
        warnings.append(
            f"Seulement {returns.size} jours communs d'historique (minimum : {MIN_OBSERVATIONS}) : "
            "indicateurs non calculés."
        )
        return result

    var = historical_var(returns, confidence, horizon)
    es = historical_es(returns, confidence, horizon)
    total = snapshot.total_value
    result["metrics"] = {
        "cumulative_return": cumulative_return(returns),
        "annualized_return": annualized_return(returns),
        "annualized_volatility": annualized_volatility(returns.tolist()),
        "var": var,
        "var_amount": round(var * total, 2),
        "expected_shortfall": es,
        "expected_shortfall_amount": round(es * total, 2),
        "max_drawdown": max_drawdown(returns.tolist()),
        "sharpe_ratio": sharpe_ratio(returns, risk_free_rate),
        "sortino_ratio": sortino_ratio(returns, risk_free_rate),
    }

    covariance = np.atleast_2d(np.cov(matrix.values, rowvar=False, ddof=1))
    decomposition = risk_contributions(weights, covariance)
    annual = math.sqrt(TRADING_DAYS_PER_YEAR)
    result["risk_contributions"] = sorted(
        (
            {
                "symbol": symbols[asset_id],
                "weight": float(weights[i]),
                "marginal_contribution": float(decomposition["marginal"][i] * annual),
                "component_contribution": float(decomposition["component"][i] * annual),
                "risk_share": float(decomposition["share"][i]),
            }
            for i, asset_id in enumerate(matrix.asset_ids)
        ),
        key=lambda row: -row["risk_share"],
    )

    dated = list(zip(matrix.dates, returns.tolist()))
    result["value_curve"] = [
        {"date": day, "value": round(value, 2)}
        for day, value in value_curve(dated, Decimal(str(total)))
    ]
    result["daily_returns"] = [{"date": day, "value": value} for day, value in dated]
    return result
