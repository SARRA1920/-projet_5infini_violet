"""Modèle de Hull-White à un facteur, ajusté à une courbe zéro-coupon initiale.

Modèle : dr = (θ(t) - a r) dt + σ dW. θ(t) est choisi pour que le modèle
reproduise exactement la courbe initiale P(0,T) = exp(-R(T) T).

Décomposition utilisée : r(t) = x(t) + α(t), avec
    dx = -a x dt + σ dW, x(0) = 0 (Ornstein-Uhlenbeck, simulé exactement),
    α(t) = f(0,t) + σ² / (2a²) (1 - e^(-at))²,
f(0,t) = d/dt [R(t) t] le taux forward instantané de la courbe initiale.

La courbe initiale est une donnée d'entrée (hypothèse utilisateur : aucune courbe
de taux n'est stockée dans l'application). Taux zéro-coupon en composition
continue, interpolés linéairement, prolongés à plat avant le premier et après le
dernier point. a et σ peuvent être estimés sur une série historique comme pour
Vasicek (même AR(1)).

Contrôle de cohérence : E[exp(-∫ r dt)] sur les trajectoires simulées doit
retrouver P(0,T) de la courbe initiale (vérifié par les tests).
"""

import math

import numpy as np

from app.actuarial.stochastic import check_size, time_grid

FORWARD_BUMP = 1e-4  # pas de dérivation numérique de R(t) t, en années


class ZeroCurve:
    def __init__(self, maturities: list[float], rates: list[float]):
        maturities = np.asarray(maturities, dtype=float)
        rates = np.asarray(rates, dtype=float)
        if maturities.size == 0 or maturities.size != rates.size:
            raise ValueError("La courbe doit avoir autant de taux que de maturités (au moins un point)")
        if np.any(maturities <= 0) or np.any(np.diff(maturities) <= 0):
            raise ValueError("Les maturités de la courbe doivent être positives et croissantes")
        self.maturities = maturities
        self.rates = rates

    def zero_rate(self, t):
        return np.interp(t, self.maturities, self.rates)

    def discount(self, t: float) -> float:
        return math.exp(-float(self.zero_rate(t)) * t)

    def forward(self, t):
        """f(0,t) = d/dt [R(t) t] par différence centrée (avant en t = 0)."""
        t = np.asarray(t, dtype=float)
        low = np.maximum(t - FORWARD_BUMP, 0.0)
        high = t + FORWARD_BUMP
        return (self.zero_rate(high) * high - self.zero_rate(low) * low) / (high - low)


def alpha(curve: ZeroCurve, a: float, sigma: float, t):
    t = np.asarray(t, dtype=float)
    return curve.forward(t) + sigma**2 / (2 * a**2) * (1 - np.exp(-a * t)) ** 2


def simulate(
    curve: ZeroCurve, a: float, sigma: float, horizon: float, steps: int, n_simulations: int, seed: int | None = None
) -> tuple[np.ndarray, np.ndarray]:
    if a <= 0:
        raise ValueError("La vitesse de retour à la moyenne a doit être strictement positive")
    if sigma < 0:
        raise ValueError("La volatilité σ doit être positive")
    check_size(n_simulations, steps)
    times = time_grid(horizon, steps)
    dt = horizon / steps
    decay = math.exp(-a * dt)
    noise = sigma * math.sqrt((1 - math.exp(-2 * a * dt)) / (2 * a))
    rng = np.random.default_rng(seed)
    shocks = rng.standard_normal((n_simulations, steps))
    x = np.zeros((n_simulations, steps + 1))
    for k in range(steps):
        x[:, k + 1] = x[:, k] * decay + noise * shocks[:, k]
    return x + alpha(curve, a, sigma, times), times


def mean(curve: ZeroCurve, a: float, sigma: float, t: float) -> float:
    return float(alpha(curve, a, sigma, t))


def variance(a: float, sigma: float, t: float) -> float:
    return sigma**2 / (2 * a) * (1 - math.exp(-2 * a * t))
