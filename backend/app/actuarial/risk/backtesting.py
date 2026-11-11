"""Backtesting de la VaR historique à 1 jour (test de couverture de Kupiec).

Procédure : pour chaque jour t après une fenêtre glissante de W jours, on calcule
la VaR historique sur les W rendements précédents et on compte une exception si
la perte du jour dépasse cette VaR.

Test de Kupiec (proportion of failures), x exceptions sur n jours, p = 1 - α :
    LR = -2 ln[(1 - p)^(n-x) p^x] + 2 ln[(1 - x/n)^(n-x) (x/n)^x]  ~ χ²(1)
Le modèle est rejeté au seuil de 5 % si la p-valeur est < 0,05 (trop ou trop
peu d'exceptions par rapport aux n x p attendues).
"""

import math

import numpy as np
from scipy.stats import chi2

from app.actuarial.risk.var import historical_var

SIGNIFICANCE = 0.05


def _xlogy(x: float, y: float) -> float:
    return 0.0 if x == 0 else x * math.log(y)


def kupiec_test(observations: int, exceptions: int, confidence: float) -> dict:
    if observations <= 0:
        raise ValueError("Aucune observation à tester")
    p = 1 - confidence
    rate = exceptions / observations
    log_null = _xlogy(observations - exceptions, 1 - p) + _xlogy(exceptions, p)
    log_alt = _xlogy(observations - exceptions, 1 - rate) + _xlogy(exceptions, rate)
    statistic = max(0.0, -2 * (log_null - log_alt))
    p_value = float(1 - chi2.cdf(statistic, df=1))
    return {
        "observations": observations,
        "exceptions": exceptions,
        "expected_exceptions": observations * p,
        "exception_rate": rate,
        "lr_statistic": statistic,
        "p_value": p_value,
        "rejected": p_value < SIGNIFICANCE,
    }


def rolling_var_backtest(returns: np.ndarray, confidence: float = 0.95, window: int = 100) -> dict:
    returns = np.asarray(returns, dtype=float)
    if window < 30:
        raise ValueError("Fenêtre d'estimation trop courte (minimum 30 jours)")
    if returns.size <= window:
        raise ValueError(f"Il faut plus de {window} rendements pour ce backtest")
    forecasts = np.array([historical_var(returns[t - window:t], confidence) for t in range(window, returns.size)])
    losses = -returns[window:]
    hits = losses > forecasts
    return {
        **kupiec_test(int(hits.size), int(hits.sum()), confidence),
        "window": window,
        "var_forecasts": forecasts.tolist(),
        "losses": losses.tolist(),
        "hits": hits.tolist(),
    }
