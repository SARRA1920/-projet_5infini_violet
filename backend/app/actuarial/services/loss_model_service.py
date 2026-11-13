"""Modélisation des pertes fréquence-sévérité : données, ajustement, simulation, capital, stress.

Trois sources de données, toujours identifiées :
- real_market_data : événements de perte de marché tirés de price_history. Un
  événement est un jour où la perte dépasse un seuil (en % de la valeur exposée) ;
  sa sévérité est le montant perdu ce jour-là ; la fréquence est le nombre
  d'événements par mois civil. Hypothèse simplificatrice : événements
  indépendants (la volatilité des marchés est en réalité regroupée dans le temps) ;
- user_assumption : nombres et montants saisis par l'utilisateur ;
- synthetic : données générées par les lois et paramètres choisis, avec graine.
"""

from collections import Counter

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial.loss_models import frequency, severity
from app.actuarial.loss_models.aggregate_losses import compound_moments, simulate
from app.actuarial.loss_models.capital import REFERENCE_LEVEL, risk_measures
from app.actuarial.services.market_data_service import returns_matrix
from app.actuarial.services.portfolio_risk_service import get_owned_portfolio, portfolio_returns
from app.actuarial.stats import describe, histogram
from app.models.models import Asset, User

DEFAULT_SCENARIOS = (
    {"name": "Central", "frequency_multiplier": 1.0, "severity_multiplier": 1.0, "tail_multiplier": 1.0},
    {"name": "Fréquence +50 %", "frequency_multiplier": 1.5, "severity_multiplier": 1.0, "tail_multiplier": 1.0},
    {"name": "Sévérité +50 %", "frequency_multiplier": 1.0, "severity_multiplier": 1.5, "tail_multiplier": 1.0},
    {"name": "Queue épaissie +25 %", "frequency_multiplier": 1.0, "severity_multiplier": 1.0, "tail_multiplier": 1.25},
    {"name": "Combiné adverse", "frequency_multiplier": 1.5, "severity_multiplier": 1.5, "tail_multiplier": 1.25},
)
SCENARIO_MAX_YEARS = 50_000


def _monthly_counts(dates: list, event_dates: list) -> tuple[list[str], list[int]]:
    """Nombre d'événements par mois civil, mois sans événement compris."""
    months = sorted({(d.year, d.month) for d in dates})
    per_month = Counter((d.year, d.month) for d in event_dates)
    return [f"{y}-{m:02d}" for y, m in months], [per_month.get(month, 0) for month in months]


def market_dataset(
    db: Session,
    user: User,
    symbol: str | None,
    portfolio_id: int | None,
    threshold: float,
    notional: float | None,
    lookback: int | None,
) -> dict:
    if not 0 < threshold < 1:
        raise ValueError("Le seuil de perte doit être entre 0 et 100 %")
    if symbol:
        asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
        if asset is None:
            raise LookupError(f"Actif inconnu : {symbol}")
        matrix = returns_matrix(db, [asset.id], lookback)
        if not matrix.asset_ids:
            raise ValueError(f"Pas d'historique de cours pour {asset.symbol}")
        dates, returns = matrix.dates, matrix.values[:, 0]
        exposure = notional or 100_000.0
        label = f"{asset.symbol}, valeur exposée {exposure:,.0f}".replace(",", " ")
    else:
        portfolio = get_owned_portfolio(db, user, portfolio_id)
        data = portfolio_returns(db, portfolio, lookback)
        if data.returns.size == 0:
            raise ValueError("Aucune position avec historique : pas d'événement de perte observable")
        dates, returns = data.matrix.dates, data.returns
        exposure = notional or data.snapshot.total_value
        label = f"portefeuille « {portfolio.name} », composition actuelle"
    losses = -returns
    hit = losses > threshold
    event_dates = [d for d, h in zip(dates, hit) if h]
    labels, counts = _monthly_counts(dates, event_dates)
    return {
        "source": "market",
        "data_source": "real_market_data",
        "description": f"Jours de perte > {threshold * 100:.2f} % ({label}), du {dates[0]} au {dates[-1]}".replace(".", ","),
        "period_label": "mois",
        "periods_per_year": 12,
        "period_labels": labels,
        "counts": counts,
        "amounts": (losses[hit] * exposure).tolist(),
        "threshold_amount": threshold * exposure,
    }


