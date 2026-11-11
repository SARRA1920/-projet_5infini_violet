"""Chocs de taux : déplacements parallèles et déformations de la courbe.

Courbe de départ : une courbe fournie (maturités, taux) ou, à défaut, une courbe
plate au rendement actuariel de l'obligation (hypothèse affichée comme telle).

Profils de choc s(t) pour une amplitude Δ (en fraction : 0.01 = 100 pb) :
- parallèle      : s(t) = Δ ;
- pentification  : s(t) = Δ x clip((t - 5) / 5, -1, 1)  (court terme -Δ, long terme +Δ, pivot 5 ans) ;
- aplatissement  : opposé de la pentification ;
- papillon       : +Δ hors de [2 ans, 10 ans], -Δ entre les deux.

Chaque scénario est réévalué intégralement ; pour le parallèle, on donne aussi
l'approximation duration + convexité pour mesurer l'erreur du développement limité.
"""

import numpy as np

from app.actuarial.fixed_income.bond_pricing import dirty_price_from_flows, price_on_curve
from app.actuarial.fixed_income.cashflows import CashFlow

PIVOT_YEARS = 5.0
BELLY = (2.0, 10.0)
DEFAULT_PARALLEL_BP = (-200, -100, -50, -25, 25, 50, 100, 200)


def shock_profile(kind: str, delta: float, t):
    t = np.asarray(t, dtype=float)
    if kind == "parallel":
        return np.full_like(t, delta)
    if kind == "steepening":
        return delta * np.clip((t - PIVOT_YEARS) / PIVOT_YEARS, -1, 1)
    if kind == "flattening":
        return -delta * np.clip((t - PIVOT_YEARS) / PIVOT_YEARS, -1, 1)
    if kind == "butterfly":
        return np.where((t >= BELLY[0]) & (t <= BELLY[1]), -delta, delta)
    raise ValueError(f"Choc inconnu : {kind}")


def parallel_sensitivity(
    flows: list[CashFlow], y: float, frequency: int, modified: float, convexity: float, shifts_bp=DEFAULT_PARALLEL_BP
) -> list[dict]:
    base = dirty_price_from_flows(flows, y, frequency)
    rows = []
    for bp in shifts_bp:
        dy = bp / 10_000
        full = dirty_price_from_flows(flows, y + dy, frequency)
        duration_only = base * (1 - modified * dy)
        second_order = base * (1 - modified * dy + 0.5 * convexity * dy**2)
        rows.append(
            {
                "shift_bp": bp,
                "price": full,
                "change_pct": full / base - 1,
                "duration_approx": duration_only,
                "duration_convexity_approx": second_order,
                "approx_error": second_order - full,
            }
        )
    return rows


def curve_scenarios(flows: list[CashFlow], frequency: int, curve_rate, amplitude_bp: float = 100) -> list[dict]:
    """Prix plein sous chaque déformation de la courbe `curve_rate(t)`."""
    base = price_on_curve(flows, frequency, curve_rate)
    delta = amplitude_bp / 10_000
    rows = [{"scenario": "base", "price": base, "change_pct": 0.0}]
    for kind in ("parallel", "steepening", "flattening", "butterfly"):
        for sign in (1, -1):
            shocked = price_on_curve(flows, frequency, lambda t, k=kind, d=sign * delta: curve_rate(t) + shock_profile(k, d, t))
            rows.append({"scenario": f"{kind}{'+' if sign > 0 else '-'}", "price": shocked, "change_pct": shocked / base - 1})
    return rows
