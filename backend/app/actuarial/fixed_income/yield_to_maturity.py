"""Rendement actuariel (Yield to Maturity) : taux y tel que prix plein(y) = prix observé.

Résolution par la méthode de Brent sur [-50 %, 200 %] : le prix est strictement
décroissant en y pour des flux positifs, la solution est donc unique si elle existe.
"""

from datetime import date

from scipy.optimize import brentq

from app.actuarial.fixed_income.bond_pricing import dirty_price_from_flows
from app.actuarial.fixed_income.cashflows import Bond, accrued_interest, cash_flows

LOWER, UPPER = -0.5, 2.0


def yield_to_maturity(bond: Bond, settlement: date, clean_price: float) -> float:
    if clean_price <= 0:
        raise ValueError("Le prix doit être strictement positif")
    flows = cash_flows(bond, settlement)
    target = clean_price + accrued_interest(bond, settlement)

    def gap(y: float) -> float:
        return dirty_price_from_flows(flows, y, bond.frequency) - target

    if gap(LOWER) * gap(UPPER) > 0:
        raise ValueError("Aucun rendement entre -50 % et 200 % ne reproduit ce prix")
    return float(brentq(gap, LOWER, UPPER, xtol=1e-12))