def synthetic_dataset(
    freq_model: str, freq_params: dict, sev_model: str, sev_params: dict, periods: int, periods_per_year: int, seed: int | None
) -> dict:
    if not 2 <= periods <= 10_000:
        raise ValueError("Le nombre de périodes synthétiques doit être entre 2 et 10 000")
    rng = np.random.default_rng(seed)
    counts = frequency.sample(freq_model, freq_params, rng, periods)
    if counts.sum() > 1_000_000:
        raise ValueError("Trop de pertes synthétiques : réduisez la fréquence ou le nombre de périodes")
    amounts = severity.sample(sev_model, sev_params, rng, int(counts.sum()))
    return {
        "source": "synthetic",
        "data_source": "synthetic",
        "description": f"Données synthétiques : {freq_model} {freq_params}, {sev_model} {sev_params}, graine {seed}",
        "period_label": "période",
        "periods_per_year": periods_per_year,
        "period_labels": [str(i + 1) for i in range(periods)],
        "counts": counts.tolist(),
        "amounts": amounts.tolist(),
        "threshold_amount": sev_params.get("xm") if sev_model == "pareto" else None,
    }


def manual_dataset(counts: list[int], amounts: list[float], periods_per_year: int) -> dict:
    return {
        "source": "manual",
        "data_source": "user_assumption",
        "description": f"Données saisies : {len(counts)} périodes, {len(amounts)} montants",
        "period_label": "période",
        "periods_per_year": periods_per_year,
        "period_labels": [str(i + 1) for i in range(len(counts))],
        "counts": [int(c) for c in counts],
        "amounts": [float(a) for a in amounts],
        "threshold_amount": None,
    }


