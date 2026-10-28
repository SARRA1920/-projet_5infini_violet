"""Indicateurs de risque d'un portefeuille (simulation historique).

Principe : on garde les proportions ACTUELLES du portefeuille et on les applique
à l'historique des prix. Cela répond à la question « si je détenais ce portefeuille
depuis un an, comment aurait-il évolué ? ». Les calculs statistiques utilisent des
float ; les montants en argent restent des Decimal ailleurs dans l'application.
"""

import math
import statistics
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset, Portfolio, Position, PriceHistory
from app.services.prices import PriceUnavailableError, get_current_price

TRADING_DAYS_PER_YEAR = 252
INITIAL_CASH = Decimal("100000.00")  # capital de départ d'un portefeuille (voir Portfolio.cash_balance)

# Seuils des avertissements avant un ordre (modifiables ici, à un seul endroit).
# Un avertissement n'empêche pas l'ordre : il informe l'utilisateur.
MAX_SINGLE_ASSET_WEIGHT = Decimal("0.30")  # 30 % du portefeuille sur un seul actif
MIN_CASH_WEIGHT = Decimal("0.05")  # 5 % du portefeuille gardés en liquidités


def _closes_by_asset(db: Session, asset_ids: list[int]) -> dict[int, list[tuple[date, float]]]:
    """Cours de clôture de chaque actif, triés par date."""
    rows = db.execute(
        select(PriceHistory.asset_id, PriceHistory.date, PriceHistory.close)
        .where(PriceHistory.asset_id.in_(asset_ids))
        .order_by(PriceHistory.asset_id, PriceHistory.date)
    ).all()
    closes: dict[int, list[tuple[date, float]]] = defaultdict(list)
    for asset_id, day, close in rows:
        closes[asset_id].append((day, float(close)))
    return closes


def _daily_returns(series: list[tuple[date, float]]) -> dict[date, float]:
    """Rendement d'un jour = cours du jour / cours précédent - 1."""
    return {
        day: close / previous - 1
        for (_, previous), (day, close) in zip(series, series[1:])
        if previous
    }


def portfolio_daily_returns(db: Session, portfolio_id: int) -> list[tuple[date, float]]:
    """Rendement quotidien du portefeuille actuel, jour par jour, du plus ancien au plus récent.

    Rendement du jour = somme des (part de chaque actif x rendement de cet actif).
    Le cash ne bouge pas (rendement 0). Une position sans cours, ou avec moins de
    deux cours, est traitée comme du cash. On ne garde que les jours où tous les
    actifs détenus ont un rendement.
    """
    portfolio = db.get(Portfolio, portfolio_id)
    if portfolio is None:
        return []

    rows = db.execute(
        select(Position, Asset)
        .join(Asset, Position.asset_id == Asset.id)
        .where(Position.portfolio_id == portfolio_id, Position.is_open.is_(True))
    ).all()

    # Valeur de marché de chaque position ouverte (aujourd'hui)
    values: dict[int, float] = {}
    for position, asset in rows:
        try:
            price = get_current_price(db, asset.symbol)
        except PriceUnavailableError:
            continue
        values[asset.id] = float(position.quantity * price)
    if not values:
        return []

    total = float(portfolio.cash_balance) + sum(values.values())
    weights = {asset_id: value / total for asset_id, value in values.items()}

    closes = _closes_by_asset(db, list(weights))
    returns = {
        asset_id: _daily_returns(closes[asset_id])
        for asset_id in weights
        if len(closes.get(asset_id, [])) >= 2
    }
    if not returns:
        return []

    common_days = set.intersection(*(set(r) for r in returns.values()))
    return [
        (day, sum(weights[asset_id] * returns[asset_id][day] for asset_id in returns))
        for day in sorted(common_days)
    ]


def annualized_volatility(returns: list[float]) -> float | None:
    """Volatilité annualisée = écart-type des rendements quotidiens x racine de 252.

    Renvoie une fraction (0.159 pour 15,9 %), ou None s'il y a moins de 2 rendements.
    """
    if len(returns) < 2:
        return None
    return statistics.stdev(returns) * math.sqrt(TRADING_DAYS_PER_YEAR)


def historical_var(returns: list[float], confidence: float = 0.95) -> float | None:
    """VaR historique sur 1 jour : la perte dépassée seulement (1 - confidence) du temps.

    On trie les rendements du pire au meilleur et on lit celui qui se trouve à la
    frontière des (1 - confidence) pires jours. Renvoie une perte positive en
    fraction (0.02 pour 2 %), ou 0.0 si ce jour-là n'est pas une perte.
    Renvoie None s'il n'y a pas assez de rendements pour la lire.
    """
    if not returns or not 0 < confidence < 1:
        return None
    ordered = sorted(returns)
    index = int((1 - confidence) * len(ordered))
    return max(0.0, -ordered[index])


def max_drawdown(returns: list[float]) -> float | None:
    """Drawdown maximal : la plus grande chute entre un sommet et le creux qui suit.

    On reconstruit une courbe de valeur (départ = 1) à partir des rendements
    quotidiens. Renvoie une fraction positive (0.10 pour -10 %), ou None sans données.
    """
    if not returns:
        return None
    value = 1.0
    peak = 1.0
    worst = 0.0
    for daily in returns:
        value *= 1 + daily
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    return worst


def _fr(value: Decimal) -> str:
    """Pourcentage avec une décimale et la virgule française (40.9 -> '40,9')."""
    return f"{value:.1f}".replace(".", ",")


def order_warnings(
    is_buy: bool,
    amount: Decimal,
    cash: Decimal,
    total_value: Decimal,
    asset_value_before: Decimal,
) -> tuple[Decimal, Decimal, list[str]]:
    """Simule un ordre sans l'exécuter.

    Renvoie (poids de l'actif après l'ordre, poids du cash après l'ordre, avertissements),
    les poids étant des fractions du portefeuille (0.30 = 30 %). La valeur totale ne change
    pas : un achat transforme du cash en actions, une vente fait l'inverse.
    """
    if is_buy:
        cash_after = cash - amount
        asset_after = asset_value_before + amount
    else:
        cash_after = cash + amount
        asset_after = asset_value_before - amount
    if total_value <= 0:
        return Decimal("0"), Decimal("0"), []
    asset_weight = asset_after / total_value
    cash_weight = cash_after / total_value

    warnings: list[str] = []
    if is_buy and cash_after < 0:
        warnings.append("Cash insuffisant : l'ordre sera refusé.")
    elif is_buy and cash_weight < MIN_CASH_WEIGHT:
        warnings.append(
            f"Il ne vous resterait que {_fr(cash_weight * 100)} % de liquidités "
            f"(minimum conseillé : {MIN_CASH_WEIGHT * 100:.0f} %)."
        )
    if is_buy and asset_weight > MAX_SINGLE_ASSET_WEIGHT:
        warnings.append(
            f"Cet actif représenterait {_fr(asset_weight * 100)} % du portefeuille "
            f"(maximum conseillé : {MAX_SINGLE_ASSET_WEIGHT * 100:.0f} %)."
        )
    return asset_weight, cash_weight, warnings
