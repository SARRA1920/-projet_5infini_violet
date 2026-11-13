"""Chocs de solvabilité sur les banques synthétiques.

Le calcul ne modifie pas la base : les fonds propres absorbent la perte,
puis le ratio est recalculé. Seuil de référence : 8 %.
"""
from decimal import ROUND_HALF_UP, Decimal

from app.models.models import Bank

MONEY = Decimal("0.01")
RATIO = Decimal("0.01")
# 8 % de fonds propres rapportés aux prêts.
CAPITAL_THRESHOLD = Decimal("0.08")


class UnknownShockError(ValueError):
    """Type de choc inconnu."""


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _points(ratio: Decimal) -> Decimal:
    """Fraction -> points de pourcentage (0.0889 -> 8.89)."""
    return (ratio * 100).quantize(RATIO, rounding=ROUND_HALF_UP)


def loss_amount(bank: Bank, shock: str, intensity_pct: Decimal) -> Decimal:
    """Perte absorbée par les fonds propres.

    Crédit : une part des prêts fait défaut.
    Immobilier : la part immobilière des prêts perd de la valeur.
    `intensity_pct` est un pourcentage (10 pour 10 %).
    """
    rate = intensity_pct / Decimal("100")
    if shock == "credit":
        return _money(bank.total_loans * rate)
    if shock == "real_estate":
        return _money(bank.total_loans * bank.real_estate_share * rate)
    raise UnknownShockError(f"Choc inconnu : {shock}")


def apply_shock(bank: Bank, shock: str, intensity_pct: Decimal) -> dict:
    """Résultat du choc pour une banque. `ratio_*` est en points de pourcentage."""
    loss = loss_amount(bank, shock, intensity_pct)
    equity_after = _money(bank.equity_capital - loss)
    ratio_after = equity_after / bank.total_loans if bank.total_loans else None
    return {
        "name": bank.name,
        "bank_type": bank.bank_type.value,
        "loss": loss,
        "equity_before": bank.equity_capital,
        "equity_after": equity_after,
        "ratio_before": _points(bank.capital_ratio),
        "ratio_after": None if ratio_after is None else _points(ratio_after),
        "below_threshold": ratio_after is not None and ratio_after < CAPITAL_THRESHOLD,
    }
