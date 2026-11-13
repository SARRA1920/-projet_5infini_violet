"""Laboratoire de modèles : catalogue commun et exécution au format uniforme.

Chaque exécution renvoie la même structure (indicateurs, distribution, hypothèses,
paramètres utilisés, provenance), ce qui permet de comparer des modèles côte à côte.
Les calculs délèguent aux modules existants : aucune formule n'est dupliquée ici.
Aucun modèle d'apprentissage automatique.
"""

import math

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial.loss_models import frequency, severity
from app.actuarial.risk.expected_shortfall import historical_es, monte_carlo_es, parametric_es
from app.actuarial.risk.var import (
    MIN_OBSERVATIONS,
    historical_var,
    monte_carlo_var,
    parametric_var,
    simulate_portfolio_returns,
)
from app.actuarial.services import optimization_service, stochastic_service
from app.actuarial.services.market_data_service import returns_matrix
from app.actuarial.services.portfolio_risk_service import get_owned_portfolio, portfolio_returns
from app.actuarial.stats import histogram
from app.models.models import Asset, User

P = lambda name, label, default, unit="": {"name": name, "label": label, "default": default, "unit": unit}  # noqa: E731

VAR_ASSUMPTIONS = [
    "Rendements simples quotidiens, composition constante sur la période.",
    "Perte = −rendement ; VaR = quantile des pertes (inverted_cdf) ; ES = moyenne au-delà.",
]

CATALOG = {
    "var_historical": {
        "family": "risk", "label": "VaR historique", "target": "portfolio_or_assets",
        "formula": "VaR_α = quantile_α(−r) × √h",
        "assumptions": VAR_ASSUMPTIONS + ["Distribution empirique sans hypothèse de loi ; règle de la racine du temps."],
        "params": [],
    },
    "var_parametric": {
        "family": "risk", "label": "VaR paramétrique", "target": "portfolio_or_assets",
        "formula": "VaR_α = −μh + z_α σ √h",
        "assumptions": VAR_ASSUMPTIONS + ["Rendements normaux : sous-estime les queues épaisses."],
        "params": [],
    },
    "var_monte_carlo": {
        "family": "risk", "label": "VaR Monte Carlo", "target": "portfolio_or_assets",
        "formula": "log-rendements ~ N(μh, Σh), VaR sur les rendements simulés",
        "assumptions": VAR_ASSUMPTIONS + ["Lognormalité multivariée, corrélations historiques constantes."],
        "params": [],
    },
    "gbm": {
        "family": "stochastic", "label": "Mouvement brownien géométrique", "target": "asset",
        "formula": "dS = μ S dt + σ S dW",
        "assumptions": ["μ, σ constants ; rendements log normaux et indépendants ; calibration sur les cours réels si vide."],
        "params": [P("s0", "Prix initial", None), P("mu", "Dérive μ", None, "%"), P("sigma", "Volatilité σ", None, "%")],
    },
    "vasicek": {
        "family": "stochastic", "label": "Vasicek", "target": "none",
        "formula": "dr = a(b − r)dt + σ dW",
        "assumptions": ["Taux gaussien avec retour à la moyenne ; peut devenir négatif."],
        "params": [P("r0", "Taux initial r₀", 0.03, "%"), P("a", "Vitesse a", 0.5), P("b", "Niveau long terme b", 0.04, "%"),
                   P("sigma", "Volatilité σ", 0.01, "%")],
    },
    "cir": {
        "family": "stochastic", "label": "Cox-Ingersoll-Ross", "target": "none",
        "formula": "dr = a(b − r)dt + σ √r dW",
        "assumptions": ["Taux positif si 2ab ≥ σ² (condition de Feller)."],
        "params": [P("r0", "Taux initial r₀", 0.03, "%"), P("a", "Vitesse a", 0.5), P("b", "Niveau long terme b", 0.04, "%"),
                   P("sigma", "Volatilité σ", 0.05, "%")],
    },
    "hull_white": {
        "family": "stochastic", "label": "Hull-White", "target": "none",
        "formula": "dr = (θ(t) − a r)dt + σ dW",
        "assumptions": ["θ(t) ajusté à la courbe zéro-coupon initiale saisie (hypothèse) ; taux gaussien."],
        "params": [P("a", "Vitesse a", 0.3), P("sigma", "Volatilité σ", 0.01, "%"),
                   P("curve_maturities", "Maturités de la courbe (ans)", [1, 5, 10]),
                   P("curve_rates", "Taux zéro-coupon", [0.03, 0.035, 0.04], "%")],
    },
    "markowitz": {
        "family": "optimization", "label": "Markowitz (Sharpe maximal)", "target": "portfolio",
        "formula": "max (wᵀμ − rf) / √(wᵀΣw), Σw = 1",
        "assumptions": ["μ et Σ historiques pris comme estimations ; résultat indicatif, aucun ordre passé."],
        "params": [P("max_weight", "Pondération maximale", 1.0, "%"), P("risk_free_rate", "Taux sans risque", 0.0, "%")],
    },
    "poisson": {
        "family": "frequency", "label": "Poisson", "target": "none",
        "formula": "P(N = k) = e^(−λ) λ^k / k!",
        "assumptions": ["Pertes indépendantes, intensité constante ; moyenne = variance."],
        "params": [P("lam", "Intensité λ", 3.0)],
    },
    "negative_binomial": {
        "family": "frequency", "label": "Binomiale négative", "target": "none",
        "formula": "E[N] = r(1 − p)/p, Var[N] = E[N] + E[N]²/r",
        "assumptions": ["Surdispersion : intensité elle-même aléatoire (mélange Poisson-Gamma)."],
        "params": [P("r", "Paramètre r", 2.0), P("p", "Paramètre p", 0.4)],
    },
    "gamma": {
        "family": "severity", "label": "Gamma", "target": "none",
        "formula": "f(x) = x^(k−1) e^(−x/θ) / (Γ(k) θ^k)",
        "assumptions": ["Queue fine (décroissance exponentielle)."],
        "params": [P("shape", "Forme k", 2.0), P("scale", "Échelle θ", 5000.0)],
    },
    "lognormal": {
        "family": "severity", "label": "Lognormale", "target": "none",
        "formula": "ln X ~ N(μ, σ²)",
        "assumptions": ["Queue modérément épaisse ; tous les moments finis."],
        "params": [P("mu", "μ (de ln X)", 8.5), P("sigma", "σ (de ln X)", 1.0)],
    },
    "pareto": {
        "family": "severity", "label": "Pareto", "target": "none",
        "formula": "P(X > x) = (x_m / x)^α, x ≥ x_m",
        "assumptions": ["Queue épaisse (puissance) ; moyenne infinie si α ≤ 1, variance infinie si α ≤ 2."],
        "params": [P("alpha", "Indice de queue α", 2.5), P("xm", "Seuil x_m", 5000.0)],
    },
}


