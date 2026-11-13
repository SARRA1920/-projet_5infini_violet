"""Résumés statistiques communs aux simulations (distributions, quantiles, histogrammes)."""

import math

import numpy as np

QUANTILE_LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)


def describe(values: np.ndarray) -> dict:
    """Moyenne, écart-type, extrêmes, quantiles et erreur standard Monte Carlo de la moyenne.

    Intervalle de confiance à 95 % de la moyenne : moyenne ± 1,96 x écart-type / sqrt(n)
    (théorème central limite). Les quantiles 5 % et 95 % bornent l'intervalle à 90 %
    des valeurs simulées.
    """
    values = np.asarray(values, dtype=float)
    n = values.size
    std = float(values.std(ddof=1)) if n > 1 else 0.0
    mean = float(values.mean())
    standard_error = std / math.sqrt(n) if n else 0.0
    return {
        "count": n,
        "mean": mean,
        "std": std,
        "min": float(values.min()),
        "max": float(values.max()),
        "quantiles": {f"p{round(q * 100):02d}": float(np.quantile(values, q)) for q in QUANTILE_LEVELS},
        "mean_standard_error": standard_error,
        "mean_ci95": [mean - 1.96 * standard_error, mean + 1.96 * standard_error],
    }


def histogram(values: np.ndarray, bins: int = 40) -> list[dict]:
    """Histogramme en classes de même largeur : [{from, to, count}]."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return []
    counts, edges = np.histogram(values, bins=bins)
    return [
        {"from": float(edges[i]), "to": float(edges[i + 1]), "count": int(counts[i])}
        for i in range(len(counts))
    ]


def fan(paths: np.ndarray, times: np.ndarray, max_points: int = 120) -> list[dict]:
    """Quantiles des trajectoires à chaque date (sous-échantillonnées à `max_points` dates)."""
    index = np.unique(np.linspace(0, len(times) - 1, min(max_points, len(times))).round().astype(int))
    quantiles = np.quantile(paths[:, index], QUANTILE_LEVELS, axis=0)
    mean = paths[:, index].mean(axis=0)
    return [
        {
            "t": float(times[i]),
            "mean": float(mean[k]),
            **{f"p{round(q * 100):02d}": float(quantiles[j, k]) for j, q in enumerate(QUANTILE_LEVELS)},
        }
        for k, i in enumerate(index)
    ]


def sample_paths(paths: np.ndarray, times: np.ndarray, count: int = 12, max_points: int = 120) -> list[list[float]]:
    """Quelques trajectoires individuelles, aux mêmes dates que `fan`."""
    index = np.unique(np.linspace(0, len(times) - 1, min(max_points, len(times))).round().astype(int))
    return [[float(v) for v in paths[p, index]] for p in range(min(count, paths.shape[0]))]
