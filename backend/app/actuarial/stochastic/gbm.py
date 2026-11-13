"""Mouvement brownien géométrique (GBM) pour le prix d'un actif.

Modèle : dS = μ S dt + σ S dW.
Solution exacte : S(t+Δ) = S(t) exp((μ - σ²/2) Δ + σ sqrt(Δ) Z), Z ~ N(0, 1).

Hypothèses : rendements log indépendants et normaux, μ et σ constants, pas de
dividende ni de saut. Le modèle ne prédit pas le prix : il décrit une
distribution de valeurs futures compatible avec la volatilité historique.

Calibration (maximum de vraisemblance sur les rendements log x_i, pas Δ) :
    σ² = Var(x) / Δ        μ = moyenne(x) / Δ + σ² / 2
Erreurs standards : se(μ) ≈ σ / sqrt(T), se(σ) ≈ σ / sqrt(2(n - 1)), T = n Δ.
La dérive μ est très imprécise sur un an d'historique : se(μ) ≈ σ.
"""

import math

import numpy as np
from scipy.stats import norm

from app.actuarial.stochastic import check_size, time_grid

DAILY_DT = 1 / 252


def calibrate(prices: np.ndarray, dt: float = DAILY_DT) -> dict:
    prices = np.asarray(prices, dtype=float)
    if prices.size < 3:
        raise ValueError("Au moins trois cours sont nécessaires pour calibrer le GBM")
    if np.any(prices <= 0):
        raise ValueError("Les cours doivent être strictement positifs")
    x = np.diff(np.log(prices))
    sigma = float(x.std(ddof=1) / math.sqrt(dt))
    mu = float(x.mean() / dt + sigma**2 / 2)
    years = x.size * dt
    return {
        "mu": mu,
        "sigma": sigma,
        "s0": float(prices[-1]),
        "observations": int(x.size),
        "standard_errors": {"mu": sigma / math.sqrt(years), "sigma": sigma / math.sqrt(2 * (x.size - 1))},
    }


def simulate(
    s0: float, mu: float, sigma: float, horizon: float, steps: int, n_simulations: int, seed: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Trajectoires (n_simulations x steps+1) et grille de temps."""
    if s0 <= 0:
        raise ValueError("Le prix initial doit être strictement positif")
    if sigma < 0:
        raise ValueError("La volatilité doit être positive")
    check_size(n_simulations, steps)
    times = time_grid(horizon, steps)
    dt = horizon / steps
    rng = np.random.default_rng(seed)
    increments = (mu - sigma**2 / 2) * dt + sigma * math.sqrt(dt) * rng.standard_normal((n_simulations, steps))
    log_paths = np.concatenate([np.zeros((n_simulations, 1)), np.cumsum(increments, axis=1)], axis=1)
    return s0 * np.exp(log_paths), times


def expected_value(s0: float, mu: float, t: float) -> float:
    """E[S(t)] = S0 exp(μ t)."""
    return s0 * math.exp(mu * t)


def probability_below(s0: float, mu: float, sigma: float, t: float, level: float) -> float:
    """P(S(t) < level), loi lognormale exacte."""
    if sigma == 0:
        return float(s0 * math.exp(mu * t) < level)
    z = (math.log(level / s0) - (mu - sigma**2 / 2) * t) / (sigma * math.sqrt(t))
    return float(norm.cdf(z))
