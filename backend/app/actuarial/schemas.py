"""Schémas Pydantic du module Actuariat.

Les indicateurs sont des fractions en float (0.023 = 2,3 %) : ce sont des
estimations statistiques, pas des montants comptables. Les montants sont
arrondis au centime.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DataSource = Literal["real_market_data", "synthetic", "user_assumption", "simulated"]


class PortfolioRef(BaseModel):
    id: int
    name: str


class AssetHistoryOut(BaseModel):
    id: int
    symbol: str
    name: str
    asset_type: str
    observations: int
    first_date: date | None
    last_date: date | None


class DashboardMetrics(BaseModel):
    cumulative_return: float
    annualized_return: float | None
    annualized_volatility: float | None
    var: float
    var_amount: float
    expected_shortfall: float
    expected_shortfall_amount: float
    max_drawdown: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None


class ExposureRow(BaseModel):
    asset_class: str
    value: float
    weight: float


class RiskContributionRow(BaseModel):
    symbol: str
    weight: float
    marginal_contribution: float
    component_contribution: float
    risk_share: float


class DatedValue(BaseModel):
    date: date
    value: float


class DashboardOut(BaseModel):
    portfolio_id: int
    portfolio_name: str
    data_source: DataSource
    total_value: float
    cash: float
    positions_value: float
    realized_pnl_total: float
    transactions_count: int
    confidence: float
    horizon_days: int
    lookback_days: int | None
    risk_free_rate: float
    observations: int
    period_start: date | None
    period_end: date | None
    metrics: DashboardMetrics | None
    exposure: list[ExposureRow]
    risk_contributions: list[RiskContributionRow]
    concentration_hhi: float | None
    value_curve: list[DatedValue]
    daily_returns: list[DatedValue]
    warnings: list[str]


# ---------- Risk Analytics ----------
Confidence = Literal[0.95, 0.99]
Horizon = Literal[1, 10, 20]


class VarRow(BaseModel):
    method: Literal["historical", "parametric", "monte_carlo"]
    confidence: float
    horizon_days: int
    var: float
    var_amount: float
    expected_shortfall: float
    expected_shortfall_amount: float


class HistogramBin(BaseModel):
    """Classe d'histogramme [from, to[ ; « from » est un mot réservé en Python, d'où l'alias."""

    model_config = {"populate_by_name": True, "serialize_by_alias": True}

    from_: float = Field(alias="from")
    to: float
    count: int


class AssetRiskRow(BaseModel):
    symbol: str
    weight: float
    annualized_return: float | None
    annualized_volatility: float | None
    var_1d: float
    max_drawdown: float | None


class CorrelationOut(BaseModel):
    symbols: list[str]
    matrix: list[list[float]]


class BacktestPoint(BaseModel):
    date: date
    loss: float
    var: float
    hit: bool


class BacktestOut(BaseModel):
    observations: int
    exceptions: int
    expected_exceptions: float
    exception_rate: float
    lr_statistic: float
    p_value: float
    rejected: bool
    window: int
    series: list[BacktestPoint]


class RiskMetricsOut(BaseModel):
    annualized_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None
    sharpe_ratio: float | None
    sortino_ratio: float | None


class RiskReportOut(BaseModel):
    portfolio_id: int | None
    data_source: DataSource
    observations: int
    period_start: date
    period_end: date
    total_value: float
    confidence: float
    horizon_days: int
    n_simulations: int
    seed: int | None
    var_table: list[VarRow]
    metrics: RiskMetricsOut
    monte_carlo_distribution: list[HistogramBin]
    assets: list[AssetRiskRow]
    correlation: CorrelationOut
    risk_contributions: list[RiskContributionRow]
    backtest: BacktestOut | None
    warnings: list[str]


class BasketRiskRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=20)
    weights: list[float] | None = Field(None, description="Normalisés à 100 % ; poids égaux si absent")
    notional: float = Field(100_000, gt=0, le=1e12)
    lookback: int = Field(252, ge=0, le=5000, description="0 = tout l'historique")
    confidence: Confidence = 0.95
    horizon: Horizon = 1
    n_simulations: int = Field(10_000, ge=1_000, le=50_000)
    seed: int | None = Field(42, ge=0, le=2**31 - 1)
    risk_free_rate: float = Field(0.0, ge=-0.05, le=0.20)
    backtest_window: int = Field(100, ge=30, le=1000)


