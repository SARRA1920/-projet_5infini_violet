"""Moteur des salles de crise : rejeu jour par jour de vraies crises financières.

Principes
- Les cours viennent de fichiers JSON figés (app/data/crises/*.json) : tout le monde rejoue les mêmes prix.
- Le serveur ne révèle JAMAIS les prix des jours à venir (pas de triche possible).
- Chaque tentative a son propre portefeuille virtuel (CrisisRun), sans lien avec le vrai portefeuille.
- Ordres exécutés au cours de clôture du jour courant, sans frais, sans vente à découvert.
- Score = rendement (%) − perte maximale (%) / 2.
"""
import json
from bisect import bisect_right
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
INITIAL_CASH = 100_000.0

LEVEL_RANK = {"debutant": 0, "intermediaire": 1, "pro": 2}
VALIDATION_SCORE = 3.0  # score minimal d'une partie terminée pour valider la salle
PREP_SECONDS = 60
SECONDS_PER_DAY = {"debutant": 20, "intermediaire": 15, "pro": 12}


class RoomError(Exception):
    """Action refusée (message affichable au joueur)."""


# ---------- Données ----------
@lru_cache(maxsize=None)
def load_crisis(key: str) -> dict:
    path = DATA / "crises" / f"{key}.json"
    if not path.exists():
        raise RoomError("Salle inconnue")
    doc = json.loads(path.read_text(encoding="utf-8"))
    prices = doc["prices"]
    # Calendrier = jours où plus de la moitié des actifs cotent (jours de Bourse).
    counts: dict[str, int] = {}
    for rows in prices.values():
        for row in rows:
            counts[row[0]] = counts.get(row[0], 0) + 1
    calendar = sorted(d for d, n in counts.items() if n * 2 > len(prices))
    series = {s: ([r[0] for r in rows], [r[4] for r in rows]) for s, rows in prices.items()}
    return {"meta": {k: v for k, v in doc.items() if k != "prices"}, "calendar": calendar, "series": series}


def list_keys() -> list[str]:
    catalog = json.loads((DATA / "crises_catalog.json").read_text(encoding="utf-8"))
    return [c["key"] for c in catalog["crises"]]


def price_at(crisis: dict, symbol: str, day: int) -> float | None:
    """Dernier cours de clôture connu à la date du jour `day` (None si pas encore coté)."""
    dates, closes = crisis["series"][symbol]
    i = bisect_right(dates, crisis["calendar"][day]) - 1
    return closes[i] if i >= 0 else None


def time_limit_seconds(crisis: dict) -> int:
    """60 s de préparation + (nombre de jours × secondes par jour selon le niveau)."""
    level = crisis["meta"]["level"]
    return PREP_SECONDS + len(crisis["calendar"]) * SECONDS_PER_DAY[level]


def can_enter(user_level: str | None, is_admin: bool, crisis: dict) -> bool:
    if is_admin:
        return True
    return LEVEL_RANK.get(user_level, -1) >= LEVEL_RANK[crisis["meta"]["level"]]


# ---------- Valeur et score ----------
def equity(run, crisis: dict) -> float:
    total = run.cash
    for symbol, qty in (run.positions or {}).items():
        price = price_at(crisis, symbol, run.day_index)
        total += qty * (price or 0.0)
    return total


def score_curve(curve: list[float], initial: float = INITIAL_CASH) -> dict:
    """Rendement, perte maximale (creux depuis un sommet) et score = rendement − perte/2."""
    final = curve[-1] if curve else initial
    peak = initial
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak * 100)
    ret = (final / initial - 1) * 100
    return {
        "return_pct": round(ret, 2),
        "max_drawdown_pct": round(worst, 2),
        "score": round(ret - worst / 2, 2),
        "final_equity": round(final, 2),
    }


# ---------- Cycle de vie d'une tentative ----------
def start_run(user_id: int, key: str, now: datetime):
    from app.models.models import CrisisRun

    crisis = load_crisis(key)
    return CrisisRun(
        user_id=user_id,
        crisis_key=key,
        status="active",
        started_at=now,
        day_index=0,
        cash=INITIAL_CASH,
        positions={},
        equity_curve=[],
    )


def deadline(run, crisis: dict) -> datetime:
    return run.started_at + timedelta(seconds=time_limit_seconds(crisis))


