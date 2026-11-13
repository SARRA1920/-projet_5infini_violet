"""Calibration et simulation des modèles stochastiques (GBM, Vasicek, CIR, Hull-White).

Provenance des données :
- GBM : calibré sur les cours réels de price_history (real_market_data) ;
- modèles de taux : aucune série de taux n'est stockée dans l'application. Ils sont
  calibrés sur une série fournie par l'utilisateur, ou paramétrés à la main
  (user_assumption). Rien n'est inventé côté serveur.
Les trajectoires sont toujours des résultats simulés (simulated).
"""

import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial.services.market_data_service import closes_by_asset
from app.actuarial.stats import describe, fan, histogram, sample_paths
from app.actuarial.stochastic import cir, gbm, hull_white, vasicek
from app.models.models import Asset

RATE_MODELS = ("vasicek", "cir", "hull_white")
MODELS = ("gbm", *RATE_MODELS)
SENSITIVITY_MULTIPLIERS = (0.5, 0.75, 1.0, 1.25, 1.5)
SENSITIVITY_MAX_SIMULATIONS = 2_000


class UnknownAssetError(LookupError):
    pass


def _asset_closes(db: Session, symbol: str, lookback: int | None) -> tuple[Asset, list]:
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    if asset is None:
        raise UnknownAssetError(f"Actif inconnu : {symbol}")
    series = closes_by_asset(db, [asset.id]).get(asset.id, [])
    if lookback:
        series = series[-(lookback + 1):]
    return asset, series


def calibrate(
    db: Session, model: str, symbol: str | None, series: list[float] | None, dt: float, lookback: int | None
) -> dict:
    if model == "gbm":
        if not symbol:
            raise ValueError("Choisissez un actif pour calibrer le GBM")
        asset, closes = _asset_closes(db, symbol, lookback)
        params = gbm.calibrate(np.array([c for _, c in closes]))
        return {
            "model": model,
            "data_source": "real_market_data",
            "symbol": asset.symbol,
            "period_start": closes[0][0],
            "period_end": closes[-1][0],
            "params": {k: params[k] for k in ("mu", "sigma", "s0")},
            "standard_errors": params["standard_errors"],
            "observations": params["observations"],
            "notes": ["μ et σ annualisés (252 jours) ; s0 = dernier cours de clôture."],
        }
    if model not in RATE_MODELS:
        raise ValueError(f"Modèle inconnu : {model}")
    if not series:
        raise ValueError("Fournissez une série historique de taux (en fractions : 0.035 pour 3,5 %)")
    rates = np.asarray(series, dtype=float)
    fitted = cir.calibrate(rates, dt) if model == "cir" else vasicek.calibrate(rates, dt)
    params = {k: fitted[k] for k in ("a", "b", "sigma", "r0")}
    notes = [f"Estimation par moindres carrés sur {fitted['observations']} observations, pas de {dt:.4f} an."]
    if model == "cir":
        notes.append("Condition de Feller " + ("respectée." if cir.feller(params["a"], params["b"], params["sigma"])
                                               else "non respectée : le taux peut toucher 0."))
    if model == "hull_white":
        params.pop("b")
        params.pop("r0")
        notes.append("Seuls a et σ sont estimés ; θ(t) est ajusté à la courbe initiale saisie.")
    return {
        "model": model,
        "data_source": "user_assumption",
        "symbol": None,
        "period_start": None,
        "period_end": None,
        "params": params,
        "standard_errors": None,
        "observations": fitted["observations"],
        "notes": notes,
    }


def _run(model: str, p: dict, horizon: float, steps: int, n: int, seed: int | None):
    if model == "gbm":
        return gbm.simulate(p["s0"], p["mu"], p["sigma"], horizon, steps, n, seed)
    if model == "vasicek":
        return vasicek.simulate(p["r0"], p["a"], p["b"], p["sigma"], horizon, steps, n, seed)
    if model == "cir":
        return cir.simulate(p["r0"], p["a"], p["b"], p["sigma"], horizon, steps, n, seed)
    return hull_white.simulate(p["curve"], p["a"], p["sigma"], horizon, steps, n, seed)


def _discount_mc(paths: np.ndarray, times: np.ndarray) -> float:
    return float(np.exp(-np.trapezoid(paths, times, axis=1)).mean())


