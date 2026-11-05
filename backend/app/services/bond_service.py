"""Simulates coupon (interest) payments for held bonds."""
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.models import Portfolio, Position, Asset, AssetType

ANNUAL_YIELD = Decimal("0.04")
DAILY_YIELD = ANNUAL_YIELD / Decimal("365")

def pay_daily_bond_coupons(db: Session | None = None) -> tuple[int, Decimal]:
    """Adds daily interest to portfolios holding bonds."""
    owns_session = db is None
    if owns_session:
        db = SessionLocal()
    try:
        bond_positions = db.execute(
            select(Position, Asset)
            .join(Asset, Position.asset_id == Asset.id)
            .where(Position.is_open == True, Asset.asset_type == AssetType.BOND)
        ).all()

        paid_count = 0
        total_paid = Decimal("0.00")

        for position, asset in bond_positions:
            invested_amount = position.quantity * position.average_buy_price
            daily_interest = (invested_amount * DAILY_YIELD).quantize(Decimal("0.01"))

            if daily_interest > 0:
                portfolio = db.scalar(
                    select(Portfolio).where(Portfolio.id == position.portfolio_id)
                )
                if portfolio:
                    portfolio.cash_balance += daily_interest
                    paid_count += 1
                    total_paid += daily_interest

        db.commit()
        print(f"Success! Interest paid to {paid_count} portfolios. Total: ${total_paid}")
        return paid_count, total_paid
    except Exception as e:
        db.rollback()
        print(f"Error paying coupons: {e}")
        return 0, Decimal("0.00")
    finally:
        if owns_session:
            db.close()