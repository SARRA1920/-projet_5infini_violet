"""Simule le paiement des coupons (intérêts) pour les obligations détenues."""
from decimal import Decimal
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.models import Portfolio, Position, Asset, AssetType

# Simulation d'un rendement annuel de 4% sur les obligations.
# 4% divisé par 365 jours = 0.01095% par jour.
ANNUAL_YIELD = Decimal("0.04")
DAILY_YIELD = ANNUAL_YIELD / Decimal("365")

def pay_daily_bond_coupons():
    """Ajoute des intérêts quotidiens aux portefeuilles contenant des obligations."""
    db = SessionLocal()
    try:
        # 1. Trouver toutes les positions ouvertes sur des obligations
        bond_positions = db.execute(
            select(Position, Asset)
            .join(Asset, Position.asset_id == Asset.id)
            .where(Position.is_open == True, Asset.asset_type == AssetType.BOND)
        ).all()

        paid_count = 0
        total_paid = Decimal("0.00")

        for position, asset in bond_positions:
            # 2. Calculer l'intérêt quotidien (Valeur investie * taux quotidien)
            invested_amount = position.quantity * position.average_buy_price
            daily_interest = (invested_amount * DAILY_YIELD).quantize(Decimal("0.01"))

            if daily_interest > 0:
                # 3. Ajouter le cash au portefeuille de l'utilisateur
                portfolio = db.scalar(select(Portfolio).where(Portfolio.id == position.portfolio_id))
                if portfolio:
                    portfolio.cash_balance += daily_interest
                    paid_count += 1
                    total_paid += daily_interest

        db.commit()
        print(f"Succès ! Intérêts des obligations versés à {paid_count} portefeuilles. Total payé : ${total_paid}")
    except Exception as e:
        db.rollback()
        print(f"Erreur lors du paiement des coupons : {e}")
    finally:
        db.close()