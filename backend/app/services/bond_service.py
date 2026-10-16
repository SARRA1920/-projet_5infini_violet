"""Simule le paiement quotidien des coupons (intérêts) sur les obligations détenues.

Règles :
- rendement annuel simulé de 4 %, versé chaque jour sur la somme investie
  (quantité x prix moyen d'achat) ;
- un seul versement par position et par jour : la contrainte unique de coupon_payments
  l'impose, donc relancer le script le même jour ne paie rien de plus ;
- le portefeuille est verrouillé avant de toucher au cash (comme place_order), pour qu'un
  achat simultané ne puisse pas écraser les intérêts ;
- chaque versement est enregistré dans coupon_payments (date et montant).
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.models import Asset, AssetType, CouponPayment, Portfolio, Position

ANNUAL_YIELD = Decimal("0.04")
DAILY_YIELD = ANNUAL_YIELD / Decimal("365")
CASH_STEP = Decimal("0.01")


def pay_daily_bond_coupons(today: date | None = None) -> tuple[int, Decimal]:
    """Verse les coupons du jour. Retourne (nombre de positions payées, total versé)."""
    today = today or datetime.now(timezone.utc).date()
    paid_count = 0
    total_paid = Decimal("0.00")

    with SessionLocal() as db:
        candidates = db.execute(
            select(Position.id, Position.portfolio_id)
            .join(Asset, Position.asset_id == Asset.id)
            .where(Position.is_open.is_(True), Asset.asset_type == AssetType.BOND)
            .order_by(Position.portfolio_id, Position.id)
        ).all()

        for position_id, portfolio_id in candidates:
            try:
                # Verrou du portefeuille avant de relire la position et le cash.
                portfolio = db.scalar(
                    select(Portfolio).where(Portfolio.id == portfolio_id).with_for_update()
                )
                position = db.get(Position, position_id)
                if portfolio is None or position is None or not position.is_open:
                    db.rollback()
                    continue

                already_paid = db.scalar(
                    select(CouponPayment.id).where(
                        CouponPayment.position_id == position_id,
                        CouponPayment.paid_on == today,
                    )
                )
                if already_paid is not None:
                    db.rollback()
                    continue

                invested = position.quantity * position.average_buy_price
                interest = (invested * DAILY_YIELD).quantize(CASH_STEP)
                if interest <= 0:
                    db.rollback()
                    continue

                portfolio.cash_balance += interest
                db.add(
                    CouponPayment(
                        portfolio_id=portfolio_id,
                        position_id=position_id,
                        paid_on=today,
                        amount=interest,
                    )
                )
                db.commit()  # libère le verrou
            except IntegrityError:
                # Un autre lancement a payé cette position entre-temps : rien à faire.
                db.rollback()
                continue
            except Exception:
                db.rollback()
                raise

            paid_count += 1
            total_paid += interest

    return paid_count, total_paid
