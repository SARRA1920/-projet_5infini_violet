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
