"""Moteur de la salle Type 1 : rejeu d'une vraie crise BVMT, tirée au hasard à chaque partie.

Principes
- Contrairement aux salles de crise de la Formation (un scénario figé par salle), ici une
  crise différente est tirée au hasard dans un catalogue à chaque nouvelle tentative.
- Les cours viennent du vrai historique (price_history), pour TOUS les actifs cotés
  pendant la période choisie (pas un seul actif).
- Ordres exécutés au cours de clôture du jour courant, sans frais, sans vente à découvert.
- Score = rendement (%) − perte maximale (%) / 2.
"""
import random
from bisect import bisect_right
from datetime import datetime
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

INITIAL_CASH = 100_000.0

EVENTS = {
    "covid_2020": {
        "name": "Krach du COVID-19",
        "story": "Février-avril 2020 : l'arrêt brutal de l'économie mondiale fait plonger les marchés, BVMT comprise.",
        "start": "2020-02-01",
        "end": "2020-04-30",
    },
    "crise_25_juillet_2021": {
        "name": "25 juillet 2021",
        "story": "Été 2021 : l'intervention présidentielle du 25 juillet bouleverse la scène politique tunisienne et secoue la Bourse de Tunis.",
        "start": "2021-06-01",
        "end": "2021-09-30",
    },
    "guerre_ukraine_2022": {
        "name": "Guerre en Ukraine",
        "story": "Février-avril 2022 : le choc énergétique et l'incertitude mondiale qui suivent l'invasion de l'Ukraine frappent les marchés.",
        "start": "2022-02-01",
        "end": "2022-04-30",
    },
    "devaluation_dinar_2018": {
        "name": "Dévaluation du dinar (2018)",
        "story": "Été-automne 2018 : la chute du dinar tunisien et les tensions budgétaires pèsent sur les valeurs cotées.",
        "start": "2018-06-01",
        "end": "2018-10-31",
    },
    "dette_fmi_2023": {
        "name": "Crise de la dette / négociations FMI",
        "story": "Premier semestre 2023 : l'incertitude autour des négociations avec le FMI et de la dette publique inquiète les investisseurs.",
        "start": "2023-01-01",
        "end": "2023-06-30",
    },
    "instabilite_post_covid_2020_2021": {
        "name": "Instabilité post-COVID",
        "story": "Fin 2020 : la reprise économique tunisienne reste fragile, les cours restent très volatils après le choc du printemps.",
        "start": "2020-09-01",
        "end": "2020-12-31",
    },
}


class RoomError(Exception):
    """Action refusée (message affichable au joueur)."""


def list_events() -> list[dict]:
    return [{"key": k, "name": v["name"], "story": v["story"]} for k, v in EVENTS.items()]


@lru_cache(maxsize=16)
def _load_event(event_key: str) -> dict:
    from app.core.database import SessionLocal
    from app.models.models import Asset, PriceHistory

    meta = EVENTS.get(event_key)
    if meta is None:
        raise RoomError("Évènement inconnu")
    db = SessionLocal()
    try:
        rows = db.execute(
            select(
                PriceHistory.date,
                PriceHistory.open,
                PriceHistory.high,
                PriceHistory.low,
                PriceHistory.close,
                PriceHistory.volume,
                Asset.symbol,
            )
            .join(Asset, Asset.id == PriceHistory.asset_id)
            .where(PriceHistory.date >= meta["start"], PriceHistory.date <= meta["end"])
            .order_by(PriceHistory.date)
        ).all()
    finally:
        db.close()
    if not rows:
        raise RoomError("Pas de données pour cette période")
    counts: dict = {}
    per_symbol: dict = {}
    for d, o, h, l, c, v, symbol in rows:
        counts[d] = counts.get(d, 0) + 1
        per_symbol.setdefault(symbol, ([], [], [], [], [], []))
        dates, opens, highs, lows, closes, volumes = per_symbol[symbol]
        dates.append(d)
        opens.append(float(o))
        highs.append(float(h))
        lows.append(float(l))
        closes.append(float(c))
        volumes.append(int(v) if v else 0)
    n_symbols = len(per_symbol)
    calendar = sorted(d for d, n in counts.items() if n * 2 > n_symbols)
    return {"meta": meta, "calendar": calendar, "series": per_symbol}


def price_at(event: dict, symbol: str, day: int) -> float | None:
    dates, _opens, _highs, _lows, closes, _volumes = event["series"][symbol]
    i = bisect_right(dates, event["calendar"][day]) - 1
    return closes[i] if i >= 0 else None


def ohlc_at(event: dict, symbol: str, day: int):
    dates, opens, highs, lows, closes, volumes = event["series"][symbol]
    i = bisect_right(dates, event["calendar"][day]) - 1
    if i < 0:
        return None
    return opens[i], highs[i], lows[i], closes[i], volumes[i]


def equity(run, event: dict) -> float:
    total = run.cash
    for symbol, qty in (run.positions or {}).items():
        price = price_at(event, symbol, run.day_index)
        total += qty * (price or 0.0)
    return total


def score_curve(curve: list[float], initial: float = INITIAL_CASH) -> dict:
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


def start_run(user_id: int, now: datetime):
    from app.models.models import EventRun

    event_key = random.choice(list(EVENTS.keys()))
    return EventRun(
        user_id=user_id,
        event_key=event_key,
        status="active",
        started_at=now,
        day_index=0,
        cash=INITIAL_CASH,
        positions={},
        equity_curve=[],
    )


def _finish(run, event: dict, status: str, now: datetime) -> None:
    curve = list(run.equity_curve or []) + [equity(run, event)]
    result = score_curve(curve)
    run.equity_curve = curve
    run.status = status
    run.finished_at = now
    run.score = result["score"]
    run.return_pct = result["return_pct"]
    run.max_drawdown_pct = result["max_drawdown_pct"]


def _require_active(run) -> dict:
    if run.status != "active":
        raise RoomError("Cette tentative est terminée")
    return _load_event(run.event_key)


def trade(run, symbol: str, side: str, quantity: float, now: datetime) -> None:
    event = _require_active(run)
    if symbol not in event["series"]:
        raise RoomError("Actif indisponible pendant cette période")
    if not quantity or quantity <= 0:
        raise RoomError("Quantité invalide")
    quantity = round(float(quantity), 6)
    price = price_at(event, symbol, run.day_index)
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
    event = _require_active(run)
    last = len(event["calendar"]) - 1
    if run.day_index >= last:
        _finish(run, event, "finished", now)
        return
    run.equity_curve = list(run.equity_curve or []) + [equity(run, event)]
    run.day_index += 1


def build_state(run, names: dict[str, str]) -> dict:
    event = _load_event(run.event_key)
    meta = event["meta"]
    idx = run.day_index
    n_days = len(event["calendar"])

    assets = []
    for symbol in event["series"]:
        price = price_at(event, symbol, idx)
        prev = price_at(event, symbol, idx - 1) if idx > 0 else None
        history = []
        for d in range(idx + 1):
            bar = ohlc_at(event, symbol, d)
            if bar is not None:
                o, h, l, c, v = bar
                history.append(
                    {"time": event["calendar"][d].isoformat(), "open": o, "high": h, "low": l, "close": c, "volume": v}
                )
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
        "event": {"key": meta.get("name", run.event_key), "name": meta["name"], "story": meta["story"]},
        "day": idx + 1,
        "total_days": n_days,
        "date": event["calendar"][idx].isoformat(),
        "cash": round(run.cash, 2),
        "equity": round(equity(run, event), 2),
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
        }
    return state
