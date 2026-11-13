"""Routes du module Actuariat, sous /api/actuarial.

Toutes les routes exigent un utilisateur connecté (get_current_user) et ne lisent
que ses propres portefeuilles. Les routes sont synchrones : FastAPI les exécute
dans son pool de threads, les calculs numpy ne bloquent donc pas la boucle
d'événements.
"""

from contextlib import contextmanager
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.actuarial import models  # noqa: F401  (enregistre les tables du module dans Base.metadata)
from app.actuarial.fixed_income.cashflows import Bond
from app.actuarial.risk.var import CONFIDENCE_LEVELS, HORIZONS
from app.actuarial.schemas import (
    AnalyzeBondRequest,
    AssetHistoryOut,
    BasketRiskRequest,
    BondAnalysisOut,
    BondDetailOut,
    BondListRow,
    BondTermsIn,
    BondTermsOut,
    CalibrateOut,
    CalibrateRequest,
    DashboardOut,
    MarkowitzOut,
    MarkowitzRequest,
    PortfolioRef,
    RiskReportOut,
    SimulateOut,
    SimulateRequest,
)
from app.actuarial.models import ActuarialRun
from app.actuarial.schemas import (
    LabCompareItem,
    LabCompareRequest,
    LabModelOut,
    LabRunOut,
    LabRunRequest,
    LossDataRequest,
    LossFitOut,
    LossSimulateOut,
    LossSimulateRequest,
    RunHistoryOut,
)
from app.actuarial.services import (
    fixed_income_service,
    lab_service,
    loss_model_service,
    optimization_service,
    stochastic_service,
)
from app.actuarial.services.market_data_service import asset_history_summary
from app.actuarial.services.portfolio_risk_service import (
    build_dashboard,
    get_owned_portfolio,
    list_user_portfolios,
)
from app.actuarial.services.risk_analytics_service import basket_risk, portfolio_risk_report
from app.actuarial.services.runs import record_run
from app.api.deps import get_current_user, require_admin
from app.core.database import get_db
from app.models.models import User

router = APIRouter(prefix="/api/actuarial", tags=["actuarial"])


@contextmanager
def _http_errors():
    """Erreurs métier -> codes HTTP : introuvable = 404, données ou paramètres invalides = 422."""
    try:
        yield
    except LookupError as exc:  # portefeuille, actif ou obligation introuvable
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _check_choice(name: str, value, allowed: tuple) -> None:
    if value not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"{name} doit valoir {' ou '.join(str(a) for a in allowed)}",
        )


