"""Indicateurs de performance et de risque d'une série de rendements.

La volatilité annualisée et le drawdown maximal réutilisent les fonctions du
module Portfolio (services/risk.py) pour que les deux écrans affichent les mêmes
chiffres. Les autres indicateurs suivent les conventions de risk/var.py.
"""

import math

import numpy as np

from app.services.risk import TRADING_DAYS_PER_YEAR, annualized_volatility, max_drawdown

# En dessous, une dispersion est considérée comme nulle (erreurs d'arrondi flottant).
ZERO_DISPERSION = 1e-12

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "annualized_volatility",
    "max_drawdown",
    "cumulative_return",
    "annualized_return",
    "sharpe_ratio",
    "sortino_ratio",
    "risk_contributions",
    "herfindahl_index",
]


def cumulative_return(returns: np.ndarray) -> float:
    """Rendement composé sur la période : prod(1 + r) - 1."""
    returns = np.asarray(returns, dtype=float)
    return float(np.prod(1 + returns) - 1)


def annualized_return(returns: np.ndarray) -> float | None:
    """Rendement annualisé géométrique (CAGR) : (1 + R)^(252 / T) - 1."""
    returns = np.asarray(returns, dtype=float)
    if returns.size == 0:
        return None
    growth = 1 + cumulative_return(returns)
    if growth <= 0:
        return -1.0
    return float(growth ** (TRADING_DAYS_PER_YEAR / returns.size) - 1)


def sharpe_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float | None:
    """Ratio de Sharpe annualisé : (moyenne(r - rf_j) / écart-type(r)) x sqrt(252).

    rf_j = taux sans risque annuel / 252 (hypothèse saisie par l'utilisateur :
    aucune courbe de taux n'est stockée dans l'application). None si la
    volatilité est nulle ou s'il y a moins de deux rendements.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        return None
    sigma = returns.std(ddof=1)
    if sigma < ZERO_DISPERSION:
        return None
    excess = returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    return float(excess.mean() / sigma * math.sqrt(TRADING_DAYS_PER_YEAR))


def sortino_ratio(returns: np.ndarray, risk_free_rate: float = 0.0) -> float | None:
    """Ratio de Sortino annualisé : moyenne(r - rf_j) / écart baissier x sqrt(252).

    Écart baissier = sqrt(moyenne(min(r - rf_j, 0)^2)) sur toutes les observations.
    None s'il n'y a aucun rendement sous le seuil.
    """
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        return None
    excess = returns - risk_free_rate / TRADING_DAYS_PER_YEAR
    downside = math.sqrt(float(np.mean(np.minimum(excess, 0.0) ** 2)))
    if downside < ZERO_DISPERSION:
        return None
    return float(excess.mean() / downside * math.sqrt(TRADING_DAYS_PER_YEAR))


def risk_contributions(weights: np.ndarray, covariance: np.ndarray) -> dict[str, np.ndarray | float]:
    """Décomposition d'Euler de la volatilité du portefeuille.

    σ_p = sqrt(wᵀΣw)
    contribution marginale MRC_i = (Σw)_i / σ_p
    contribution totale    RC_i  = w_i x MRC_i   (somme des RC_i = σ_p)
    part du risque         RC_i / σ_p           (somme = 1)
    Les volatilités sont dans l'unité de Σ (quotidienne si Σ l'est).
    """
    weights = np.asarray(weights, dtype=float)
    covariance = np.atleast_2d(np.asarray(covariance, dtype=float))
    variance = float(weights @ covariance @ weights)
    sigma = math.sqrt(max(variance, 0.0))
    if sigma == 0:
        zeros = np.zeros_like(weights)
        return {"volatility": 0.0, "marginal": zeros, "component": zeros, "share": zeros}
    marginal = covariance @ weights / sigma
    component = weights * marginal
    return {"volatility": sigma, "marginal": marginal, "component": component, "share": component / sigma}


def herfindahl_index(weights: np.ndarray) -> float | None:
    """Indice de concentration de Herfindahl-Hirschman, sur les poids normalisés à 1.

    1/N pour N lignes de même poids, 1 pour une seule ligne.
    """
    weights = np.abs(np.asarray(weights, dtype=float))
    total = weights.sum()
    if total == 0:
        return None
    shares = weights / total
    return float(np.sum(shares**2))
