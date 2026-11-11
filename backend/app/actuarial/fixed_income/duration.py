"""Duration de Macaulay, duration modifiée et DV01.

Macaulay : D = Σ t_i CF_i DF_i / P (moyenne des échéances pondérée par la valeur actuelle).
Modifiée : D_mod = D / (1 + y/f), d'où ΔP/P ≈ -D_mod Δy.
DV01 : variation de prix pour +1 point de base, D_mod x P x 0,0001.
"""

from app.actuarial.fixed_income.bond_pricing import discount_factor
from app.actuarial.fixed_income.cashflows import CashFlow


def macaulay_duration(flows: list[CashFlow], y: float, frequency: int) -> float:
    weighted = 0.0
    total = 0.0
    for cf in flows:
        pv = cf.amount * discount_factor(y, frequency, cf.time)
        weighted += cf.time * pv
        total += pv
    return weighted / total


def modified_duration(flows: list[CashFlow], y: float, frequency: int) -> float:
    return macaulay_duration(flows, y, frequency) / (1 + y / frequency)


def dv01(flows: list[CashFlow], y: float, frequency: int, dirty_price: float) -> float:
    return modified_duration(flows, y, frequency) * dirty_price * 1e-4