@router.get("/portfolios", response_model=list[PortfolioRef])
def portfolios(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Portefeuilles de l'utilisateur connecté (sélecteur de portefeuille)."""
    return [PortfolioRef(id=p.id, name=p.name) for p in list_user_portfolios(db, current_user)]


@router.get("/assets", response_model=list[AssetHistoryOut])
def assets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Actifs du référentiel avec l'étendue de leur historique de cours."""
    return asset_history_summary(db)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    portfolio_id: int | None = Query(None, description="Par défaut : premier portefeuille de l'utilisateur"),
    lookback: int = Query(252, ge=0, le=5000, description="Jours d'historique ; 0 = tout l'historique"),
    confidence: float = Query(0.95, description="0.95 ou 0.99"),
    horizon: int = Query(1, description="1, 10 ou 20 jours"),
    risk_free_rate: float = Query(0.0, ge=-0.05, le=0.20, description="Taux sans risque annuel (hypothèse)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Tableau de bord actuariel du portefeuille, recalculé à chaque appel."""
    _check_choice("confidence", confidence, CONFIDENCE_LEVELS)
    _check_choice("horizon", horizon, HORIZONS)
    with _http_errors():
        portfolio = get_owned_portfolio(db, current_user, portfolio_id)
    return build_dashboard(db, portfolio, lookback or None, confidence, horizon, risk_free_rate)


# ---------- Risk Analytics ----------
def _selected_row(report: dict) -> list[dict]:
    return [
        row for row in report["var_table"]
        if row["confidence"] == report["confidence"] and row["horizon_days"] == report["horizon_days"]
    ]


@router.get("/portfolio-risk/{portfolio_id}", response_model=RiskReportOut)
def portfolio_risk(
    portfolio_id: int,
    lookback: int = Query(252, ge=0, le=5000, description="0 = tout l'historique"),
    confidence: float = Query(0.95),
    horizon: int = Query(1),
    n_simulations: int = Query(10_000, ge=1_000, le=50_000),
    seed: int | None = Query(42, ge=0, le=2**31 - 1),
    risk_free_rate: float = Query(0.0, ge=-0.05, le=0.20),
    backtest_window: int = Query(100, ge=30, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """VaR et ES (historique, paramétrique, Monte Carlo), corrélations, contributions, backtesting."""
    _check_choice("confidence", confidence, CONFIDENCE_LEVELS)
    _check_choice("horizon", horizon, HORIZONS)
    with _http_errors():
        portfolio = get_owned_portfolio(db, current_user, portfolio_id)
        return portfolio_risk_report(
            db, portfolio, lookback or None, confidence, horizon, n_simulations, seed, risk_free_rate, backtest_window
        )


@router.post("/risk/var", response_model=RiskReportOut)
@router.post("/risk/expected-shortfall", response_model=RiskReportOut)
def risk_of_basket(
    body: BasketRiskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """VaR et Expected Shortfall d'un panier libre d'actifs (les deux routes renvoient les deux mesures)."""
    with _http_errors():
        report = basket_risk(
            db, body.symbols, body.weights, body.notional, body.lookback or None, body.confidence, body.horizon,
            body.n_simulations, body.seed, body.risk_free_rate, body.backtest_window,
        )
    record_run(db, current_user, "var", body.model_dump(), "real_market_data",
               {"selected": _selected_row(report)}, seed=body.seed)
    return report


# ---------- Modèles stochastiques ----------
@router.post("/stochastic/calibrate", response_model=CalibrateOut)
def stochastic_calibrate(
    body: CalibrateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """GBM : calibré sur les cours de l'actif. Taux : calibrés sur la série fournie."""
    with _http_errors():
        return stochastic_service.calibrate(db, body.model, body.symbol, body.series, body.dt, body.lookback or None)


@router.post("/stochastic/simulate", response_model=SimulateOut)
def stochastic_simulate(
    body: SimulateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trajectoires, distribution terminale, contrôles analytiques et sensibilité à σ."""
    with _http_errors():
        result = stochastic_service.simulate(
            body.model, body.model_params(), body.horizon, body.steps, body.n_simulations, body.seed
        )
    record_run(db, current_user, body.model, body.model_dump(), "simulated",
               {"terminal": result["terminal"], "analytics": result["analytics"]}, seed=body.seed)
    return result


# ---------- Fixed Income ----------
@router.get("/fixed-income/bonds", response_model=list[BondListRow])
def fixed_income_bonds(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Obligations du référentiel : statistiques de marché et présence de caractéristiques contractuelles."""
    return fixed_income_service.list_bonds(db, current_user)


@router.get("/fixed-income/{asset_id}", response_model=BondDetailOut)
def fixed_income_detail(
    asset_id: int,
    settlement_date: date | None = Query(None, description="Date de règlement ; aujourd'hui par défaut"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    with _http_errors():
        return fixed_income_service.bond_detail(db, current_user, asset_id, settlement_date or date.today())


@router.post("/fixed-income/analyze", response_model=BondAnalysisOut)
def fixed_income_analyze(
    body: AnalyzeBondRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Obligation théorique saisie par l'utilisateur : flux, YTM, duration, convexité, chocs."""
    spec = body.bond
    with _http_errors():
        bond = Bond(spec.face_value, spec.coupon_rate, spec.coupon_frequency, spec.maturity_date,
                    spec.issue_date, spec.day_count)
        result = fixed_income_service.analyze(
            bond, body.settlement_date or date.today(), body.clean_price, body.ytm,
            body.curve_maturities, body.curve_rates, body.shock_bp,
        )
    summary = {k: result[k] for k in ("ytm", "clean_price", "macaulay_duration", "modified_duration", "convexity")}
    record_run(db, current_user, "bond", body.model_dump(mode="json"), "user_assumption", summary)
    return result


@router.put("/fixed-income/{asset_id}/terms", response_model=BondTermsOut)
def fixed_income_terms(
    asset_id: int,
    body: BondTermsIn,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Administrateurs : enregistre les caractéristiques contractuelles d'une obligation, avec leur source."""
    with _http_errors():
        terms = fixed_income_service.upsert_terms(db, asset_id, body.model_dump())
    return fixed_income_service.terms_out(terms)


# ---------- Optimisation ----------
@router.post("/optimization/markowitz", response_model=MarkowitzOut)
def optimization_markowitz(
    body: MarkowitzRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Variance minimale, Sharpe maximal, rendement cible et frontière efficiente. Aucun ordre passé."""
    with _http_errors():
        portfolio = get_owned_portfolio(db, current_user, body.portfolio_id)
        result = optimization_service.optimize(
            db, portfolio, body.extra_symbols, body.lookback or None, body.risk_free_rate,
            body.max_weight, body.allow_short, body.target_return, body.frontier_points,
        )
    summary = {"symbols": result["symbols"], "max_sharpe": result["optimized"]["max_sharpe"]}
    record_run(db, current_user, "markowitz", body.model_dump(), "real_market_data", summary,
               portfolio_id=portfolio.id)
    return result


# ---------- Modèles de pertes ----------
@router.post("/loss-model/fit", response_model=LossFitOut)
def loss_model_fit(
    body: LossDataRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Construit le jeu de pertes (marché réel, saisi ou synthétique) et ajuste les cinq lois."""
    with _http_errors():
        if body.source == "market":
            dataset = loss_model_service.market_dataset(
                db, current_user, body.symbol, body.portfolio_id, body.threshold, body.notional, body.lookback or None
            )
        elif body.source == "manual":
            dataset = loss_model_service.manual_dataset(body.counts, body.amounts, body.periods_per_year)
        else:
            dataset = loss_model_service.synthetic_dataset(
                body.frequency_model, body.frequency_params, body.severity_model, body.severity_params,
                body.periods, body.periods_per_year, body.seed,
            )
        return loss_model_service.fit_dataset(dataset)


@router.post("/loss-model/simulate", response_model=LossSimulateOut)
def loss_model_simulate(
    body: LossSimulateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Distribution annuelle des pertes, VaR/TVaR, capital économique et scénarios de stress."""
    with _http_errors():
        result = loss_model_service.run_simulation(
            body.frequency_model, body.frequency_params, body.periods_per_year, body.severity_model,
            body.severity_params, body.n_years, body.seed, body.deductible, body.limit,
            [s.model_dump() for s in body.scenarios] if body.scenarios else None,
        )
    record_run(db, current_user, "loss_model", body.model_dump(), "simulated",
               {"economic_capital": result["economic_capital"], "aggregate_mean": result["aggregate"]["mean"]},
               seed=body.seed)
    return result


# ---------- Laboratoire de modèles ----------
@router.get("/lab/catalog", response_model=list[LabModelOut])
def lab_catalog(current_user: User = Depends(get_current_user)):
    """Modèles disponibles : formule, hypothèses et paramètres par défaut."""
    return lab_service.catalog()


@router.post("/lab/run", response_model=LabRunOut)
def lab_run(
    body: LabRunRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    with _http_errors():
        result = lab_service.run(db, current_user, body.spec())
    record_run(db, current_user, body.model, body.model_dump(), result["data_source"],
               {m["key"]: m["value"] for m in result["metrics"]}, seed=body.seed, portfolio_id=body.portfolio_id)
    return result


@router.post("/lab/compare", response_model=list[LabCompareItem])
def lab_compare(
    body: LabCompareRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Exécute jusqu'à six configurations ; une erreur sur l'une n'empêche pas les autres."""
    items = []
    for request in body.runs:
        try:
            with _http_errors():
                items.append({"ok": True, "result": lab_service.run(db, current_user, request.spec()), "request": request})
        except HTTPException as exc:
            items.append({"ok": False, "error": exc.detail, "request": request})
    return items


@router.get("/lab/runs", response_model=list[RunHistoryOut])
def lab_runs(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historique des calculs de l'utilisateur connecté (paramètres et graine : rejouables)."""
    return db.scalars(
        select(ActuarialRun)
        .where(ActuarialRun.user_id == current_user.id)
        .order_by(ActuarialRun.created_at.desc(), ActuarialRun.id.desc())
        .limit(limit)
    ).all()
