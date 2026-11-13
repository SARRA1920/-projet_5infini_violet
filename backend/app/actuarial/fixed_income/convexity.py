"""Convexité d'une obligation (composition périodique).

C = Σ CF_i t_i (t_i + 1/f) DF_i / (P (1 + y/f)²)
Approximation du second ordre : ΔP/P ≈ -D_mod Δy + ½ C Δy².
"""

from app.actuarial.fixed_income.bond_pricing import discount_factor
from app.actuarial.fixed_income.cashflows import CashFlow


def convexity(flows: list[CashFlow], y: float, frequency: int) -> float:
    total = 0.0
    weighted = 0.0
    for cf in flows:
        pv = cf.amount * discount_factor(y, frequency, cf.time)
        total += pv
        weighted += pv * cf.time * (cf.time + 1 / frequency)
    return weighted / (total * (1 + y / frequency) ** 2)