# ---------- Modèles stochastiques ----------
StochasticModel = Literal["gbm", "vasicek", "cir", "hull_white"]
REQUIRED_PARAMS = {
    "gbm": ("s0", "mu", "sigma"),
    "vasicek": ("r0", "a", "b", "sigma"),
    "cir": ("r0", "a", "b", "sigma"),
    "hull_white": ("a", "sigma", "curve_maturities", "curve_rates"),
}


class CalibrateRequest(BaseModel):
    model: StochasticModel
    symbol: str | None = None
    series: list[float] | None = Field(None, max_length=20_000, description="Taux en fractions (0.035 = 3,5 %)")
    dt: float = Field(1 / 252, gt=0, le=1, description="Pas de la série de taux, en années")
    lookback: int = Field(252, ge=0, le=5000)


class CalibrateOut(BaseModel):
    model: StochasticModel
    data_source: DataSource
    symbol: str | None
    period_start: date | None
    period_end: date | None
    params: dict[str, float]
    standard_errors: dict[str, float] | None
    observations: int
    notes: list[str]


class StochasticParams(BaseModel):
    s0: float | None = Field(None, gt=0)
    mu: float | None = Field(None, ge=-2, le=2)
    sigma: float | None = Field(None, ge=0, le=5)
    r0: float | None = Field(None, ge=-0.2, le=1)
    a: float | None = Field(None, gt=0, le=50)
    b: float | None = Field(None, ge=-0.2, le=1)
    curve_maturities: list[float] | None = Field(None, min_length=1, max_length=50)
    curve_rates: list[float] | None = Field(None, min_length=1, max_length=50)


