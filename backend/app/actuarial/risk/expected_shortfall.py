"""Expected Shortfall (CVaR) : perte moyenne au-delà de la VaR.

ES_α = E[L | L >= VaR_α]. Mêmes conventions que risk/var.py (pertes positives,
quantile inverted_cdf, racine du temps pour l'historique). Par construction
ES_α >= VaR_α : c'est le contrôle de cohérence vérifié par les tests.
"""

import math

import numpy as np
from scipy.stats import norm

from app.actuarial.risk.var import _check_confidence, _check_horizon, loss_quantile


def tail_mean(losses: np.ndarray, confidence: float) -> float:
    """Moyenne des pertes supérieures ou égales à la VaR (le quantile lui-même inclus)."""
    losses = np.asarray(losses, dtype=float)
    threshold = loss_quantile(losses, confidence)
    return float(losses[losses >= threshold].mean())


def historical_es(returns: np.ndarray, confidence: float = 0.95, horizon: int = 1) -> float:
    """ES historique sur 1 jour, mise à l'échelle par sqrt(horizon)."""
    _check_horizon(horizon)
    return tail_mean(-np.asarray(returns, dtype=float), confidence) * math.sqrt(horizon)


def parametric_es(returns: np.ndarray, confidence: float = 0.95, horizon: int = 1) -> float:
    """ES sous hypothèse normale : -μh + σ sqrt(h) φ(z_α) / (1 - α)."""
    _check_confidence(confidence)
    _check_horizon(horizon)
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        raise ValueError("Au moins deux rendements sont nécessaires")
    mu = returns.mean()
    sigma = returns.std(ddof=1)
    z = norm.ppf(confidence)
    return float(-mu * horizon + sigma * math.sqrt(horizon) * norm.pdf(z) / (1 - confidence))


def monte_carlo_es(simulated_returns: np.ndarray, confidence: float = 0.95) -> float:
    """ES lue sur des rendements simulés à l'horizon voulu."""
    return tail_mean(-np.asarray(simulated_returns, dtype=float), confidence)
