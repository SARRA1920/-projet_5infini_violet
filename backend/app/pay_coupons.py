"""Lance le paiement des coupons obligataires (un versement par position et par jour).

Lancement : python -m app.pay_coupons
"""
from app.services.bond_service import pay_daily_bond_coupons

if __name__ == "__main__":
    count, total = pay_daily_bond_coupons()
    print(f"Coupons versés à {count} position(s) ; total : {total} USD")
