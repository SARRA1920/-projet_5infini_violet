"""Modèle de Vasicek pour le taux court.

Modèle : dr = a (b - r) dt + σ dW   (a > 0 vitesse de retour, b niveau long terme).
Transition exacte sur un pas Δ :
    r(t+Δ) = r(t) e^(-aΔ) + b (1 - e^(-aΔ)) + σ sqrt((1 - e^(-2aΔ)) / (2a)) Z
Moments : E[r(t)] = b + (r0 - b) e^(-at) ; Var[r(t)] = σ²/(2a) (1 - e^(-2at)).
Hypothèse : taux gaussien, il peut donc devenir négatif (probabilité calculée).

Calibration : la transition exacte est un AR(1), r(t+1) = c + φ r(t) + ε, estimé
par moindres carrés : a = -ln(φ)/Δ, b = c / (1 - φ), σ = sd(ε) sqrt(2a / (1 - φ²)).
Exige 0 < φ < 1 (retour à la moyenne détecté dans la série).

Prix zéro-coupon : P(0,T) = A exp(-B r0), B = (1 - e^(-aT))/a,
A = exp((b - σ²/(2a²)) (B - T) - σ² B² / (4a)).
"""

import math

import numpy as np

from app.actuarial.stochastic import check_size, ols, time_grid


def _check(a: float, sigma: float) -> None:
    if a <= 0:
        raise ValueError("La vitesse de retour à la moyenne a doit être strictement positive")
    if sigma < 0:
        raise ValueError("La volatilité σ doit être positive")


def calibrate(rates: np.ndarray, dt: float) -> dict:
    rates = np.asarray(rates, dtype=float)
    if rates.size < 10:
        raise ValueError("Au moins dix observations de taux sont nécessaires")
    x = np.column_stack([np.ones(rates.size - 1), rates[:-1]])
    (c, phi), residuals = ols(x, rates[1:])
    if not 0 < phi < 1:
        raise ValueError(f"Pas de retour à la moyenne dans la série (φ = {phi:.4f}) : modèle non calibrable")
    a = -math.log(phi) / dt
    b = c / (1 - phi)
    sigma = float(residuals.std(ddof=2) * math.sqrt(2 * a / (1 - phi**2)))
    return {"a": a, "b": b, "sigma": sigma, "r0": float(rates[-1]), "phi": float(phi), "observations": int(rates.size)}


def simulate(
    r0: float, a: float, b: float, sigma: float, horizon: float, steps: int, n_simulations: int, seed: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    _check(a, sigma)
    check_size(n_simulations, steps)
    times = time_grid(horizon, steps)
    dt = horizon / steps
    decay = math.exp(-a * dt)
    noise = sigma * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((n_simulations, steps))
    paths = np.empty((n_simulations, steps + 1))
    paths[:, 0] = r0
    for k in range(steps):
        paths[:, k + 1] = paths[:, k] * decay + b * (1 - decay) + noise * shocks[:, k]
    return paths, times


def mean(r0: float, a: float, b: float, t: float) -> float:
    return b + (r0 - b) * math.exp(-a * t)


def variance(a: float, sigma: float, t: float) -> float:
    return sigma**2 / (2 * a) * (1 - math.exp(-2 * a * t))


def zero_coupon_price(r0: float, a: float, b: float, sigma: float, maturity: float) -> float:
    _check(a, sigma)
    big_b = (1 - math.exp(-a * maturity)) / a
    log_a = (b - sigma**2 / (2 * a**2)) * (big_b - maturity) - sigma**2 * big_b**2 / (4 * a)
    return math.exp(log_a - big_b * r0)