def catalog() -> list[dict]:
    return [{"id": key, **spec} for key, spec in CATALOG.items()]


def metric(key: str, label: str, value, kind: str = "number") -> dict:
    if isinstance(value, float) and not math.isfinite(value):
        value = None
    return {"key": key, "label": label, "value": value, "kind": kind}


def _target_returns(db: Session, user: User, spec: dict) -> tuple[np.ndarray, np.ndarray, list[str], float, str]:
    """(matrice des rendements, poids, symboles, valeur exposée, description de la cible)."""
    symbols = spec.get("symbols") or []
    if not symbols:
        portfolio = get_owned_portfolio(db, user, spec.get("portfolio_id"))
        data = portfolio_returns(db, portfolio, spec.get("lookback"))
        if not data.matrix.asset_ids:
            raise ValueError("Aucune position avec historique dans ce portefeuille")
        names = [data.symbols[a] for a in data.matrix.asset_ids]
        return data.matrix.values, data.weights, names, data.snapshot.total_value, f"portefeuille « {portfolio.name} »"
    wanted = [s.strip().upper() for s in symbols]
    assets = {a.symbol: a for a in db.scalars(select(Asset).where(Asset.symbol.in_(wanted)))}
    unknown = [s for s in wanted if s not in assets]
    if unknown:
        raise LookupError(f"Actif(s) inconnu(s) : {', '.join(unknown)}")
    matrix = returns_matrix(db, [assets[s].id for s in wanted], spec.get("lookback"))
    if matrix.excluded:
        raise ValueError("Historique insuffisant pour au moins un actif")
    raw = np.asarray(spec.get("weights") or [1.0] * len(wanted), dtype=float)
    if raw.size != len(wanted) or raw.sum() <= 0:
        raise ValueError("Poids invalides")
    by_id = {assets[s].id: w for s, w in zip(wanted, raw / raw.sum())}
    weights = np.array([by_id[a] for a in matrix.asset_ids])
    names = [next(s for s in wanted if assets[s].id == a) for a in matrix.asset_ids]
    return matrix.values, weights, names, spec.get("notional") or 100_000.0, "panier " + ", ".join(names)


