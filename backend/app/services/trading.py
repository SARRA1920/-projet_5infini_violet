"""Exécution d'un ordre au marché sur un portefeuille virtuel.

Le service ne fait jamais de commit : l'appelant valide (commit) ou annule
(rollback) la transaction.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Asset, Portfolio, Position, Transaction, TransactionSide
from app.services.prices import get_current_price

CASH_STEP = Decimal("0.01")
PRICE_STEP = Decimal("0.0001")
QUANTITY_STEP = Decimal("0.000001")  # Numeric(18, 6) en base


class TradingError(Exception):
    """Base commune des erreurs d'ordre."""


class InvalidOrderError(TradingError):
    """Ordre mal formé : sens, quantité, stop loss ou take profit incohérents."""


class PortfolioNotFoundError(TradingError):
    """Portefeuille inexistant."""


class InsufficientFundsError(TradingError):
    """Cash insuffisant pour couvrir l'achat."""


class InsufficientPositionError(TradingError):
    """Quantité détenue insuffisante pour la vente (pas de vente à découvert)."""


def _round(value: Decimal, step: Decimal) -> Decimal:
    return value.quantize(step, rounding=ROUND_HALF_UP)


def _check_decimal(name: str, value: object) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise InvalidOrderError(f"{name} doit être un Decimal fini")


def place_order(
    db: Session,
    portfolio_id: int,
    symbol: str,
    side: TransactionSide,
    quantity: Decimal,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
) -> Transaction:
    """Exécute un ordre au prix courant et renvoie la Transaction créée."""
    # 1. Validations sans accès à la base
    try:
        side = TransactionSide(side)
    except ValueError:
        raise InvalidOrderError(f"Sens d'ordre inconnu : {side}") from None
    _check_decimal("quantity", quantity)
    if quantity <= 0:
        raise InvalidOrderError("La quantité doit être strictement positive")
    if quantity != _round(quantity, QUANTITY_STEP):
        raise InvalidOrderError("La quantité est limitée à 6 décimales")
    if side == TransactionSide.SELL and (stop_loss is not None or take_profit is not None):
        raise InvalidOrderError("Stop loss et take profit ne sont acceptés que sur un achat")
    for name, value in (("stop_loss", stop_loss), ("take_profit", take_profit)):
        if value is not None:
            _check_decimal(name, value)

    # 2. Prix d'exécution (lève PriceUnavailableError si symbole inconnu / sans cours)
    price = _round(get_current_price(db, symbol), PRICE_STEP)
    if side == TransactionSide.BUY:
        if stop_loss is not None and not stop_loss < price:
            raise InvalidOrderError(f"Le stop loss doit être inférieur au prix ({price})")
        if take_profit is not None and not price < take_profit:
            raise InvalidOrderError(f"Le take profit doit être supérieur au prix ({price})")

    # 3. Verrou du portefeuille avant toute lecture du cash
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
    )
    if portfolio is None:
        raise PortfolioNotFoundError(f"Portefeuille introuvable : {portfolio_id}")
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    position = db.scalar(
        select(Position).where(
            Position.portfolio_id == portfolio.id, Position.asset_id == asset.id
        )
    )
    amount = _round(quantity * price, CASH_STEP)
    realized_pnl: Decimal | None = None  # rempli seulement pour une vente

    # 4. Contrôles métier, puis seulement ensuite les modifications
    if side == TransactionSide.BUY:
        if portfolio.cash_balance < amount:
            raise InsufficientFundsError(
                f"Cash insuffisant : {portfolio.cash_balance} disponible, {amount} requis"
            )
        portfolio.cash_balance -= amount
        if position is None:
            position = Position(
                portfolio_id=portfolio.id,
                asset_id=asset.id,
                quantity=quantity,
                average_buy_price=price,
                is_open=True,
            )
            db.add(position)
        else:
            new_quantity = position.quantity + quantity
            position.average_buy_price = _round(
                (position.quantity * position.average_buy_price + quantity * price)
                / new_quantity,
                PRICE_STEP,
            )
            position.quantity = new_quantity
            if not position.is_open:
                position.is_open = True
                position.opened_at = func.now()
                position.closed_at = None
    else:
        if position is None or not position.is_open or quantity > position.quantity:
            held = position.quantity if position is not None and position.is_open else 0
            raise InsufficientPositionError(
                f"Position insuffisante sur {asset.symbol} : {held} détenu, {quantity} demandé"
            )
        portfolio.cash_balance += amount
        # Gain ou perte réalisé = (prix de vente - prix moyen d'achat) x quantité
        realized_pnl = _round((price - position.average_buy_price) * quantity, CASH_STEP)
        position.quantity -= quantity
        if position.quantity == 0:
            position.is_open = False
            position.closed_at = func.now()

    transaction = Transaction(
        portfolio_id=portfolio.id,
        asset_id=asset.id,
        side=side,
        quantity=quantity,
        price=price,
        stop_loss=_round(stop_loss, PRICE_STEP) if stop_loss is not None else None,
        take_profit=_round(take_profit, PRICE_STEP) if take_profit is not None else None,
        realized_pnl=realized_pnl,
    )
    db.add(transaction)
    db.flush()  # attribue transaction.id ; rien n'est validé tant que l'appelant ne commit pas
    return transaction