def _analytics(model: str, p: dict, horizon: float, paths: np.ndarray, times: np.ndarray) -> dict:
    """Valeurs théoriques à comparer aux résultats simulés (contrôle de cohérence)."""
    terminal = paths[:, -1]
    if model == "gbm":
        loss_mc = float((terminal < p["s0"]).mean())
        relative = terminal / p["s0"] - 1
        return {
            "analytic_mean": gbm.expected_value(p["s0"], p["mu"], horizon),
            "analytic_std": p["s0"] * math.exp(p["mu"] * horizon) * math.sqrt(math.expm1(p["sigma"] ** 2 * horizon)),
            "probability_of_loss": loss_mc,
            "probability_of_loss_analytic": gbm.probability_below(p["s0"], p["mu"], p["sigma"], horizon, p["s0"]),
            "var_95": float(-np.quantile(relative, 0.05, method="inverted_cdf")),
            "var_99": float(-np.quantile(relative, 0.01, method="inverted_cdf")),
        }
    result = {
        "probability_negative_rate": float((terminal < 0).mean()),
        "zero_coupon_mc": _discount_mc(paths, times),
    }
    if model == "vasicek":
        result.update(
            analytic_mean=vasicek.mean(p["r0"], p["a"], p["b"], horizon),
            analytic_std=math.sqrt(vasicek.variance(p["a"], p["sigma"], horizon)),
            zero_coupon_analytic=vasicek.zero_coupon_price(p["r0"], p["a"], p["b"], p["sigma"], horizon),
        )
    elif model == "cir":
        result.update(
            analytic_mean=cir.mean(p["r0"], p["a"], p["b"], horizon),
            analytic_std=math.sqrt(cir.variance(p["r0"], p["a"], p["b"], p["sigma"], horizon)),
            zero_coupon_analytic=cir.zero_coupon_price(p["r0"], p["a"], p["b"], p["sigma"], horizon),
            feller_condition=cir.feller(p["a"], p["b"], p["sigma"]),
        )
    else:
        result.update(
            analytic_mean=hull_white.mean(p["curve"], p["a"], p["sigma"], horizon),
            analytic_std=math.sqrt(hull_white.variance(p["a"], p["sigma"], horizon)),
            zero_coupon_analytic=p["curve"].discount(horizon),
        )
    return result


def _sensitivity(model: str, p: dict, horizon: float, steps: int, n: int, seed: int | None) -> list[dict]:
    """Effet de la volatilité σ (x0,5 à x1,5), mêmes tirages aléatoires pour chaque point."""
    n = min(n, SENSITIVITY_MAX_SIMULATIONS)
    rows = []
    for multiplier in SENSITIVITY_MULTIPLIERS:
        shocked = {**p, "sigma": p["sigma"] * multiplier}
        paths, times = _run(model, shocked, horizon, steps, n, seed)
        terminal = paths[:, -1]
        row = {"sigma_multiplier": multiplier, "sigma": shocked["sigma"], "mean": float(terminal.mean()),
               "std": float(terminal.std(ddof=1)) if n > 1 else 0.0}
        if model == "gbm":
            row["probability_of_loss"] = float((terminal < p["s0"]).mean())
            row["var_95"] = float(-np.quantile(terminal / p["s0"] - 1, 0.05, method="inverted_cdf"))
        else:
            row["probability_negative_rate"] = float((terminal < 0).mean())
            row["zero_coupon_mc"] = _discount_mc(paths, times)
        rows.append(row)
    return rows


def simulate(model: str, params: dict, horizon: float, steps: int, n_simulations: int, seed: int | None) -> dict:
    """`params` : s0, mu, sigma (GBM) ; r0, a, b, sigma (Vasicek, CIR) ;
    a, sigma, curve_maturities, curve_rates (Hull-White)."""
    if model not in MODELS:
        raise ValueError(f"Modèle inconnu : {model}")
    p = dict(params)
    if model == "hull_white":
        p["curve"] = hull_white.ZeroCurve(p.pop("curve_maturities"), p.pop("curve_rates"))
    paths, times = _run(model, p, horizon, steps, n_simulations, seed)
    terminal = paths[:, -1]
    return {
        "model": model,
        "data_source": "simulated",
        "horizon_years": horizon,
        "steps": steps,
        "n_simulations": n_simulations,
        "seed": seed,
        "times": [row["t"] for row in fan(paths, times)],
        "fan": fan(paths, times),
        "sample_paths": sample_paths(paths, times),
        "terminal": describe(terminal),
        "terminal_histogram": histogram(terminal, 40),
        "analytics": _analytics(model, p, horizon, paths, times),
        "sensitivity": _sensitivity(model, p, horizon, steps, n_simulations, seed),
    }