def _try(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except ValueError as exc:
        return {"error": str(exc)}


def fit_dataset(dataset: dict) -> dict:
    counts = np.asarray(dataset["counts"], dtype=float)
    amounts = np.asarray(dataset["amounts"], dtype=float)
    warnings = []
    if counts.size < 24:
        warnings.append(f"Seulement {counts.size} périodes observées : estimation de la fréquence peu précise.")
    if amounts.size < 30:
        warnings.append(f"Seulement {amounts.size} montants : estimation de la sévérité et de la queue peu précise.")

    freq_fits = [
        {"model": "poisson", **_try(frequency.fit_poisson, counts)},
        {"model": "negative_binomial", **_try(frequency.fit_negative_binomial, counts)},
    ]
    threshold = dataset.get("threshold_amount")
    sev_fits = [
        {"model": m, **_try(severity.fit, m, amounts, **({"threshold": threshold} if m == "pareto" and threshold else {}))}
        for m in severity.MODELS
    ]

    def best(fits):
        ok = [f for f in fits if "error" not in f]
        return min(ok, key=lambda f: f["aic"])["model"] if ok else None

    count_values = Counter(int(c) for c in counts)
    return {
        "dataset": {
            "source": dataset["source"],
            "data_source": dataset["data_source"],
            "description": dataset["description"],
            "period_label": dataset["period_label"],
            "periods_per_year": dataset["periods_per_year"],
            "periods": int(counts.size),
            "events": int(counts.sum()),
            "count_mean": float(counts.mean()) if counts.size else 0.0,
            "count_variance": float(counts.var(ddof=1)) if counts.size > 1 else 0.0,
            "threshold_amount": threshold,
            "counts_by_period": [{"period": p, "count": int(c)} for p, c in zip(dataset["period_labels"], counts)],
            "count_frequencies": [{"count": k, "periods": count_values[k]} for k in sorted(count_values)],
            "amounts": describe(amounts) if amounts.size else None,
            "amounts_histogram": histogram(amounts, 30),
        },
        "frequency_fits": freq_fits,
        "severity_fits": sev_fits,
        "best_frequency": best(freq_fits),
        "best_severity": best(sev_fits),
        "warnings": warnings,
    }


def run_simulation(
    freq_model: str,
    freq_params: dict,
    periods_per_year: int,
    sev_model: str,
    sev_params: dict,
    n_years: int,
    seed: int | None,
    deductible: float,
    limit: float | None,
    scenarios: list[dict] | None,
) -> dict:
    annual = frequency.annualize(freq_model, freq_params, periods_per_year)
    totals, counts = simulate(freq_model, annual, sev_model, sev_params, n_years, seed, deductible, limit)
    analytic = compound_moments(freq_model, annual, sev_model, sev_params)
    measures = risk_measures(totals)
    reference = next(r for r in measures if r["confidence"] == REFERENCE_LEVEL)
    warnings = []
    if deductible or limit:
        warnings.append("Franchise ou plafond appliqués : les moments analytiques portent sur les pertes brutes.")
    if analytic["mean"] is None:
        warnings.append("Sévérité de Pareto avec α <= 1 : perte moyenne théorique infinie, résultats instables.")
    elif analytic["variance"] is None:
        warnings.append("Sévérité de Pareto avec α <= 2 : variance théorique infinie, quantiles extrêmes instables.")

    # Référence des scénarios : modèle central simulé avec le même nombre d'années et la même graine,
    # pour que l'écart de capital ne mélange pas effet du choc et bruit Monte Carlo.
    stress_rows = []
    years = min(n_years, SCENARIO_MAX_YEARS)
    central, _ = simulate(freq_model, annual, sev_model, sev_params, years, seed, deductible, limit)
    base_capital = risk_measures(central, (REFERENCE_LEVEL,))[0]["capital_var"]
    for scenario in scenarios or DEFAULT_SCENARIOS:
        f_params = frequency.stress(freq_model, annual, scenario["frequency_multiplier"])
        s_params = severity.stress(sev_model, sev_params, scenario["severity_multiplier"], scenario["tail_multiplier"])
        stressed, _ = simulate(freq_model, f_params, sev_model, s_params, years, seed, deductible, limit)
        row = next(r for r in risk_measures(stressed, (REFERENCE_LEVEL,)))
        stress_rows.append(
            {
                **scenario,
                "expected_loss": float(stressed.mean()),
                "var": row["var"],
                "tvar": row["tvar"],
                "capital": row["capital_var"],
                "capital_change": row["capital_var"] / base_capital - 1 if base_capital > 0 else None,
            }
        )

    return {
        "data_source": "simulated",
        "n_years": n_years,
        "seed": seed,
        "annual_frequency_params": annual,
        "frequency_moments": dict(zip(("mean", "variance"), frequency.moments(freq_model, annual))),
        "severity": severity.describe(sev_model, sev_params),
        "analytic": {"mean": analytic["mean"], "std": None if analytic["variance"] is None else analytic["variance"] ** 0.5},
        "aggregate": describe(totals),
        "probability_no_loss": float((counts == 0).mean()),
        "histogram": histogram(totals, 50),
        "risk_measures": measures,
        "economic_capital": {
            "confidence": REFERENCE_LEVEL,
            "expected_loss": float(totals.mean()),
            "var": reference["var"],
            "capital": reference["capital_var"],
            "capital_tvar": reference["capital_tvar"],
        },
        "stress": stress_rows,
        "severity_curve": severity.pdf_curve(sev_model, sev_params),
        "frequency_pmf": frequency.pmf(freq_model, freq_params, max(10, int(frequency.moments(freq_model, freq_params)[0] * 3) + 5))[:60],
        "warnings": warnings,
    }
