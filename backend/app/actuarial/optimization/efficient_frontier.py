"""Frontière efficiente : portefeuilles de variance minimale pour une grille de rendements cibles.

La grille va du rendement du portefeuille de variance minimale au rendement
maximal atteignable sous les mêmes contraintes (programme linéaire). Les points
non résolus sont omis plutôt qu'approximés.
"""

import numpy as np
from scipy.optimize import linprog

from app.actuarial.optimization.markowitz import OptimizationError, bounds, min_variance, stats, target_return


def max_attainable_return(mu: np.ndarray, max_weight: float, allow_short: bool) -> float:
    n = mu.size
    result = linprog(-mu, A_eq=np.ones((1, n)), b_eq=[1.0], bounds=bounds(n, max_weight, allow_short), method="highs")
    if not result.success:
        raise OptimizationError("Rendement maximal introuvable sous ces contraintes")
    return float(-result.fun)


def efficient_frontier(mu: np.ndarray, cov: np.ndarray, risk_free_rate: float = 0.0, points: int = 25,
                       max_weight: float = 1.0, allow_short: bool = False) -> list[dict]:
    low = float(min_variance(cov, max_weight, allow_short) @ mu)
    high = max_attainable_return(mu, max_weight, allow_short)
    frontier = []
    for target in np.linspace(low, high, max(points, 2)):
        try:
            weights = target_return(mu, cov, float(target), max_weight, allow_short)
        except OptimizationError:
            continue
        frontier.append({**stats(weights, mu, cov, risk_free_rate), "weights": weights.tolist()})
    return frontier
