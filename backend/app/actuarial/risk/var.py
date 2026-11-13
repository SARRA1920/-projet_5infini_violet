"""Value at Risk : historique, paramétrique (loi normale) et Monte Carlo.

Conventions de calcul
---------------------
- Rendement simple quotidien : r_t = P_t / P_(t-1) - 1.
- Perte : L = -r (positive quand on perd).
- VaR au niveau de confiance α : quantile d'ordre α de la distribution des pertes,
  méthode « inverted_cdf » : plus petite perte l telle que P(L <= l) >= α.
  Aucune interpolation entre deux observations.
- Horizon h jours :
    * historique : règle de la racine du temps, VaR_h = VaR_1 x sqrt(h)
      (hypothèse : rendements indépendants et identiquement distribués) ;
    * paramétrique : moyenne μh et écart-type σ sqrt(h) ;
    * Monte Carlo : rendements log simulés sur h jours, puis composés.
- Résultat en fraction de la valeur exposée (0.023 = 2,3 %). Une VaR négative
  signifie que même le quantile défavorable correspond à un gain.

Ces conventions diffèrent de la VaR affichée par /trading/risk (services/risk.py,
lecture par indice et VaR bornée à 0) : les deux chiffres peuvent donc s'écarter
légèrement sur un petit échantillon.
"""

import math

import numpy as np
from scipy.stats import norm

CONFIDENCE_LEVELS = (0.95, 0.99)
HORIZONS = (1, 10, 20)
MIN_OBSERVATIONS = 30  # en dessous, les quantiles empiriques ne sont pas significatifs


def _check_confidence(confidence: float) -> None:
    if not 0 < confidence < 1:
        raise ValueError("Le niveau de confiance doit être strictement entre 0 et 1")


def _check_horizon(horizon: int) -> None:
    if horizon < 1:
        raise ValueError("L'horizon doit être d'au moins 1 jour")


def loss_quantile(losses: np.ndarray, confidence: float) -> float:
    """Quantile d'ordre `confidence` des pertes (méthode inverted_cdf, sans interpolation)."""
    _check_confidence(confidence)
    losses = np.asarray(losses, dtype=float)
    if losses.size == 0:
        raise ValueError("Aucune observation")
    return float(np.quantile(losses, confidence, method="inverted_cdf"))


def historical_var(returns: np.ndarray, confidence: float = 0.95, horizon: int = 1) -> float:
    """VaR historique : quantile empirique des pertes quotidiennes, x sqrt(horizon)."""
    _check_horizon(horizon)
    returns = np.asarray(returns, dtype=float)
    return loss_quantile(-returns, confidence) * math.sqrt(horizon)


def parametric_var(returns: np.ndarray, confidence: float = 0.95, horizon: int = 1) -> float:
    """VaR paramétrique (variance-covariance) sous hypothèse de normalité.

    VaR = -μh + z_α σ sqrt(h), avec μ et σ la moyenne et l'écart-type
    (estimateur sans biais, ddof=1) des rendements quotidiens, z_α le quantile
    de la loi normale centrée réduite.
    """
    _check_confidence(confidence)
    _check_horizon(horizon)
    returns = np.asarray(returns, dtype=float)
    if returns.size < 2:
        raise ValueError("Au moins deux rendements sont nécessaires")
    mu = returns.mean()
    sigma = returns.std(ddof=1)
    return float(-mu * horizon + norm.ppf(confidence) * sigma * math.sqrt(horizon))


def simulate_portfolio_returns(
    asset_returns: np.ndarray,
    weights: np.ndarray,
    horizon: int = 1,
    n_simulations: int = 10_000,
    seed: int | None = None,
) -> np.ndarray:
    """Rendements du portefeuille simulés sur `horizon` jours (Monte Carlo).

    Hypothèses : les rendements log quotidiens des actifs suivent une loi normale
    multivariée N(μ, Σ), indépendante d'un jour à l'autre. Sur h jours, le
    rendement log de chaque actif suit donc N(μh, Σh). Le rendement simple de
    l'actif est exp(x) - 1, celui du portefeuille la somme pondérée (poids
    constants sur l'horizon, cash à rendement nul).

    `asset_returns` : matrice T x N de rendements simples quotidiens.
    `weights` : N poids (fractions de la valeur totale, cash exclu).
    """
    _check_horizon(horizon)
    asset_returns = np.atleast_2d(np.asarray(asset_returns, dtype=float))
    weights = np.asarray(weights, dtype=float)
    if asset_returns.shape[0] < 2:
        raise ValueError("Au moins deux observations sont nécessaires")
    if asset_returns.shape[1] != weights.size:
        raise ValueError("Autant de poids que d'actifs sont nécessaires")
    if n_simulations < 1:
        raise ValueError("Au moins une simulation est nécessaire")
    if np.any(asset_returns <= -1):
        raise ValueError("Rendement inférieur ou égal à -100 % : rendement log indéfini")

    log_returns = np.log1p(asset_returns)
    mean = log_returns.mean(axis=0) * horizon
    cov = np.atleast_2d(np.cov(log_returns, rowvar=False, ddof=1)) * horizon
    rng = np.random.default_rng(seed)
    draws = rng.multivariate_normal(mean, cov, size=n_simulations, method="eigh")
    return np.expm1(draws) @ weights


def monte_carlo_var(simulated_returns: np.ndarray, confidence: float = 0.95) -> float:
    """VaR lue directement sur des rendements simulés à l'horizon voulu."""
    return loss_quantile(-np.asarray(simulated_returns, dtype=float), confidence)