class SimulateRequest(BaseModel):
    model: StochasticModel
    params: StochasticParams
    symbol: str | None = Field(None, description="Actif simulé (GBM), pour l'historique uniquement")
    horizon: float = Field(1.0, gt=0, le=50, description="Années")
    steps: int = Field(252, ge=1, le=2520)
    n_simulations: int = Field(5_000, ge=1, le=20_000)
    seed: int | None = Field(42, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def _required_params(self):
        missing = [p for p in REQUIRED_PARAMS[self.model] if getattr(self.params, p) is None]
        if missing:
            raise ValueError(f"Paramètres manquants pour {self.model} : {', '.join(missing)}")
        return self

    def model_params(self) -> dict:
        return {p: getattr(self.params, p) for p in REQUIRED_PARAMS[self.model]}


class TerminalStats(BaseModel):
    count: int
    mean: float
    std: float
    min: float
    max: float
    quantiles: dict[str, float]
    mean_standard_error: float
    mean_ci95: list[float]


class SimulateOut(BaseModel):
    model: StochasticModel
    data_source: DataSource
    horizon_years: float
    steps: int
    n_simulations: int
    seed: int | None
    times: list[float]
    fan: list[dict[str, float]]
    sample_paths: list[list[float]]
    terminal: TerminalStats
    terminal_histogram: list[HistogramBin]
    analytics: dict[str, float | bool]
    sensitivity: list[dict[str, float]]


# ---------- Fixed Income ----------
class BondSpec(BaseModel):
    face_value: float = Field(100, gt=0, le=1e9)
    coupon_rate: float = Field(ge=0, le=1, description="0.045 pour 4,5 % par an")
    coupon_frequency: Literal[1, 2, 4, 12] = 2
    maturity_date: date
    issue_date: date | None = None
    day_count: Literal["ACT/365", "ACT/360", "30/360"] = "ACT/365"


class BondTermsIn(BondSpec):
    source: str = Field(min_length=3, max_length=255, description="Provenance des caractéristiques (prospectus…)")


class AnalyzeBondRequest(BaseModel):
    bond: BondSpec
    settlement_date: date | None = None
    clean_price: float | None = Field(None, gt=0)
    ytm: float | None = Field(None, gt=-0.5, lt=2)
    curve_maturities: list[float] | None = Field(None, max_length=50)
    curve_rates: list[float] | None = Field(None, max_length=50)
    shock_bp: float = Field(100, gt=0, le=500)


class CashFlowRow(BaseModel):
    date: date
    time: float
    coupon: float
    principal: float
    amount: float
    discount_factor: float
    present_value: float


class BondAnalysisOut(BaseModel):
    settlement: date
    ytm: float
    clean_price: float
    dirty_price: float
    accrued_interest: float
    macaulay_duration: float
    modified_duration: float
    convexity: float
    dv01: float
    cash_flows: list[CashFlowRow]
    price_yield_curve: list[dict[str, float]]
    parallel_sensitivity: list[dict[str, float]]
    curve_scenarios: list[dict[str, float | str]]
    curve_source: Literal["user_assumption", "flat_at_ytm"]
    shock_bp: float


class BondMarketStats(BaseModel):
    last_price: float
    last_date: date
    observations: int
    annualized_return: float | None
    annualized_volatility: float | None
    max_drawdown: float | None


class CouponSummary(BaseModel):
    count: int
    total: float


class BondListRow(BaseModel):
    asset_id: int
    symbol: str
    name: str
    has_terms: bool
    market: BondMarketStats | None
    coupons: CouponSummary


class BondTermsOut(BaseModel):
    face_value: float
    coupon_rate: float
    coupon_frequency: int
    issue_date: date | None
    maturity_date: date
    day_count: str
    source: str


class BondDetailOut(BaseModel):
    asset_id: int
    symbol: str
    name: str
    market: BondMarketStats | None
    coupons: CouponSummary
    terms: BondTermsOut | None
    analysis: BondAnalysisOut | None
    message: str | None


# ---------- Optimisation ----------
class MarkowitzRequest(BaseModel):
    portfolio_id: int | None = None
    extra_symbols: list[str] = Field(default_factory=list, max_length=30)
    lookback: int = Field(252, ge=0, le=5000)
    risk_free_rate: float = Field(0.0, ge=-0.05, le=0.20)
    max_weight: float = Field(1.0, ge=0.05, le=1.0)
    allow_short: bool = False
    target_return: float | None = Field(None, ge=-1, le=5)
    frontier_points: int = Field(25, ge=5, le=60)


class AllocationOut(BaseModel):
    weights: list[float]
    expected_return: float
    volatility: float
    sharpe_ratio: float | None


class AssetMoments(BaseModel):
    symbol: str
    expected_return: float
    volatility: float


class OptimizationConstraints(BaseModel):
    max_weight: float
    allow_short: bool
    risk_free_rate: float


class RebalanceRow(BaseModel):
    symbol: str
    price: float | None
    current_quantity: float
    target_value: float
    target_quantity: float | None
    quantity_change: float | None


class MarkowitzOut(BaseModel):
    portfolio_id: int
    data_source: DataSource
    observations: int
    period_start: date
    period_end: date
    symbols: list[str]
    assets: list[AssetMoments]
    correlation: CorrelationOut
    constraints: OptimizationConstraints
    current: AllocationOut | None
    optimized: dict[str, AllocationOut]
    frontier: list[AllocationOut]
    notional: float
    rebalance: list[RebalanceRow]
    warnings: list[str]


# ---------- Modèles de pertes (fréquence-sévérité) ----------
FrequencyModel = Literal["poisson", "negative_binomial"]
SeverityModel = Literal["gamma", "lognormal", "pareto"]


class LossDataRequest(BaseModel):
    source: Literal["market", "manual", "synthetic"]
    # market : événements de perte tirés des cours (actif, ou portefeuille si aucun actif)
    symbol: str | None = None
    portfolio_id: int | None = None
    threshold: float = Field(0.01, gt=0, lt=0.5, description="Seuil de perte quotidienne (0.01 = 1 %)")
    notional: float | None = Field(None, gt=0, le=1e12)
    lookback: int = Field(0, ge=0, le=5000, description="0 = tout l'historique")
    # manual
    counts: list[int] | None = Field(None, max_length=10_000)
    amounts: list[float] | None = Field(None, max_length=100_000)
    # synthetic
    frequency_model: FrequencyModel = "poisson"
    frequency_params: dict[str, float] | None = None
    severity_model: SeverityModel = "lognormal"
    severity_params: dict[str, float] | None = None
    periods: int = Field(60, ge=2, le=10_000)
    periods_per_year: int = Field(12, ge=1, le=365)
    seed: int | None = Field(42, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def _source_fields(self):
        if self.source == "manual" and (not self.counts or not self.amounts):
            raise ValueError("Données saisies : fournissez les nombres de pertes par période et les montants")
        if self.source == "synthetic" and (self.frequency_params is None or self.severity_params is None):
            raise ValueError("Données synthétiques : fournissez les paramètres de fréquence et de sévérité")
        return self


class LossDatasetOut(BaseModel):
    source: str
    data_source: DataSource
    description: str
    period_label: str
    periods_per_year: int
    periods: int
    events: int
    count_mean: float
    count_variance: float
    threshold_amount: float | None
    counts_by_period: list[dict[str, str | int]]
    count_frequencies: list[dict[str, int]]
    amounts: TerminalStats | None
    amounts_histogram: list[HistogramBin]


class DistributionFit(BaseModel):
    model: str
    params: dict[str, float] | None = None
    standard_errors: dict[str, float] | None = None
    loglik: float | None = None
    aic: float | None = None
    ks_statistic: float | None = None
    ks_p_value: float | None = None
    mean: float | None = None
    std: float | None = None
    quantile_95: float | None = None
    quantile_99: float | None = None
    quantile_995: float | None = None
    error: str | None = None


class LossFitOut(BaseModel):
    dataset: LossDatasetOut
    frequency_fits: list[DistributionFit]
    severity_fits: list[DistributionFit]
    best_frequency: str | None
    best_severity: str | None
    warnings: list[str]


class StressScenario(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    frequency_multiplier: float = Field(1.0, gt=0, le=10)
    severity_multiplier: float = Field(1.0, gt=0, le=10)
    tail_multiplier: float = Field(1.0, gt=0, le=5)


class LossSimulateRequest(BaseModel):
    frequency_model: FrequencyModel
    frequency_params: dict[str, float] = Field(description="Paramètres par période d'observation")
    periods_per_year: int = Field(1, ge=1, le=365)
    severity_model: SeverityModel
    severity_params: dict[str, float]
    n_years: int = Field(20_000, ge=1_000, le=200_000)
    seed: int | None = Field(42, ge=0, le=2**31 - 1)
    deductible: float = Field(0.0, ge=0)
    limit: float | None = Field(None, gt=0)
    scenarios: list[StressScenario] | None = Field(None, max_length=8)


class CapitalRow(BaseModel):
    confidence: float
    var: float
    tvar: float
    capital_var: float
    capital_tvar: float


class StressRow(StressScenario):
    expected_loss: float
    var: float
    tvar: float
    capital: float
    capital_change: float | None


class LossSimulateOut(BaseModel):
    data_source: DataSource
    n_years: int
    seed: int | None
    annual_frequency_params: dict[str, float]
    frequency_moments: dict[str, float]
    severity: dict[str, float | None]
    analytic: dict[str, float | None]
    aggregate: TerminalStats
    probability_no_loss: float
    histogram: list[HistogramBin]
    risk_measures: list[CapitalRow]
    economic_capital: dict[str, float]
    stress: list[StressRow]
    severity_curve: list[dict[str, float]]
    frequency_pmf: list[float]
    warnings: list[str]


# ---------- Laboratoire de modèles ----------
class LabParam(BaseModel):
    name: str
    label: str
    default: float | list[float] | None
    unit: str


class LabModelOut(BaseModel):
    id: str
    family: Literal["risk", "stochastic", "optimization", "frequency", "severity"]
    label: str
    target: Literal["portfolio_or_assets", "asset", "portfolio", "none"]
    formula: str
    assumptions: list[str]
    params: list[LabParam]


class LabRunRequest(BaseModel):
    model: str
    symbols: list[str] = Field(default_factory=list, max_length=20)
    weights: list[float] | None = None
    portfolio_id: int | None = None
    notional: float | None = Field(None, gt=0, le=1e12)
    lookback: int = Field(252, ge=0, le=5000)
    confidence: Confidence = 0.95
    horizon: Horizon = 1
    horizon_years: float = Field(1.0, gt=0, le=50)
    steps: int = Field(52, ge=1, le=2520)
    n_simulations: int = Field(5_000, ge=100, le=50_000)
    seed: int | None = Field(42, ge=0, le=2**31 - 1)
    params: dict[str, float | list[float] | None] = Field(default_factory=dict)

    def spec(self) -> dict:
        data = self.model_dump()
        data["lookback"] = self.lookback or None
        return data


class LabMetric(BaseModel):
    key: str
    label: str
    value: float | None
    kind: Literal["pct", "amount", "number", "count"]


class LabRunOut(BaseModel):
    model: str
    label: str
    family: str
    formula: str
    assumptions: list[str]
    seed: int | None
    notes: list[str]
    data_source: DataSource
    target: str | None
    metrics: list[LabMetric]
    histogram: list[HistogramBin] | None
    histogram_kind: str | None
    histogram_label: str | None
    marker: float | None
    params_used: dict


class LabCompareRequest(BaseModel):
    runs: list[LabRunRequest] = Field(min_length=1, max_length=6)


class LabCompareItem(BaseModel):
    ok: bool
    result: LabRunOut | None = None
    error: str | None = None
    request: LabRunRequest


class RunHistoryOut(BaseModel):
    id: int
    model: str
    data_source: DataSource
    seed: int | None
    portfolio_id: int | None
    params: dict
    summary: dict
    created_at: datetime
