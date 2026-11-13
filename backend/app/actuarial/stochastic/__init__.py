"""Modèles stochastiques : GBM (prix), Vasicek, CIR et Hull-White (taux courts).

Conventions communes :
- temps en années ; pas de temps dt = horizon / steps ;
- paramètres annualisés ;
- simulations exactes (lois de transition connues) plutôt qu'Euler, donc sans
  biais de discrétisation ;
- graine `seed` pour la reproductibilité (numpy.random.default_rng).
"""

import numpy as np

MAX_SIMULATIONS = 20_000
MAX_STEPS = 2_520
MAX_CELLS = MAX_SIMULATIONS * 252  # simulations x pas (1 an au pas quotidien) : borne mémoire et temps


def time_grid(horizon: float, steps: int) -> np.ndarray:
    if horizon <= 0:
        raise ValueError("L'horizon doit être strictement positif")
    if not 1 <= steps <= MAX_STEPS:
        raise ValueError(f"Le nombre de pas doit être entre 1 et {MAX_STEPS}")
    return np.linspace(0.0, horizon, steps + 1)


def check_size(n_simulations: int, steps: int) -> None:
    if not 1 <= n_simulations <= MAX_SIMULATIONS:
        raise ValueError(f"Le nombre de simulations doit être entre 1 et {MAX_SIMULATIONS}")
    if n_simulations * steps > MAX_CELLS:
        raise ValueError(f"Simulations x pas limité à {MAX_CELLS:,} : réduisez l'un des deux".replace(",", " "))


def ols(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Moindres carrés ordinaires y = X β + ε ; renvoie (β, résidus)."""
    beta, *_ = np.linalg.lstsq(x, y, rcond=None)
    return beta, y - x @ beta
