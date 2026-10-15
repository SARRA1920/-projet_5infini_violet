"""Lance le paiement des coupons obligataires."""
from app.services.bond_service import pay_daily_bond_coupons

if __name__ == "__main__":
    pay_daily_bond_coupons()