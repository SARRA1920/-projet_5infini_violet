"""Modèle de Cox-Ingersoll-Ross (CIR) pour le taux court.

Modèle : dr = a (b - r) dt + σ sqrt(r) dW.
Condition de Feller 2ab >= σ² : le taux reste alors strictement positif.
Transition exacte : r(t+Δ) = c X, X ~ χ²'(d, λ) (khi-deux non centré) avec
    c = σ² (1 - e^(-aΔ)) / (4a), d = 4ab / σ², λ = r(t) e^(-aΔ) / c.
Moments : E[r(t)] = b + (r0 - b) e^(-at) ;
Var[r(t)] = r0 σ²/a (e^(-at) - e^(-2at)) + b σ²/(2a) (1 - e^(-at))².

Calibration (moindres carrés sur la discrétisation d'Euler, série strictement positive) :
    (r(t+1) - r(t)) / sqrt(r(t)) = β1 / sqrt(r(t)) + β2 sqrt(r(t)) + ε
    a = -β2 / Δ, b = -β1 / β2, σ = sd(ε) / sqrt(Δ).

Prix zéro-coupon : P(0,T) = A exp(-B r0), γ = sqrt(a² + 2σ²),
B = 2(e^(γT) - 1) / D, A = (2γ e^((a+γ)T/2) / D)^(2ab/σ²), D = (γ + a)(e^(γT) - 1) + 2γ.
"""

import math

import numpy as np

from app.actuarial.stochastic import check_size, ols, time_grid


def _check(a: float, b: float, sigma: float) -> None:
    if a <= 0 or b <= 0 or sigma <= 0:
        raise ValueError("Les paramètres a, b et σ du CIR doivent être strictement positifs")


def feller(a: float, b: float, sigma: float) -> bool:
    return 2 * a * b >= sigma**2


def calibrate(rates: np.ndarray, dt: float) -> dict:
    rates = np.asarray(rates, dtype=float)
    if rates.size < 10:
        raise ValueError("Au moins dix observations de taux sont nécessaires")
    if np.any(rates <= 0):
        raise ValueError("Le CIR exige des taux strictement positifs")
    root = np.sqrt(rates[:-1])
    y = np.diff(rates) / root
    (beta1, beta2), residuals = ols(np.column_stack([1 / root, root]), y)
    if beta2 >= 0:
        raise ValueError("Pas de retour à la moyenne dans la série : modèle non calibrable")
    a = -beta2 / dt
    b = -beta1 / beta2
    if b <= 0:
        raise ValueError("Niveau long terme estimé négatif : modèle non calibrable")
    sigma = float(residuals.std(ddof=2) / math.sqrt(dt))
    return {"a": float(a), "b": float(b), "sigma": sigma, "r0": float(rates[-1]), "observations": int(rates.size)}


def simulate(
    r0: float, a: float, b: float, sigma: float, horizon: float, steps: int, n_simulations: int, seed: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    _check(a, b, sigma)
    if r0 < 0:
        raise ValueError("Le taux initial du CIR doit être positif")
    check_size(n_simulations, steps)
    times = time_grid(horizon, steps)
    dt = horizon / steps
    c = sigma**2 * (1 - math.exp(-a * dt)) / (4 * a)
    degrees = 4 * a * b / sigma**2
    rng = np.random.default_rng(seed)
    paths = np.empty((n_simulations, steps + 1))
    paths[:, 0] = r0
    for k in range(steps):
        noncentrality = paths[:, k] * math.exp(-a * dt) / c
        paths[:, k + 1] = c * rng.noncentral_chisquare(degrees, noncentrality)
    return paths, times


def mean(r0: float, a: float, b: float, t: float) -> float:
    return b + (r0 - b) * math.exp(-a * t)


def variance(r0: float, a: float, b: float, sigma: float, t: float) -> float:
    e = math.exp(-a * t)
    return r0 * sigma**2 / a * (e - e**2) + b * sigma**2 / (2 * a) * (1 - e) ** 2


def zero_coupon_price(r0: float, a: float, b: float, sigma: float, maturity: float) -> float:
    _check(a, b, sigma)
    gamma = math.sqrt(a**2 + 2 * sigma**2)
    growth = math.exp(gamma * maturity) - 1
    denominator = (gamma + a) * growth + 2 * gamma
    big_b = 2 * growth / denominator
    big_a = (2 * gamma * math.exp((a + gamma) * maturity / 2) / denominator) ** (2 * a * b / sigma**2)
    return big_a * math.exp(-big_b * r0)
