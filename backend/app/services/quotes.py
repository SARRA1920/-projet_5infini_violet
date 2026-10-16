"""Lit les derniers cours importés par le module Twelve Data (price_history).

Le code de feature/real-market-data n'est pas modifié : on lit seulement sa table.
"""

from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.models import Asset, AssetType, PriceHistory


def _french_number(value: Decimal, digits: int) -> str:
    text = f"{float(value):,.{digits}f}"
    return text.replace(",", " ").replace(".", ",")


def _spark(closes: list[Decimal]) -> list[float]:
    if len(closes) < 2:
        return [16.0, 16.0]
    low, high = min(closes), max(closes)
    span = float(high - low) or 1
    return [round(24 - (float(price - low) / span) * 18, 2) for price in closes]


def _row(asset: Asset, history: list[PriceHistory]) -> dict:
    latest = history[-1]
    previous = history[-2] if len(history) > 1 else latest
    change = (
        (latest.close - previous.close) / previous.close * 100
        if previous.close
        else Decimal("0")
    )
    digits = 4 if asset.asset_type == AssetType.FOREX else 2
    currency = "" if asset.asset_type == AssetType.FOREX else "USD"
    group = {
        AssetType.STOCK: "actions",
        AssetType.FOREX: "devises",
        AssetType.COMMODITY: "matieres",
        AssetType.BOND: "obligations",
    }[asset.asset_type]
    sign = "+" if change >= 0 else ""
    last = _french_number(latest.close, digits)
    if currency:
        last = f"{last} {currency}"
    return {
        "symbol": asset.symbol,
        "name": asset.name,
        "last": last,
        "change": f"{sign}{_french_number(change, 2)} %",
        "high": _french_number(latest.high, digits),
        "low": _french_number(latest.low, digits),
        "volume": str(latest.volume) if latest.volume else "—",
        "up": change >= 0,
        "group": group,
        "spark": _spark([row.close for row in history]),
        "live": True,
    }


def live_quotes() -> list[dict]:
    """Dernier cours connu de chaque actif présent dans price_history."""
    db = SessionLocal()
    try:
        assets = db.scalars(select(Asset).order_by(Asset.symbol)).all()
        rows = []
        for asset in assets:
            history = list(
                reversed(
                    db.scalars(
                        select(PriceHistory)
                        .where(PriceHistory.asset_id == asset.id)
                        .order_by(PriceHistory.date.desc())
                        .limit(7)
                    ).all()
                )
            )
            if history:
                rows.append(_row(asset, history))
        return rows
    finally:
        db.close()