def _run_var(db, user, model, spec) -> dict:
    values, weights, names, exposure, target = _target_returns(db, user, spec)
    returns = values @ weights
    if returns.size < MIN_OBSERVATIONS:
        raise ValueError(f"Seulement {returns.size} jours d'historique (minimum {MIN_OBSERVATIONS})")
    conf, h = spec["confidence"], spec["horizon"]
    # `marker` : VaR placée sur l'histogramme, à l'horizon de la distribution affichée.
    if model == "var_historical":
        var, es, dist, source = historical_var(returns, conf, h), historical_es(returns, conf, h), returns, "real_market_data"
        marker = historical_var(returns, conf, 1)
    elif model == "var_parametric":
        var, es, dist, source = parametric_var(returns, conf, h), parametric_es(returns, conf, h), returns, "real_market_data"
        marker = parametric_var(returns, conf, 1)
    else:
        dist = simulate_portfolio_returns(values, weights, h, spec["n_simulations"], spec.get("seed"))
        var, es, source = monte_carlo_var(dist, conf), monte_carlo_es(dist, conf), "simulated"
        marker = var
    label = f"{round(conf * 100)} % · {h} j"
    return {
        "data_source": source,
        "target": target,
        "metrics": [
            metric("var", f"VaR {label}", var, "pct"),
            metric("var_amount", "VaR en montant", var * exposure, "amount"),
            metric("es", f"Expected Shortfall {label}", es, "pct"),
            metric("es_amount", "ES en montant", es * exposure, "amount"),
            metric("observations", "Jours d'historique", int(returns.size), "count"),
        ],
        "histogram": histogram(dist, 40),
        "histogram_kind": "pct",
        "histogram_label": "Rendements simulés à l'horizon" if model == "var_monte_carlo" else "Rendements quotidiens observés",
        "marker": -marker,
        "params_used": {"symbols": names, "weights": weights.tolist(), "exposure": exposure},
    }


def _run_stochastic(db, user, model, spec) -> dict:
    params = dict(spec.get("params") or {})
    notes = []
    if model == "gbm" and any(params.get(k) is None for k in ("s0", "mu", "sigma")):
        symbols = spec.get("symbols") or []
        if not symbols:
            raise ValueError("GBM : choisissez un actif pour calibrer, ou saisissez s0, μ et σ")
        calibrated = stochastic_service.calibrate(db, "gbm", symbols[0], None, 1 / 252, spec.get("lookback"))
        params = {**calibrated["params"], **{k: v for k, v in params.items() if v is not None}}
        notes.append(f"Paramètres manquants calibrés sur {calibrated['symbol']} ({calibrated['observations']} rendements).")
    required = {"gbm": ("s0", "mu", "sigma"), "vasicek": ("r0", "a", "b", "sigma"), "cir": ("r0", "a", "b", "sigma"),
                "hull_white": ("a", "sigma", "curve_maturities", "curve_rates")}[model]
    missing = [k for k in required if params.get(k) is None]
    if missing:
        raise ValueError(f"Paramètres manquants : {', '.join(missing)}")
    params = {k: params[k] for k in required}
    result = stochastic_service.simulate(model, params, spec["horizon_years"], spec["steps"], spec["n_simulations"], spec.get("seed"))
    t, an = result["terminal"], result["analytics"]
    kind = "amount" if model == "gbm" else "pct"
    metrics = [
        metric("mean", "Moyenne à l'horizon", t["mean"], kind),
        metric("analytic_mean", "Moyenne théorique", an["analytic_mean"], kind),
        metric("std", "Écart-type", t["std"], kind),
        metric("p05", "Quantile 5 %", t["quantiles"]["p05"], kind),
        metric("p95", "Quantile 95 %", t["quantiles"]["p95"], kind),
    ]
    if model == "gbm":
        metrics += [metric("prob_loss", "Probabilité de perte", an["probability_of_loss"], "pct"),
                    metric("var_95", "VaR 95 % (relative)", an["var_95"], "pct")]
    else:
        metrics += [metric("prob_negative", "P(taux < 0)", an["probability_negative_rate"], "pct"),
                    metric("zero_coupon", "Zéro-coupon simulé", an["zero_coupon_mc"], "number")]
    return {
        "data_source": "simulated",
        "target": (spec.get("symbols") or [None])[0] if model == "gbm" else "taux court",
        "metrics": metrics,
        "histogram": result["terminal_histogram"],
        "histogram_kind": kind,
        "histogram_label": "Distribution à l'horizon",
        "marker": None,
        "params_used": params,
        "notes": notes,
    }


