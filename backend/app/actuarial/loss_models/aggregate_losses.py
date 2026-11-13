"""Simulation de la perte agrégée annuelle S = X_1 + ... + X_N (Monte Carlo).

Pour chaque année simulée : N tiré dans la loi de fréquence annuelle, puis N
montants tirés dans la loi de sévérité. Option de couverture par sinistre
(franchise d et plafond L) : perte retenue = min(max(X - d, 0), L).

Contrôle de cohérence : moyenne et variance simulées comparées aux formules du
modèle collectif (sans franchise ni plafond).
"""

import numpy as np

from app.actuarial.loss_models import frequency, severity

MAX_YEARS = 200_000
MAX_LOSSES = 10_000_000  # nombre total de pertes tirées : borne mémoire et temps


def compound_moments(freq_model: str, freq_params: dict, sev_model: str, sev_params: dict) -> dict:
    n_mean, n_var = frequency.moments(freq_model, freq_params)
    x_mean, x_var = severity.moments(sev_model, sev_params)
    mean = None if x_mean is None else n_mean * x_mean
    variance = None if x_mean is None or x_var is None else n_mean * x_var + n_var * x_mean**2
    return {"mean": mean, "variance": variance, "frequency_mean": n_mean, "severity_mean": x_mean}


def simulate(
    freq_model: str,
    freq_params: dict,
    sev_model: str,
    sev_params: dict,
    n_years: int,
    seed: int | None = None,
    deductible: float = 0.0,
    limit: float | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Renvoie (pertes agrégées par année, nombre de pertes par année)."""
    if not 1 <= n_years <= MAX_YEARS:
        raise ValueError(f"Le nombre d'années simulées doit être entre 1 et {MAX_YEARS}")
    if deductible < 0 or (limit is not None and limit <= 0):
        raise ValueError("Franchise positive et plafond strictement positif requis")
    expected_losses = frequency.moments(freq_model, freq_params)[0] * n_years
    if expected_losses > MAX_LOSSES:
        raise ValueError(
            f"Environ {expected_losses:,.0f} pertes à tirer (maximum {MAX_LOSSES:,}) : "
            "réduisez le nombre d'années simulées".replace(",", " ")
        )
    rng = np.random.default_rng(seed)
    counts = frequency.sample(freq_model, freq_params, rng, n_years)
    amounts = severity.sample(sev_model, sev_params, rng, int(counts.sum()))
    retained = np.maximum(amounts - deductible, 0.0)
    if limit is not None:
        retained = np.minimum(retained, limit)
    years = np.repeat(np.arange(n_years), counts)
    return np.bincount(years, weights=retained, minlength=n_years), counts
