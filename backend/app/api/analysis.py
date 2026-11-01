from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, PriceHistory, User
from app.schemas.analysis import CompareOut, StrategyResult, TechnicalAnalysisOut
from app.services.analysis import crossover_signal, rsi, rsi_signal, sma, simulate, trend_signal

router = APIRouter(prefix="/analysis", tags=["analysis"])

SHORT_WINDOW = 20
LONG_WINDOW = 50
RSI_PERIOD = 14
TREND_WINDOW = 50


@router.get("/{symbol}", response_model=TechnicalAnalysisOut)
def technical_analysis(
    symbol: str,
    days: int = Query(120, ge=10, le=1000, description="Nombre de derniers jours renvoyés"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cours de clôture, deux moyennes mobiles et RSI d'un actif.

    Les indicateurs sont calculés sur tout l'historique, puis on ne garde que les
    `days` derniers jours : la moyenne longue est donc déjà définie dès le premier
    point affiché.
    """
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actif inconnu")
    rows = db.execute(
        select(
            PriceHistory.date,
            PriceHistory.open,
            PriceHistory.high,
            PriceHistory.low,
            PriceHistory.close,
            PriceHistory.volume,
        )
        .where(PriceHistory.asset_id == asset.id)
        .order_by(PriceHistory.date)
    ).all()
    if len(rows) < 2:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pas d'historique de cours")

    closes = [float(row.close) for row in rows]
    short, long_, strength = sma(closes, SHORT_WINDOW), sma(closes, LONG_WINDOW), rsi(closes, RSI_PERIOD)
    start = max(0, len(rows) - days)

    def cut(values: list) -> list:
        return [None if v is None else round(v, 4) for v in values[start:]]

    return TechnicalAnalysisOut(
        symbol=asset.symbol,
        name=asset.name,
        short_window=SHORT_WINDOW,
        long_window=LONG_WINDOW,
        rsi_period=RSI_PERIOD,
        dates=[row.date for row in rows[start:]],
        open=[round(float(row.open), 4) for row in rows[start:]],
        high=[round(float(row.high), 4) for row in rows[start:]],
        low=[round(float(row.low), 4) for row in rows[start:]],
        close=cut(closes),
        volume=[int(row.volume or 0) for row in rows[start:]],
        sma_short=cut(short),
        sma_long=cut(long_),
        rsi=cut(strength),
    )


@router.get("/{symbol}/compare", response_model=CompareOut)
def compare_strategies(
    symbol: str,
    short: int = Query(SHORT_WINDOW, ge=2, le=200, description="Moyenne mobile courte (jours)"),
    long: int = Query(LONG_WINDOW, ge=3, le=400, description="Moyenne mobile longue (jours)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare quatre stratégies sur tout l'historique de l'actif, avec le même départ."""
    if short >= long:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La moyenne courte doit être plus petite que la moyenne longue",
        )
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actif inconnu")
    rows = db.execute(
        select(PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.asset_id == asset.id)
        .order_by(PriceHistory.date)
    ).all()
    closes = [float(close) for _, close in rows]

    # Même premier jour pour toutes : quand la moyenne la plus longue existe.
    start = max(long, TREND_WINDOW, RSI_PERIOD + 1) - 1
    if len(closes) < start + 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Historique insuffisant pour cette moyenne longue",
        )

    definitions = [
        ("hold", "Acheter et garder", [True] * len(closes)),
        ("crossover", f"Croisement MM {short} / {long}", crossover_signal(closes, short, long)),
        ("trend", f"Tendance (cours > MM {TREND_WINDOW})", trend_signal(closes, TREND_WINDOW)),
        ("rsi", f"RSI ({RSI_PERIOD} j) : achat < 30, vente > 70", rsi_signal(closes, RSI_PERIOD)),
    ]
    strategies = []
    for key, label, signal in definitions:
        out = simulate(closes, signal, start)
        strategies.append(
            StrategyResult(
                key=key,
                label=label,
                curve=[round(v, 2) for v in out["curve"]],
                return_pct=round(out["return_pct"], 2),
                max_drawdown_pct=round(out["max_drawdown_pct"], 2),
                entries=out["entries"],
                time_in_market_pct=round(out["time_in_market_pct"], 1),
                return_to_risk=None if out["return_to_risk"] is None else round(out["return_to_risk"], 2),
            )
        )
    return CompareOut(
        symbol=asset.symbol,
        name=asset.name,
        short_window=short,
        long_window=long,
        trend_window=TREND_WINDOW,
        rsi_period=RSI_PERIOD,
        initial_capital=10000.0,
        dates=[day for day, _ in rows][start:],
        strategies=strategies,
    )