def _run_markowitz(db, user, spec) -> dict:
    params = spec.get("params") or {}
    portfolio = get_owned_portfolio(db, user, spec.get("portfolio_id"))
    result = optimization_service.optimize(
        db, portfolio, spec.get("symbols") or [], spec.get("lookback"), params.get("risk_free_rate") or 0.0,
        params.get("max_weight") or 1.0, False, None, 10,
    )
    best, low = result["optimized"]["max_sharpe"], result["optimized"]["min_variance"]
    metrics = [
        metric("return", "Rendement espéré (Sharpe max.)", best["expected_return"], "pct"),
        metric("volatility", "Volatilité (Sharpe max.)", best["volatility"], "pct"),
        metric("sharpe", "Ratio de Sharpe", best["sharpe_ratio"], "number"),
        metric("min_vol", "Volatilité minimale atteignable", low["volatility"], "pct"),
    ]
    if result["current"]:
        metrics.append(metric("current_sharpe", "Sharpe de l'allocation actuelle", result["current"]["sharpe_ratio"], "number"))
    metrics += [metric(f"w_{s}", f"Poids {s}", w, "pct") for s, w in zip(result["symbols"], best["weights"])]
    return {
        "data_source": "real_market_data",
        "target": f"portefeuille « {portfolio.name} »",
        "metrics": metrics,
        "histogram": None,
        "histogram_kind": None,
        "histogram_label": None,
        "marker": None,
        "params_used": {**params, "symbols": result["symbols"]},
        "notes": result["warnings"],
    }


def _run_distribution(model, spec) -> dict:
    family = CATALOG[model]["family"]
    params = {p["name"]: (spec.get("params") or {}).get(p["name"], p["default"]) for p in CATALOG[model]["params"]}
    rng = np.random.default_rng(spec.get("seed"))
    n = spec["n_simulations"]
    if family == "frequency":
        mean, variance = frequency.moments(model, params)
        draws = frequency.sample(model, params, rng, n)
        metrics = [
            metric("mean", "Moyenne", mean), metric("variance", "Variance", variance),
            metric("dispersion", "Indice de dispersion (Var/E)", variance / mean if mean else None),
            metric("p_zero", "P(N = 0)", frequency.pmf(model, params, 0)[0], "pct"),
            metric("q95", "Quantile 95 % (simulé)", float(np.quantile(draws, 0.95)), "count"),
            metric("q99", "Quantile 99 % (simulé)", float(np.quantile(draws, 0.99)), "count"),
        ]
        kind = "count"
    else:
        desc = severity.describe(model, params)
        draws = severity.sample(model, params, rng, n)
        draws = draws[draws <= np.quantile(draws, 0.99)]  # affichage : 1 % des plus grandes valeurs hors histogramme
        metrics = [
            metric("mean", "Moyenne", desc["mean"], "amount"), metric("std", "Écart-type", desc["std"], "amount"),
            metric("q95", "Quantile 95 %", desc["quantile_95"], "amount"),
            metric("q99", "Quantile 99 %", desc["quantile_99"], "amount"),
            metric("q995", "Quantile 99,5 %", desc["quantile_995"], "amount"),
        ]
        kind = "amount"
    return {
        "data_source": "user_assumption",
        "target": None,
        "metrics": metrics,
        "histogram": histogram(draws, 40),
        "histogram_kind": kind,
        "histogram_label": "Tirages simulés" + (" (jusqu'au quantile 99 %)" if family == "severity" else ""),
        "marker": None,
        "params_used": params,
    }


def run(db: Session, user: User, spec: dict) -> dict:
    model = spec["model"]
    if model not in CATALOG:
        raise ValueError(f"Modèle inconnu : {model}")
    family = CATALOG[model]["family"]
    if family == "risk":
        result = _run_var(db, user, model, spec)
    elif family == "stochastic":
        result = _run_stochastic(db, user, model, spec)
    elif family == "optimization":
        result = _run_markowitz(db, user, spec)
    else:
        result = _run_distribution(model, spec)
    return {
        "model": model,
        "label": CATALOG[model]["label"],
        "family": family,
        "formula": CATALOG[model]["formula"],
        "assumptions": CATALOG[model]["assumptions"],
        "seed": spec.get("seed"),
        "notes": result.pop("notes", []),
        **result,
    }
