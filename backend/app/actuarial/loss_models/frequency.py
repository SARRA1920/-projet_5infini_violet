"""Lois de fréquence : Poisson et binomiale négative.

Poisson(λ) : E[N] = Var[N] = λ. Estimateur du maximum de vraisemblance λ = moyenne.
Binomiale négative(r, p) (nombre d'échecs avant r succès) :
    E[N] = r (1 - p) / p, Var[N] = E[N] + E[N]² / r  (surdispersion).
Maximum de vraisemblance : pour r donné, p = r / (r + moyenne) ; r est trouvé en
maximisant la vraisemblance profilée. Exige Var > moyenne (sinon Poisson convient).

Agrégation de k périodes indépendantes : Poisson(kλ) ; binomiale négative (k r, p).
Choc de fréquence (moyenne x m) : Poisson λ m ; binomiale négative r fixé, p
recalculé pour la nouvelle moyenne.
"""

import math

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.stats import nbinom, poisson

MODELS = ("poisson", "negative_binomial")


def _counts(counts) -> np.ndarray:
    counts = np.asarray(counts, dtype=float)
    if counts.size < 2:
        raise ValueError("Au moins deux périodes d'observation sont nécessaires")
    if np.any(counts < 0) or np.any(counts != np.round(counts)):
        raise ValueError("Les nombres de pertes doivent être des entiers positifs")
    return counts


def validate(model: str, params: dict) -> None:
    if model == "poisson":
        if params.get("lam") is None or params["lam"] < 0:
            raise ValueError("Poisson : λ doit être positif")
    elif model == "negative_binomial":
        r, p = params.get("r"), params.get("p")
        if r is None or p is None or r <= 0 or not 0 < p <= 1:
            raise ValueError("Binomiale négative : r > 0 et 0 < p <= 1")
    else:
        raise ValueError(f"Loi de fréquence inconnue : {model}")


def fit_poisson(counts) -> dict:
    counts = _counts(counts)
    lam = float(counts.mean())
    loglik = float(poisson.logpmf(counts, lam).sum()) if lam > 0 else (0.0 if not counts.any() else -math.inf)
    return {
        "model": "poisson",
        "params": {"lam": lam},
        "standard_errors": {"lam": math.sqrt(lam / counts.size)},
        "loglik": loglik,
        "aic": 2 * 1 - 2 * loglik,
        "mean": lam,
        "std": math.sqrt(lam),
    }


def fit_negative_binomial(counts) -> dict:
    counts = _counts(counts)
    mean = counts.mean()
    variance = counts.var(ddof=1)
    if mean == 0 or variance <= mean:
        raise ValueError(
            f"Pas de surdispersion (variance {variance:.3f} <= moyenne {mean:.3f}) : la loi de Poisson suffit"
        )

    def negative_loglik(log_r: float) -> float:
        r = math.exp(log_r)
        return -float(nbinom.logpmf(counts, r, r / (r + mean)).sum())

    result = minimize_scalar(negative_loglik, bounds=(math.log(1e-3), math.log(1e6)), method="bounded")
    r = math.exp(result.x)
    loglik = -float(result.fun)
    params = {"r": r, "p": r / (r + mean)}
    fitted_mean, fitted_variance = moments("negative_binomial", params)
    return {
        "model": "negative_binomial",
        "params": params,
        "standard_errors": None,
        "loglik": loglik,
        "aic": 2 * 2 - 2 * loglik,
        "mean": fitted_mean,
        "std": math.sqrt(fitted_variance),
    }


def moments(model: str, params: dict) -> tuple[float, float]:
    validate(model, params)
    if model == "poisson":
        return params["lam"], params["lam"]
    r, p = params["r"], params["p"]
    mean = r * (1 - p) / p
    return mean, mean + mean**2 / r


def annualize(model: str, params: dict, periods: int) -> dict:
    """Paramètres pour la somme de `periods` périodes indépendantes."""
    validate(model, params)
    if periods < 1:
        raise ValueError("Le nombre de périodes par an doit être au moins 1")
    if model == "poisson":
        return {"lam": params["lam"] * periods}
    return {"r": params["r"] * periods, "p": params["p"]}


def stress(model: str, params: dict, multiplier: float) -> dict:
    """Multiplie la fréquence moyenne par `multiplier`."""
    validate(model, params)
    if multiplier <= 0:
        raise ValueError("Le multiplicateur de fréquence doit être strictement positif")
    if model == "poisson":
        return {"lam": params["lam"] * multiplier}
    mean, _ = moments(model, params)
    r = params["r"]
    new_mean = mean * multiplier
    return {"r": r, "p": r / (r + new_mean)}


def sample(model: str, params: dict, rng: np.random.Generator, size: int) -> np.ndarray:
    validate(model, params)
    if model == "poisson":
        return rng.poisson(params["lam"], size)
    return rng.negative_binomial(params["r"], params["p"], size)


def pmf(model: str, params: dict, k_max: int) -> list[float]:
    k = np.arange(k_max + 1)
    if model == "poisson":
        return poisson.pmf(k, params["lam"]).tolist()
    return nbinom.pmf(k, params["r"], params["p"]).tolist()
