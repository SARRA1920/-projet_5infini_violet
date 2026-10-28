from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, PriceHistory, User
from app.schemas.analysis import TechnicalAnalysisOut
from app.services.analysis import rsi, sma

router = APIRouter(prefix="/analysis", tags=["analysis"])

SHORT_WINDOW = 20
LONG_WINDOW = 50
RSI_PERIOD = 14


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