def _finish(run, crisis: dict, status: str, now: datetime) -> None:
    curve = list(run.equity_curve or []) + [equity(run, crisis)]
    result = score_curve(curve)
    run.equity_curve = curve
    run.status = status
    run.finished_at = now
    run.score = result["score"]
    run.return_pct = result["return_pct"]
    run.max_drawdown_pct = result["max_drawdown_pct"]


def expire_if_needed(run, now: datetime) -> bool:
    """Ferme la tentative si le temps est écoulé (score calculé sur la situation du moment)."""
    if run.status == "active":
        crisis = load_crisis(run.crisis_key)
        if now >= deadline(run, crisis):
            _finish(run, crisis, "timeout", now)
            return True
    return False


def _require_active(run, now: datetime) -> dict:
    if run.status != "active":
        raise RoomError("Cette tentative est terminée")
    if expire_if_needed(run, now):
        raise RoomError("Le temps est écoulé : la salle est fermée")
    return load_crisis(run.crisis_key)


def trade(run, symbol: str, side: str, quantity: float, now: datetime) -> None:
    crisis = _require_active(run, now)
    if symbol not in crisis["series"]:
        raise RoomError("Actif indisponible dans cette salle")
    if not quantity or quantity <= 0:
        raise RoomError("Quantité invalide")
    quantity = round(float(quantity), 6)
    price = price_at(crisis, symbol, run.day_index)
    if price is None:
        raise RoomError("Cet actif n'est pas encore coté à cette date")
    positions = dict(run.positions or {})
    if side == "buy":
        cost = quantity * price
        if cost > run.cash + 1e-6:
            raise RoomError("Liquidités insuffisantes")
        run.cash = run.cash - cost
        positions[symbol] = round(positions.get(symbol, 0.0) + quantity, 6)
    elif side == "sell":
        held = positions.get(symbol, 0.0)
        if quantity > held + 1e-9:
            raise RoomError("Quantité supérieure à celle détenue")
        run.cash = run.cash + quantity * price
        left = round(held - quantity, 6)
        if left <= 0:
            positions.pop(symbol, None)
        else:
            positions[symbol] = left
    else:
        raise RoomError("Sens d'ordre invalide")
    run.positions = positions


def advance(run, now: datetime) -> None:
    """Passe au jour suivant ; sur le dernier jour, termine la partie."""
    crisis = _require_active(run, now)
    last = len(crisis["calendar"]) - 1
    if run.day_index >= last:
        _finish(run, crisis, "finished", now)
        return
    run.equity_curve = list(run.equity_curve or []) + [equity(run, crisis)]
    run.day_index += 1


# ---------- Vue envoyée au navigateur (jamais de prix futurs) ----------
def build_state(run, now: datetime, names: dict[str, str]) -> dict:
    crisis = load_crisis(run.crisis_key)
    meta = crisis["meta"]
    n_days = len(crisis["calendar"])
    idx = run.day_index
    limit = time_limit_seconds(crisis)
    left = max(0, int((deadline(run, crisis) - now).total_seconds())) if run.status == "active" else 0

    assets = []
    for symbol in crisis["series"]:
        price = price_at(crisis, symbol, idx)
        prev = price_at(crisis, symbol, idx - 1) if idx > 0 else None
        history = []
        for d in range(idx + 1):
            p = price_at(crisis, symbol, d)
            if p is not None:
                history.append([crisis["calendar"][d], p])
        assets.append(
            {
                "symbol": symbol,
                "name": names.get(symbol, symbol),
                "price": price,
                "change_pct": round((price / prev - 1) * 100, 2) if price and prev else None,
                "quantity": (run.positions or {}).get(symbol, 0.0),
                "history": history,
            }
        )

    state = {
        "run_id": run.id,
        "status": run.status,
        "crisis": {"key": meta["key"], "name": meta["name"], "level": meta["level"], "story": meta["story"]},
        "day": idx + 1,
        "total_days": n_days,
        "date": crisis["calendar"][idx],
        "time_limit_seconds": limit,
        "seconds_left": left,
        "cash": round(run.cash, 2),
        "equity": round(equity(run, crisis), 2),
        "initial_cash": INITIAL_CASH,
        "assets": assets,
        "is_last_day": idx >= n_days - 1,
    }
    if run.status != "active":
        state["result"] = {
            "score": run.score,
            "return_pct": run.return_pct,
            "max_drawdown_pct": run.max_drawdown_pct,
            "completed": run.status == "finished",
            "validated": run.status == "finished" and run.score is not None and run.score >= VALIDATION_SCORE,
            "days_played": idx + 1,
        }
    return state
