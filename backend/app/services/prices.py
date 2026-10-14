"""Prix courant d'un actif : dernier close connu dans price_history."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset, PriceHistory


class PriceUnavailableError(LookupError):
    """Symbole inconnu ou sans aucun cours enregistré."""


def get_current_price(db: Session, symbol: str) -> Decimal:
    """Renvoie le close le plus récent de price_history pour ce symbole.

    La session est fournie par l'appelant, qui gère son cycle de vie.
    """
    symbol = symbol.strip().upper()
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None:
        raise PriceUnavailableError(f"Symbole inconnu : {symbol}")
    close = db.scalar(
        select(PriceHistory.close)
        .where(PriceHistory.asset_id == asset.id)
        .order_by(PriceHistory.date.desc())
        .limit(1)
    )
    if close is None:
        raise PriceUnavailableError(f"Aucun cours enregistré pour {symbol}")
    return close
