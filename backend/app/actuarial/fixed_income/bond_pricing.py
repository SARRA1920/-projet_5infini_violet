"""Valeur actuelle d'une obligation à partir d'un rendement actuariel ou d'une courbe."""

from datetime import date

import numpy as np

from app.actuarial.fixed_income.cashflows import Bond, CashFlow, accrued_interest, cash_flows


def discount_factor(y: float, frequency: int, t: float) -> float:
    """DF = (1 + y/f)^(-f t). Exige 1 + y/f > 0."""
    base = 1 + y / frequency
    if base <= 0:
        raise ValueError("Rendement trop négatif pour la fréquence de capitalisation")
    return base ** (-frequency * t)


def dirty_price_from_flows(flows: list[CashFlow], y: float, frequency: int) -> float:
    return sum(cf.amount * discount_factor(y, frequency, cf.time) for cf in flows)


def price(bond: Bond, settlement: date, y: float) -> dict:
    """Prix plein, coupon couru et prix pied de coupon pour un rendement y."""
    flows = cash_flows(bond, settlement)
    dirty = dirty_price_from_flows(flows, y, bond.frequency)
    accrued = accrued_interest(bond, settlement)
    return {"dirty": dirty, "accrued": accrued, "clean": dirty - accrued}


def price_on_curve(flows: list[CashFlow], frequency: int, rate_at) -> float:
    """Prix plein en actualisant chaque flux à son propre taux rate_at(t) (même composition)."""
    return sum(cf.amount * discount_factor(float(rate_at(cf.time)), frequency, cf.time) for cf in flows)


def flows_table(flows: list[CashFlow], y: float, frequency: int) -> list[dict]:
    rows = []
    for cf in flows:
        df = discount_factor(y, frequency, cf.time)
        rows.append(
            {
                "date": cf.date,
                "time": cf.time,
                "coupon": cf.coupon,
                "principal": cf.principal,
                "amount": cf.amount,
                "discount_factor": df,
                "present_value": cf.amount * df,
            }
        )
    return rows


def price_yield_curve(flows: list[CashFlow], frequency: int, y: float, span: float = 0.03, points: int = 41) -> list[dict]:
    """Prix plein pour des rendements de y - span à y + span (courbe prix-rendement)."""
    low = max(y - span, -frequency * 0.99 + 1e-6)
    return [
        {"yield": float(rate), "price": dirty_price_from_flows(flows, float(rate), frequency)}
        for rate in np.linspace(low, y + span, points)
    ]
