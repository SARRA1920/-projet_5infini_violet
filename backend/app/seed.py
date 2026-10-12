"""Données de départ, rejouables (idempotent).

Lancement : python -m app.seed
"""
from decimal import Decimal

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.models import (
    Asset,
    AssetType,
    Bank,
    BankType,
    Portfolio,
    User,
    UserRole,
)

# Mot de passe provisoire : NON hashé, donc inutilisable pour se connecter.
# À remplacer par un vrai hash une fois le module d'authentification en place.
PLACEHOLDER_PASSWORD = "PLACEHOLDER_NOT_A_REAL_HASH_CHANGE_ME"

ASSETS = [
    ("AAPL", "Apple Inc.", AssetType.STOCK),
    ("MSFT", "Microsoft Corporation", AssetType.STOCK),
    ("GOOGL", "Alphabet Inc.", AssetType.STOCK),
    ("AMZN", "Amazon.com, Inc.", AssetType.STOCK),
    ("TSLA", "Tesla, Inc.", AssetType.STOCK),
    ("NVDA", "NVIDIA Corporation", AssetType.STOCK),
    ("JPM", "JPMorgan Chase & Co.", AssetType.STOCK),
    ("EUR/USD", "Euro / Dollar américain", AssetType.FOREX),
    ("GBP/USD", "Livre sterling / Dollar américain", AssetType.FOREX),
    ("USD/JPY", "Dollar américain / Yen japonais", AssetType.FOREX),
    ("XAU/USD", "Or / Dollar américain", AssetType.COMMODITY),
    ("USO", "United States Oil Fund (ETF pétrole brut WTI)", AssetType.COMMODITY),
    ("TLT", "iShares 20+ Year Treasury Bond ETF", AssetType.BOND),
]

C, N = BankType.CONVENTIONAL, BankType.NON_CONVENTIONAL
# (nom, type, prêts, dépôts, capital, part immobilier, ratio de solvabilité) — en euros
BANKS = [
    ("Banque Atlas", C, "5000000000", "5800000000", "600000000", "0.35", "0.1200"),
    ("Banque Carthage", C, "3200000000", "3700000000", "330000000", "0.42", "0.1031"),
    ("Banque Medina", C, "1800000000", "2100000000", "160000000", "0.50", "0.0889"),
    ("Banque Safa", N, "2600000000", "3000000000", "340000000", "0.45", "0.1308"),
    ("Banque Amana", N, "1500000000", "1750000000", "190000000", "0.55", "0.1267"),
    ("Banque Nour", N, "900000000", "1050000000", "85000000", "0.38", "0.0944"),
]

USERS = [
    ("test@example.com", "testuser", UserRole.USER),
    ("admin@example.com", "admin", UserRole.ADMIN),
]


def main() -> None:
    created: list[str] = []
    skipped: list[str] = []

    with SessionLocal() as db:
        for symbol, name, asset_type in ASSETS:
            if db.scalar(select(Asset).where(Asset.symbol == symbol)):
                skipped.append(f"Asset {symbol}")
                continue
            db.add(Asset(symbol=symbol, name=name, asset_type=asset_type))
            created.append(f"Asset {symbol}")

        for name, bank_type, loans, deposits, equity, real_estate, ratio in BANKS:
            if db.scalar(select(Bank).where(Bank.name == name)):
                skipped.append(f"Bank {name}")
                continue
            db.add(
                Bank(
                    name=name,
                    bank_type=bank_type,
                    total_loans=Decimal(loans),
                    total_deposits=Decimal(deposits),
                    equity_capital=Decimal(equity),
                    real_estate_share=Decimal(real_estate),
                    capital_ratio=Decimal(ratio),
                )
            )
            created.append(f"Bank {name}")

        for email, username, role in USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user:
                skipped.append(f"User {email}")
            else:
                user = User(
                    email=email,
                    username=username,
                    hashed_password=PLACEHOLDER_PASSWORD,
                    role=role,
                )
                db.add(user)
                created.append(f"User {email}")

            # Portefeuille par défaut : créé seulement si l'utilisateur n'en a aucun.
            has_portfolio = user.id is not None and db.scalar(
                select(Portfolio.id).where(Portfolio.user_id == user.id).limit(1)
            )
            if has_portfolio:
                skipped.append(f"Portfolio de {email}")
            else:
                user.portfolios.append(Portfolio())
                created.append(f"Portfolio de {email}")

        db.commit()

    print(f"Créés ({len(created)}) :")
    for item in created:
        print(f"  + {item}")
    print(f"Ignorés, déjà existants ({len(skipped)}) :")
    for item in skipped:
        print(f"  = {item}")


if __name__ == "__main__":
    main()
