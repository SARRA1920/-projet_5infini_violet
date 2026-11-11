"""Risk Analytics : VaR et Expected Shortfall par trois méthodes, corrélations, backtesting.

Deux points d'entrée :
- portfolio_risk_report : portefeuille de l'utilisateur (composition actuelle) ;
- basket_risk : panier libre d'actifs et de poids (exercice, aucun ordre passé).
"""

import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial.risk.backtesting import rolling_var_backtest
from app.actuarial.risk.expected_shortfall import historical_es, monte_carlo_es, parametric_es
from app.actuarial.risk.risk_metrics import (
    TRADING_DAYS_PER_YEAR,
    annualized_return,
    annualized_volatility,
    max_drawdown,
    risk_contributions,
    sharpe_ratio,
    sortino_ratio,
)
from app.actuarial.risk.var import (
    CONFIDENCE_LEVELS,
    HORIZONS,
    MIN_OBSERVATIONS,
    historical_var,
    monte_carlo_var,
    parametric_var,
    simulate_portfolio_returns,
)
from app.actuarial.services.market_data_service import returns_matrix
from app.actuarial.services.portfolio_risk_service import portfolio_returns
from app.actuarial.stats import histogram
from app.models.models import Asset, Portfolio


class InsufficientDataError(ValueError):
    """Historique trop court pour un calcul fiable."""


def correlation(values: np.ndarray) -> list[list[float]]:
    if values.shape[1] == 1:
        return [[1.0]]
    return np.round(np.corrcoef(values, rowvar=False), 6).tolist()


def var_es_table(
    asset_returns: np.ndarray, weights: np.ndarray, total_value: float, n_simulations: int, seed: int | None
) -> tuple[list[dict], dict[int, np.ndarray]]:
    """VaR et ES (historique, paramétrique, Monte Carlo) pour chaque niveau et horizon.

    Une seule simulation Monte Carlo par horizon (même graine), réutilisée pour
    les deux niveaux de confiance.
    """
    returns = asset_returns @ weights
    simulated = {
        h: simulate_portfolio_returns(asset_returns, weights, h, n_simulations, None if seed is None else seed + h)
        for h in HORIZONS
    }
    rows = []
    for confidence in CONFIDENCE_LEVELS:
        for horizon in HORIZONS:
            values = {
                "historical": (historical_var(returns, confidence, horizon), historical_es(returns, confidence, horizon)),
                "parametric": (parametric_var(returns, confidence, horizon), parametric_es(returns, confidence, horizon)),
                "monte_carlo": (monte_carlo_var(simulated[horizon], confidence), monte_carlo_es(simulated[horizon], confidence)),
            }
            for method, (var, es) in values.items():
                rows.append(
                    {
                        "method": method,
                        "confidence": confidence,
                        "horizon_days": horizon,
                        "var": var,
                        "var_amount": round(var * total_value, 2),
                        "expected_shortfall": es,
                        "expected_shortfall_amount": round(es * total_value, 2),
                    }
                )
    return rows, simulated


def _asset_stats(symbols: list[str], values: np.ndarray, weights: np.ndarray, confidence: float) -> list[dict]:
    rows = []
    for i, symbol in enumerate(symbols):
        series = values[:, i]
        rows.append(
            {
                "symbol": symbol,
                "weight": float(weights[i]),
                "annualized_return": annualized_return(series),
                "annualized_volatility": annualized_volatility(series.tolist()),
                "var_1d": historical_var(series, confidence),
                "max_drawdown": max_drawdown(series.tolist()),
            }
        )
    return rows


