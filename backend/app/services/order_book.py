"""Vérification et exécution automatique du carnet d'ordre.

Appelé périodiquement par le planificateur (app.core.scheduler, APScheduler)
plutôt qu'à la demande d'un utilisateur : un stop-loss ou un ordre limite
doit se déclencher même si personne n'a l'application ouverte, exactement
comme en vraie bourse.

Chaque passage ouvre sa propre session (le scheduler ne partage pas de
session avec les requêtes HTTP) et committe ordre par ordre, pour qu'un
échec sur l'un n'annule pas les autres déjà traités.
"""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.models import PendingOrder, PendingOrderStatus, PendingOrderType, Position
from app.services.prices import PriceUnavailableError, get_current_price
from app.services.trading import InsufficientFundsError, InsufficientPositionError, TradingError, place_order

logger = logging.getLogger("order_book")


def _check_positions_stop_loss_take_profit(db: Session) -> int:
    """Clôture automatiquement les positions dont le cours a atteint leur seuil."""
    triggered = 0
    positions = db.scalars(
        select(Position).where(
            Position.is_open.is_(True),
            (Position.stop_loss.is_not(None)) | (Position.take_profit.is_not(None)),
        )
    ).all()
    for position in positions:
        try:
            price = get_current_price(db, position.asset.symbol)
        except PriceUnavailableError:
            continue

        hit_stop = position.stop_loss is not None and price <= position.stop_loss
        hit_target = position.take_profit is not None and price >= position.take_profit
        if not (hit_stop or hit_target):
            continue

        reason = "stop-loss" if hit_stop else "take-profit"
        try:
            place_order(
                db,
                position.portfolio_id,
                position.asset.symbol,
                "sell",
                position.quantity,
            )
            db.commit()
            triggered += 1
            logger.info(
                "Position %s (portefeuille %s) clôturée automatiquement (%s) à %s",
                position.asset.symbol, position.portfolio_id, reason, price,
            )
        except (TradingError, InsufficientFundsError, InsufficientPositionError) as exc:
            db.rollback()
            logger.warning(
                "Échec du déclenchement %s sur %s (portefeuille %s) : %s",
                reason, position.asset.symbol, position.portfolio_id, exc,
            )
    return triggered


def _check_pending_limit_orders(db: Session) -> int:
    """Exécute les ordres à cours limité dont la condition de prix est atteinte."""
    triggered = 0
    orders = db.scalars(
        select(PendingOrder).where(
            PendingOrder.status == PendingOrderStatus.PENDING,
            PendingOrder.order_type == PendingOrderType.LIMIT,
        )
    ).all()
    for order in orders:
        try:
            price = get_current_price(db, order.asset.symbol)
        except PriceUnavailableError:
            continue

        side = order.side.value if hasattr(order.side, "value") else order.side
        if side == "buy" and price > order.trigger_price:
            continue
        if side == "sell" and price < order.trigger_price:
            continue

        try:
            transaction = place_order(
                db,
                order.portfolio_id,
                order.asset.symbol,
                side,
                order.quantity,
            )
            order.status = PendingOrderStatus.EXECUTED
            order.executed_at = transaction.executed_at
            order.transaction_id = transaction.id
            db.commit()
            triggered += 1
            logger.info(
                "Ordre limite #%s (%s %s, %s) exécuté à %s",
                order.id, side, order.asset.symbol, order.quantity, price,
            )
        except (TradingError, InsufficientFundsError, InsufficientPositionError) as exc:
            # Fonds insuffisants au moment du déclenchement (le cash a pu être
            # dépensé ailleurs depuis la création de l'ordre) : on annule
            # plutôt que de réessayer indéfiniment à chaque passage.
            db.rollback()
            order.status = PendingOrderStatus.CANCELLED
            order.note = str(exc)
            db.commit()
            logger.warning("Ordre limite #%s annulé (%s)", order.id, exc)
    return triggered


def run_order_book_check() -> None:
    """Point d'entrée appelé par le planificateur : une passe complète du carnet."""
    db = SessionLocal()
    try:
        n_sl_tp = _check_positions_stop_loss_take_profit(db)
        n_limit = _check_pending_limit_orders(db)
        if n_sl_tp or n_limit:
            logger.info(
                "Carnet d'ordre : %s stop-loss/take-profit, %s ordre(s) limite déclenché(s)",
                n_sl_tp, n_limit,
            )
    finally:
        db.close()
