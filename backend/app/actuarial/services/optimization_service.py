"""Optimisation de l'allocation (Markowitz) et comparaison avec le portefeuille actuel.

Univers : actifs détenus (valorisés) + actifs ajoutés par l'utilisateur. Les poids
portent sur la partie investie (hors liquidités). Les quantités cibles sont
indicatives : aucun ordre n'est jamais passé par ce module.
"""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial.optimization.efficient_frontier import efficient_frontier
from app.actuarial.optimization.markowitz import annualize, max_sharpe, min_variance, stats, target_return
from app.actuarial.risk.var import MIN_OBSERVATIONS
from app.actuarial.services.market_data_service import returns_matrix
from app.actuarial.services.portfolio_risk_service import portfolio_snapshot
from app.actuarial.services.risk_analytics_service import InsufficientDataError, correlation
from app.models.models import Asset, Portfolio
from app.services.prices import PriceUnavailableError, get_current_price


def optimize(
    db: Session,
    portfolio: Portfolio,
    extra_symbols: list[str],
    lookback: int | None,
    risk_free_rate: float,
    max_weight: float,
    allow_short: bool,
    target: float | None,
    frontier_points: int,
) -> dict:
    snapshot = portfolio_snapshot(db, portfolio)
    held = {h.asset_id: h for h in snapshot.priced}
    wanted = {s.strip().upper() for s in extra_symbols}
    extras = db.scalars(select(Asset).where(Asset.symbol.in_(wanted))).all() if wanted else []
    unknown = wanted - {a.symbol for a in extras}
    if unknown:
        raise ValueError(f"Actif(s) inconnu(s) : {', '.join(sorted(unknown))}")

    symbols = {h.asset_id: h.symbol for h in snapshot.priced} | {a.id: a.symbol for a in extras}
    if len(symbols) < 2:
        raise InsufficientDataError("Il faut au moins deux actifs : ajoutez des actifs à l'univers")

    matrix = returns_matrix(db, sorted(symbols), lookback)
    warnings = []
    if matrix.excluded:
        warnings.append(
            "Exclus faute d'historique : " + ", ".join(symbols[a] for a in matrix.excluded)
        )
    if len(matrix.asset_ids) < 2:
        raise InsufficientDataError("Moins de deux actifs avec un historique de cours")
    if len(matrix.dates) < MIN_OBSERVATIONS:
        raise InsufficientDataError(f"Seulement {len(matrix.dates)} jours communs (minimum : {MIN_OBSERVATIONS})")

    names = [symbols[a] for a in matrix.asset_ids]
    mu, cov = annualize(matrix.values)
    portfolios = {
        "min_variance": min_variance(cov, max_weight, allow_short),
        "max_sharpe": max_sharpe(mu, cov, risk_free_rate, max_weight, allow_short),
    }
    if target is not None:
        portfolios["target_return"] = target_return(mu, cov, target, max_weight, allow_short)

    invested = sum(held[a].value for a in matrix.asset_ids if a in held)
    current = None
    if invested > 0:
        current_weights = np.array([held[a].value / invested if a in held else 0.0 for a in matrix.asset_ids])
        current = {"weights": current_weights.tolist(), **stats(current_weights, mu, cov, risk_free_rate)}
    notional = invested if invested > 0 else snapshot.total_value
    if invested <= 0:
        warnings.append("Aucune position investie : quantités indicatives calculées sur la valeur totale du portefeuille.")
    if allow_short:
        warnings.append("Vente à découvert activée : allocation purement théorique, non réalisable dans le simulateur.")

    prices = {a: h.price for a, h in held.items()}
    for asset_id in matrix.asset_ids:
        if asset_id not in prices:
            try:
                prices[asset_id] = float(get_current_price(db, symbols[asset_id]))
            except PriceUnavailableError:
                prices[asset_id] = None

    best = portfolios["max_sharpe"]
    rebalance = []
    for i, asset_id in enumerate(matrix.asset_ids):
        current_qty = held[asset_id].quantity if asset_id in held else 0.0
        target_value = float(best[i] * notional)
        price = prices[asset_id]
        target_qty = target_value / price if price else None
        rebalance.append(
            {
                "symbol": names[i],
                "price": price,
                "current_quantity": current_qty,
                "target_value": round(target_value, 2),
                "target_quantity": target_qty,
                "quantity_change": None if target_qty is None else target_qty - current_qty,
            }
        )

    return {
        "portfolio_id": portfolio.id,
        "data_source": "real_market_data",
        "observations": len(matrix.dates),
        "period_start": matrix.dates[0],
        "period_end": matrix.dates[-1],
        "symbols": names,
        "assets": [
            {"symbol": names[i], "expected_return": float(mu[i]), "volatility": float(np.sqrt(cov[i, i]))}
            for i in range(len(names))
        ],
        "correlation": {"symbols": names, "matrix": correlation(matrix.values)},
        "constraints": {"max_weight": max_weight, "allow_short": allow_short, "risk_free_rate": risk_free_rate},
        "current": current,
        "optimized": {key: {"weights": w.tolist(), **stats(w, mu, cov, risk_free_rate)} for key, w in portfolios.items()},
        "frontier": efficient_frontier(mu, cov, risk_free_rate, frontier_points, max_weight, allow_short),
        "notional": round(notional, 2),
        "rebalance": rebalance,
        "warnings": warnings,
    }