def _report(
    symbols: list[str],
    dates: list,
    values: np.ndarray,
    weights: np.ndarray,
    total_value: float,
    confidence: float,
    horizon: int,
    n_simulations: int,
    seed: int | None,
    risk_free_rate: float,
    backtest_window: int,
    warnings: list[str],
) -> dict:
    returns = values @ weights
    if returns.size < MIN_OBSERVATIONS:
        raise InsufficientDataError(
            f"Seulement {returns.size} jours communs d'historique (minimum : {MIN_OBSERVATIONS})"
        )
    table, simulated = var_es_table(values, weights, total_value, n_simulations, seed)
    covariance = np.atleast_2d(np.cov(values, rowvar=False, ddof=1))
    decomposition = risk_contributions(weights, covariance)
    annual = math.sqrt(TRADING_DAYS_PER_YEAR)

    backtest = None
    if returns.size > backtest_window:
        result = rolling_var_backtest(returns, confidence, backtest_window)
        tested_dates = dates[backtest_window:]
        backtest = {
            key: result[key]
            for key in ("observations", "exceptions", "expected_exceptions", "exception_rate",
                        "lr_statistic", "p_value", "rejected", "window")
        }
        backtest["series"] = [
            {"date": day, "loss": loss, "var": var, "hit": hit}
            for day, loss, var, hit in zip(tested_dates, result["losses"], result["var_forecasts"], result["hits"])
        ]
    else:
        warnings.append(
            f"Backtesting impossible : {returns.size} rendements pour une fenêtre de {backtest_window} jours."
        )

    selected = simulated[horizon]
    return {
        "observations": int(returns.size),
        "period_start": dates[0],
        "period_end": dates[-1],
        "total_value": round(total_value, 2),
        "confidence": confidence,
        "horizon_days": horizon,
        "n_simulations": n_simulations,
        "seed": seed,
        "var_table": table,
        "metrics": {
            "annualized_return": annualized_return(returns),
            "annualized_volatility": annualized_volatility(returns.tolist()),
            "max_drawdown": max_drawdown(returns.tolist()),
            "sharpe_ratio": sharpe_ratio(returns, risk_free_rate),
            "sortino_ratio": sortino_ratio(returns, risk_free_rate),
        },
        "monte_carlo_distribution": histogram(selected, 50),
        "assets": _asset_stats(symbols, values, weights, confidence),
        "correlation": {"symbols": symbols, "matrix": correlation(values)},
        "risk_contributions": sorted(
            (
                {
                    "symbol": symbols[i],
                    "weight": float(weights[i]),
                    "marginal_contribution": float(decomposition["marginal"][i] * annual),
                    "component_contribution": float(decomposition["component"][i] * annual),
                    "risk_share": float(decomposition["share"][i]),
                }
                for i in range(len(symbols))
            ),
            key=lambda row: -row["risk_share"],
        ),
        "backtest": backtest,
        "warnings": warnings,
    }


def portfolio_risk_report(
    db: Session,
    portfolio: Portfolio,
    lookback: int | None,
    confidence: float,
    horizon: int,
    n_simulations: int,
    seed: int | None,
    risk_free_rate: float,
    backtest_window: int,
) -> dict:
    data = portfolio_returns(db, portfolio, lookback)
    if not data.matrix.asset_ids:
        raise InsufficientDataError("Aucune position avec historique de cours : rien à mesurer")
    symbols = [data.symbols[a] for a in data.matrix.asset_ids]
    report = _report(
        symbols, data.matrix.dates, data.matrix.values, data.weights, data.snapshot.total_value,
        confidence, horizon, n_simulations, seed, risk_free_rate, backtest_window, data.warnings,
    )
    return {"portfolio_id": portfolio.id, "data_source": "real_market_data", **report}


def basket_risk(
    db: Session,
    symbols: list[str],
    weights: list[float] | None,
    notional: float,
    lookback: int | None,
    confidence: float,
    horizon: int,
    n_simulations: int,
    seed: int | None,
    risk_free_rate: float,
    backtest_window: int,
) -> dict:
    """Panier libre : poids saisis (normalisés à 100 %) ou égaux par défaut."""
    wanted = [s.strip().upper() for s in symbols]
    if len(set(wanted)) != len(wanted):
        raise ValueError("Chaque actif ne doit apparaître qu'une fois")
    assets = {a.symbol: a for a in db.scalars(select(Asset).where(Asset.symbol.in_(wanted)))}
    unknown = [s for s in wanted if s not in assets]
    if unknown:
        raise ValueError(f"Actif(s) inconnu(s) : {', '.join(unknown)}")
    raw = np.full(len(wanted), 1.0) if weights is None else np.asarray(weights, dtype=float)
    if raw.size != len(wanted):
        raise ValueError("Autant de poids que d'actifs sont nécessaires")
    if raw.sum() <= 0:
        raise ValueError("La somme des poids doit être strictement positive")
    raw = raw / raw.sum()

    ids = [assets[s].id for s in wanted]
    matrix = returns_matrix(db, ids, lookback)
    warnings = []
    if matrix.excluded:
        names = ", ".join(s for s in wanted if assets[s].id in matrix.excluded)
        raise InsufficientDataError(f"Historique insuffisant pour {names}")
    by_id = dict(zip(ids, raw))
    kept_weights = np.array([by_id[a] for a in matrix.asset_ids])
    kept_symbols = [next(s for s in wanted if assets[s].id == a) for a in matrix.asset_ids]
    report = _report(
        kept_symbols, matrix.dates, matrix.values, kept_weights, notional,
        confidence, horizon, n_simulations, seed, risk_free_rate, backtest_window, warnings,
    )
    return {"portfolio_id": None, "data_source": "real_market_data", **report}
