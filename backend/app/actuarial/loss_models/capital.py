"""Mesures de risque de la perte agrégée et capital économique.

VaR_α(S)  : quantile d'ordre α de S (mêmes conventions que risk/var.py) ;
TVaR_α(S) : moyenne de S au-delà de VaR_α (Expected Shortfall) ;
capital économique = VaR_α(S) - E[S] (perte inattendue : la perte attendue est
supposée couverte par les primes ou les provisions). Variante TVaR_α(S) - E[S].
Référence : 99,5 % à un an (convention Solvabilité II).
"""

import numpy as np

from app.actuarial.risk.expected_shortfall import tail_mean
from app.actuarial.risk.var import loss_quantile

LEVELS = (0.95, 0.99, 0.995, 0.999)
REFERENCE_LEVEL = 0.995


def risk_measures(aggregate: np.ndarray, levels=LEVELS) -> list[dict]:
    aggregate = np.asarray(aggregate, dtype=float)
    expected = float(aggregate.mean())
    rows = []
    for level in levels:
        var = loss_quantile(aggregate, level)
        tvar = tail_mean(aggregate, level)
        rows.append(
            {
                "confidence": level,
                "var": var,
                "tvar": tvar,
                "capital_var": var - expected,
                "capital_tvar": tvar - expected,
            }
        )
    return rows
