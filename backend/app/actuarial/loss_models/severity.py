"""Lois de sévérité : Gamma, lognormale et Pareto (type I).

Gamma(k, θ)      : E[X] = kθ, Var[X] = kθ² ; maximum de vraisemblance numérique (scipy).
Lognormale(μ, σ) : ln X ~ N(μ, σ²) ; E[X] = exp(μ + σ²/2) ; estimateurs fermés sur ln X.
Pareto(α, x_m)   : P(X > x) = (x_m / x)^α pour x >= x_m ; queue épaisse.
                   E[X] = α x_m / (α - 1) si α > 1 (infinie sinon) ; variance infinie si α <= 2.
                   x_m = seuil connu (pertes au-delà d'un seuil) ou, à défaut, le plus petit montant ;
                   α = n / Σ ln(x_i / x_m).

Qualité d'ajustement : log-vraisemblance, AIC = 2k - 2 ln L (plus petit = meilleur),
statistique de Kolmogorov-Smirnov. La p-valeur KS est optimiste car les paramètres
sont estimés sur les mêmes données : indicative seulement.

Chocs (stress testing des hypothèses) :
- sévérité x s : le paramètre d'échelle est multiplié (θ x s, μ + ln s, x_m x s) ;
- queue x t    : la dispersion augmente (k / t² soit un coefficient de variation x t,
                 σ x t, α / t).
"""

import math

import numpy as np
from scipy.stats import gamma, kstest, lognorm, pareto

MODELS = ("gamma", "lognormal", "pareto")
PARAM_COUNT = {"gamma": 2, "lognormal": 2, "pareto": 2}


def _amounts(amounts) -> np.ndarray:
    amounts = np.asarray(amounts, dtype=float)
    if amounts.size < 5:
        raise ValueError("Au moins cinq montants de pertes sont nécessaires pour ajuster une sévérité")
    if np.any(amounts <= 0):
        raise ValueError("Les montants de pertes doivent être strictement positifs")
    return amounts


def validate(model: str, params: dict) -> None:
    required = {"gamma": ("shape", "scale"), "lognormal": ("mu", "sigma"), "pareto": ("alpha", "xm")}
    if model not in required:
        raise ValueError(f"Loi de sévérité inconnue : {model}")
    missing = [k for k in required[model] if params.get(k) is None]
    if missing:
        raise ValueError(f"Paramètres manquants pour {model} : {', '.join(missing)}")
    positive = {"gamma": ("shape", "scale"), "lognormal": ("sigma",), "pareto": ("alpha", "xm")}[model]
    if any(params[k] <= 0 for k in positive):
        raise ValueError(f"Paramètres de {model} : {', '.join(positive)} doivent être strictement positifs")


def _distribution(model: str, params: dict):
    validate(model, params)
    if model == "gamma":
        return gamma(params["shape"], scale=params["scale"])
    if model == "lognormal":
        return lognorm(params["sigma"], scale=math.exp(params["mu"]))
    return pareto(params["alpha"], scale=params["xm"])


def _quality(model: str, params: dict, amounts: np.ndarray) -> dict:
    dist = _distribution(model, params)
    loglik = float(dist.logpdf(amounts).sum())
    ks = kstest(amounts, dist.cdf)
    return {
        "loglik": loglik,
        "aic": 2 * PARAM_COUNT[model] - 2 * loglik,
        "ks_statistic": float(ks.statistic),
        "ks_p_value": float(ks.pvalue),
    }


def fit(model: str, amounts, threshold: float | None = None) -> dict:
    amounts = _amounts(amounts)
    if model == "gamma":
        shape, _, scale = gamma.fit(amounts, floc=0)
        params = {"shape": float(shape), "scale": float(scale)}
    elif model == "lognormal":
        logs = np.log(amounts)
        params = {"mu": float(logs.mean()), "sigma": float(logs.std(ddof=0))}
    elif model == "pareto":
        xm = float(amounts.min()) if threshold is None else float(threshold)
        if xm <= 0 or xm > amounts.min():
            raise ValueError("Le seuil de Pareto doit être positif et inférieur au plus petit montant")
        total = float(np.log(amounts / xm).sum())
        if total <= 0:
            raise ValueError("Montants tous égaux au seuil : Pareto non ajustable")
        params = {"alpha": amounts.size / total, "xm": xm}
    else:
        raise ValueError(f"Loi de sévérité inconnue : {model}")
    return {"model": model, "params": params, **_quality(model, params, amounts), **describe(model, params)}


def describe(model: str, params: dict) -> dict:
    """Moyenne et écart-type théoriques (None si infinis) et quantiles de queue."""
    mean, variance = moments(model, params)
    dist = _distribution(model, params)
    return {
        "mean": mean,
        "std": None if variance is None else math.sqrt(variance),
        "quantile_95": float(dist.ppf(0.95)),
        "quantile_99": float(dist.ppf(0.99)),
        "quantile_995": float(dist.ppf(0.995)),
    }


def moments(model: str, params: dict) -> tuple[float | None, float | None]:
    validate(model, params)
    if model == "gamma":
        k, theta = params["shape"], params["scale"]
        return k * theta, k * theta**2
    if model == "lognormal":
        mu, s = params["mu"], params["sigma"]
        mean = math.exp(mu + s**2 / 2)
        return mean, (math.exp(s**2) - 1) * mean**2
    alpha, xm = params["alpha"], params["xm"]
    mean = alpha * xm / (alpha - 1) if alpha > 1 else None
    variance = xm**2 * alpha / ((alpha - 1) ** 2 * (alpha - 2)) if alpha > 2 else None
    return mean, variance


def stress(model: str, params: dict, severity_multiplier: float = 1.0, tail_multiplier: float = 1.0) -> dict:
    validate(model, params)
    if severity_multiplier <= 0 or tail_multiplier <= 0:
        raise ValueError("Les multiplicateurs de sévérité et de queue doivent être strictement positifs")
    s, t = severity_multiplier, tail_multiplier
    if model == "gamma":
        return {"shape": params["shape"] / t**2, "scale": params["scale"] * s * t**2}
    if model == "lognormal":
        return {"mu": params["mu"] + math.log(s), "sigma": params["sigma"] * t}
    return {"alpha": params["alpha"] / t, "xm": params["xm"] * s}


def sample(model: str, params: dict, rng: np.random.Generator, size: int) -> np.ndarray:
    validate(model, params)
    if model == "gamma":
        return rng.gamma(params["shape"], params["scale"], size)
    if model == "lognormal":
        return rng.lognormal(params["mu"], params["sigma"], size)
    return (rng.pareto(params["alpha"], size) + 1) * params["xm"]


def pdf_curve(model: str, params: dict, points: int = 80) -> list[dict]:
    """Densité entre le quantile 0,5 % et le quantile 99 % (affichage)."""
    dist = _distribution(model, params)
    xs = np.linspace(dist.ppf(0.005), dist.ppf(0.99), points)
    return [{"x": float(x), "density": float(d)} for x, d in zip(xs, dist.pdf(xs))]
