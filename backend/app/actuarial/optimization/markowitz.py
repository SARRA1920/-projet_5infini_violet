"""Optimisation moyenne-variance de Markowitz.

Entrées annualisées : μ = moyenne des rendements quotidiens x 252,
Σ = covariance quotidienne x 252 (rendements arithmétiques).
Problèmes résolus (SLSQP, scipy) :
- variance minimale       : min wᵀΣw ;
- Sharpe maximal          : max (wᵀμ - rf) / sqrt(wᵀΣw) ;
- rendement cible         : min wᵀΣw sous wᵀμ = cible.
Contraintes : Σ w_i = 1 ; bornes [0, w_max] (positions longues, par défaut) ou
[-w_max, w_max] si la vente à découvert est autorisée (simulation théorique).
Faisabilité : n x w_max >= 1.

Hypothèse forte : μ et Σ historiques sont pris comme estimations du futur. Les
poids optimaux y sont très sensibles (erreur d'estimation) : à interpréter comme
un exercice, pas comme une recommandation.
"""

import math

import numpy as np
from scipy.optimize import minimize

TOLERANCE = 1e-10


class OptimizationError(ValueError):
    """Problème infaisable ou non résolu."""


def annualize(daily_returns: np.ndarray, periods: int = 252) -> tuple[np.ndarray, np.ndarray]:
    daily_returns = np.atleast_2d(np.asarray(daily_returns, dtype=float))
    mu = daily_returns.mean(axis=0) * periods
    cov = np.atleast_2d(np.cov(daily_returns, rowvar=False, ddof=1)) * periods
    return mu, cov


def stats(weights: np.ndarray, mu: np.ndarray, cov: np.ndarray, risk_free_rate: float = 0.0) -> dict:
    expected = float(weights @ mu)
    volatility = math.sqrt(max(float(weights @ cov @ weights), 0.0))
    return {
        "expected_return": expected,
        "volatility": volatility,
        "sharpe_ratio": (expected - risk_free_rate) / volatility if volatility > 1e-12 else None,
    }


def bounds(n: int, max_weight: float, allow_short: bool) -> list[tuple[float, float]]:
    if not 0 < max_weight <= 1:
        raise OptimizationError("La pondération maximale doit être entre 0 et 100 %")
    if n * max_weight < 1 - 1e-9:
        raise OptimizationError(
            f"Infaisable : {n} actifs x {max_weight:.0%} maximum < 100 %. Augmentez la pondération maximale."
        )
    return [(-max_weight if allow_short else 0.0, max_weight)] * n


def _solve(objective, n: int, box, extra_constraints=()) -> np.ndarray:
    constraints = [{"type": "eq", "fun": lambda w: w.sum() - 1}, *extra_constraints]
    start = np.full(n, 1 / n)
    result = minimize(objective, start, method="SLSQP", bounds=box, constraints=constraints,
                      options={"maxiter": 500, "ftol": TOLERANCE})
    if not result.success:
        raise OptimizationError(f"Optimisation non convergée : {result.message}")
    weights = result.x
    weights[np.abs(weights) < 1e-8] = 0.0
    return weights / weights.sum()


def min_variance(cov: np.ndarray, max_weight: float = 1.0, allow_short: bool = False) -> np.ndarray:
    n = cov.shape[0]
    return _solve(lambda w: w @ cov @ w, n, bounds(n, max_weight, allow_short))


def max_sharpe(mu: np.ndarray, cov: np.ndarray, risk_free_rate: float = 0.0,
               max_weight: float = 1.0, allow_short: bool = False) -> np.ndarray:
    n = cov.shape[0]

    def negative_sharpe(w):
        volatility = math.sqrt(max(w @ cov @ w, 1e-18))
        return -(w @ mu - risk_free_rate) / volatility

    return _solve(negative_sharpe, n, bounds(n, max_weight, allow_short))


def target_return(mu: np.ndarray, cov: np.ndarray, target: float,
                  max_weight: float = 1.0, allow_short: bool = False) -> np.ndarray:
    n = cov.shape[0]
    constraint = {"type": "eq", "fun": lambda w: w @ mu - target}
    return _solve(lambda w: w @ cov @ w, n, bounds(n, max_weight, allow_short), [constraint])
