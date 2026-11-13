"""Lecture des données de marché (assets, price_history) pour les calculs actuariels.

Lecture seule : les cours sont importés par app.import_prices (Twelve Data).
Ce module ne crée aucun second système d'import.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.models import Asset, PriceHistory


@dataclass
class ReturnsMatrix:
    """Rendements simples quotidiens alignés sur les dates communes à tous les actifs.

    `values[t, i]` = rendement de l'actif `asset_ids[i]` à la date `dates[t]`.
    `excluded` : actifs écartés faute d'historique, avec la raison.
    """

    dates: list[date]
    asset_ids: list[int]
    values: np.ndarray
    excluded: dict[int, str] = field(default_factory=dict)


def closes_by_asset(db: Session, asset_ids: list[int]) -> dict[int, list[tuple[date, float]]]:
    """Cours de clôture de chaque actif, triés par date croissante."""
    if not asset_ids:
        return {}
    rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.asset_id.in_(asset_ids))
        .order_by(PriceHistory.asset_id, PriceHistory.date)
    ).all()
    closes: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for asset_id, day, close in rows:
        closes[asset_id].append((day, float(close)))
    return closes


def _simple_returns(series: list[tuple[date, float]]) -> dict[date, float]:
    """Rendement du jour = cours / cours précédent - 1 (cours précédent nul ignoré)."""
    return {
        day: close / previous - 1
        for (_, previous), (day, close) in zip(series, series[1:])
        if previous > 0
    }


def returns_matrix(db: Session, asset_ids: list[int], lookback: int | None = None) -> ReturnsMatrix:
    """Matrice T x N des rendements sur les dates communes, limitée aux `lookback` derniers jours.

    Données manquantes : un actif avec moins de deux cours est exclu ; seules les
    dates où tous les actifs restants ont un rendement sont conservées (aucune
    interpolation, aucun remplissage).
    """
    closes = closes_by_asset(db, asset_ids)
    excluded: dict[int, str] = {}
    per_asset: dict[int, dict[date, float]] = {}
    for asset_id in asset_ids:
        series = closes.get(asset_id, [])
        if len(series) < 2:
            excluded[asset_id] = "moins de deux cours enregistrés"
            continue
        per_asset[asset_id] = _simple_returns(series)

    kept = list(per_asset)
    if not kept:
        return ReturnsMatrix([], [], np.empty((0, 0)), excluded)

    common = sorted(set.intersection(*(set(r) for r in per_asset.values())))
    if lookback:
        common = common[-lookback:]
    values = np.array([[per_asset[a][day] for a in kept] for day in common], dtype=float)
    return ReturnsMatrix(common, kept, values.reshape(len(common), len(kept)), excluded)


def asset_history_summary(db: Session) -> list[dict]:
    """Actifs disponibles avec l'étendue de leur historique (pour les sélecteurs)."""
    rows = db.execute(
        select(
            Asset.id,
            Asset.symbol,
            Asset.name,
            Asset.asset_type,
            func.count(PriceHistory.id),
            func.min(PriceHistory.date),
            func.max(PriceHistory.date),
        )
        .outerjoin(PriceHistory, PriceHistory.asset_id == Asset.id)
        .group_by(Asset.id)
        .order_by(Asset.symbol)
    ).all()
    return [
        {
            "id": asset_id,
            "symbol": symbol,
            "name": name,
            "asset_type": asset_type.value,
            "observations": count,
            "first_date": first,
            "last_date": last,
        }
        for asset_id, symbol, name, asset_type, count, first, last in rows
    ]
