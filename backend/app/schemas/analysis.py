from datetime import date as Date

from pydantic import BaseModel


class TechnicalAnalysisOut(BaseModel):
    """Cours et indicateurs alignés jour par jour (None tant que l'historique manque)."""

    symbol: str
    name: str
    short_window: int
    long_window: int
    rsi_period: int
    dates: list[Date]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[int]
    sma_short: list[float | None]
    sma_long: list[float | None]
    rsi: list[float | None]


class StrategyResult(BaseModel):
    key: str
    label: str
    curve: list[float]
    return_pct: float
    max_drawdown_pct: float
    entries: int
    time_in_market_pct: float
    return_to_risk: float | None


class CompareOut(BaseModel):
    """Plusieurs stratégies rejouées sur le même actif, même départ, même capital."""

    symbol: str
    name: str
    short_window: int
    long_window: int
    trend_window: int
    rsi_period: int
    initial_capital: float
    dates: list[Date]
    strategies: list[StrategyResult]
