"""Historique des calculs (table actuarial_runs) : paramètres, graine et résumé.

Le résumé reste petit (indicateurs clés) : les trajectoires ne sont jamais stockées,
elles se régénèrent à l'identique avec les mêmes paramètres et la même graine.
"""

from sqlalchemy.orm import Session

from app.actuarial.models import DATA_SOURCES, ActuarialRun
from app.models.models import User


def record_run(
    db: Session,
    user: User,
    model: str,
    params: dict,
    data_source: str,
    summary: dict,
    seed: int | None = None,
    portfolio_id: int | None = None,
) -> ActuarialRun:
    if data_source not in DATA_SOURCES:
        raise ValueError(f"Provenance inconnue : {data_source}")
    run = ActuarialRun(
        user_id=user.id,
        portfolio_id=portfolio_id,
        model=model,
        params=params,
        seed=seed,
        data_source=data_source,
        summary=summary,
    )
    db.add(run)
    db.commit()
    return run
