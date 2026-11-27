"""Moteur des salles de stratégie : rejeu de vraies données BVMT, le joueur choisit une
stratégie de trading et applique ses propres règles.

Principes
- Les cours viennent de l'historique réel (price_history), pas de scénarios figés : une fenêtre
  de jours consécutifs est tirée au hasard pour chaque tentative (les 10 premiers jours de
  l'actif servent uniquement de recul pour calculer la tendance, jamais de fenêtre de jeu).
- Chaque stratégie a ses propres règles d'entrée/sortie. Une violation n'empêche JAMAIS l'ordre
  (le joueur reste libre d'agir) : elle est seulement enregistrée et pénalise le score final.
- Ordres exécutés au prix du "jour" courant (un vrai jour de Bourse, ou un micro-prix généré
  pour le scalping), sans frais, sans vente à découvert.
- Score = rendement (%) − perte max (%) / 2 − 1 point par violation.
"""
import random
from datetime import date as date_type
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

INITIAL_CASH = 100_000.0
WINDOW_DAYS = 20       # nombre de jours de Bourse rejoués par tentative
LOOKBACK_DAYS = 10     # jours gardés avant la fenêtre, pour calculer la tendance au jour 0
SCALPING_TICKS = 16    # micro-prix générés par journée simulée, en mode scalping
TREND_LOOKBACK = 5     # jours comparés pour juger une tendance haussière/baissière

STRATEGIES = {
    "day_trading": {
        "name": "Day trading",
        "description": "Acheter et revendre la même action avant la fin de la journée simulée, pour éviter toute position du jour au lendemain.",
        "horizon": "Quelques heures (même journée)",
    },
    "position": {
        "name": "Trading de position",
        "description": "Garder une position longtemps, en ignorant les baisses passagères, en attendant une remontée.",
        "horizon": "Plusieurs semaines",
        "min_hold_days": 10,
    },
    "swing": {
        "name": "Swing trading",
        "description": "Repérer les creux et les sommets : acheter sur un creux, revendre sur un sommet, avec une détention de quelques jours.",
        "horizon": "2 à 7 jours",
        "min_hold_days": 2,
        "max_hold_days": 7,
    },
    "trend": {
        "name": "Trend trading",
        "description": "Suivre la tendance : acheter quand le cours est en tendance haussière, éviter d'acheter en tendance baissière.",
        "horizon": "Variable, selon la durée de la tendance",
    },
    "scalping": {
        "name": "Scalping",
        "description": "Acheter et revendre en quelques instants, sur de petits mouvements de prix à l'intérieur d'une seule journée simulée.",
        "horizon": "Quelques minutes (même micro-session)",
    },
}

SESSION_STRATEGIES = {"day_trading", "scalping"}  # doivent clôturer avant la fin de leur "session"


class RoomError(Exception):
    """Action refusée (message affichable au joueur)."""


def list_strategies() -> list[dict]:
    return [
        {"key": k, "name": v["name"], "description": v["description"], "horizon": v["horizon"]}
        for k, v in STRATEGIES.items()
    ]


# ---------- Données ----------
def _load_series(db: Session, symbol: str):
    from app.models.models import Asset, PriceHistory

    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None:
        raise RoomError("Actif inconnu")
    rows = db.scalars(
        select(PriceHistory).where(PriceHistory.asset_id == asset.id).order_by(PriceHistory.date)
    ).all()
    if len(rows) < LOOKBACK_DAYS + WINDOW_DAYS + 1:
        raise RoomError("Pas assez d'historique sur cet actif pour une salle de stratégie")
    return rows


def _group_of(strategy_key: str, idx: int) -> int:
    """Indice du 'jour de Bourse' réel correspondant à un indice de série (identique sauf en scalping)."""
    return idx // SCALPING_TICKS if strategy_key == "scalping" else idx


def _build_window(strategy_key: str, rows: list, start_row_idx: int, seed: int):
    """Construit les étiquettes/bougies OHLC affichées au joueur pour la fenêtre choisie."""
    window = rows[start_row_idx : start_row_idx + WINDOW_DAYS]
    if strategy_key != "scalping":
        labels = [r.date.isoformat() for r in window]
        opens = [float(r.open) for r in window]
        highs = [float(r.high) for r in window]
        lows = [float(r.low) for r in window]
        closes = [float(r.close) for r in window]
        volumes = [int(r.volume) if r.volume else 0 for r in window]
        return labels, opens, highs, lows, closes, volumes

    rng = random.Random(seed)
    labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    prev_close = float(window[0].open) if window else 0.0
    for r in window:
        o, h, l, c = float(r.open), float(r.high), float(r.low), float(r.close)
        v = int(r.volume) if r.volume else 0
        spread = max(h - l, abs(c - o), 0.01)
        for t in range(SCALPING_TICKS):
            frac = t / (SCALPING_TICKS - 1)
            base = o + (c - o) * frac
            noise = rng.uniform(-spread, spread) * 0.15
            price = round(min(max(base + noise, l * 0.98), h * 1.02), 3)
            labels.append(f"{r.date.isoformat()} · tick {t + 1}/{SCALPING_TICKS}")
            opens.append(prev_close)
            closes.append(price)
            highs.append(max(prev_close, price))
            lows.append(min(prev_close, price))
            volumes.append(round(v / SCALPING_TICKS))
            prev_close = price
    return labels, opens, highs, lows, closes, volumes


def _crisis(db: Session, run) -> dict:
    """Recharge la fenêtre réelle d'une tentative (rows réels + série affichée au joueur)."""
    rows = _load_series(db, run.symbol)
    dates = [r.date for r in rows]
    try:
        start_row_idx = dates.index(run.window_start)
    except ValueError:
        raise RoomError("Fenêtre de données introuvable (historique modifié depuis le début de la partie)")
    labels, opens, highs, lows, closes, volumes = _build_window(run.strategy_key, rows, start_row_idx, seed=run.id or 0)
    # Série de recul (10 jours réels avant la fenêtre), pour juger une tendance au tout début.
    lookback_closes = [float(r.close) for r in rows[max(0, start_row_idx - TREND_LOOKBACK) : start_row_idx]]
    return {
        "labels": labels,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "prices": closes,
        "volumes": volumes,
        "lookback": lookback_closes,
    }


# ---------- Valeur et score ----------
def equity(run, crisis: dict) -> float:
    price = crisis["prices"][run.day_index]
    total = run.cash
    for symbol, qty in (run.positions or {}).items():
        total += qty * price  # une seule action par tentative
    return total


def score_curve(curve: list[float], n_violations: int, initial: float = INITIAL_CASH) -> dict:
    final = curve[-1] if curve else initial
    peak = initial
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        worst = max(worst, (peak - value) / peak * 100)
    ret = (final / initial - 1) * 100
    score = ret - worst / 2 - n_violations
    return {
        "return_pct": round(ret, 2),
        "max_drawdown_pct": round(worst, 2),
        "score": round(score, 2),
        "final_equity": round(final, 2),
    }


# ---------- Règles de stratégie (avertissement, jamais de blocage) ----------
def _trend_at(crisis: dict, day_index: int) -> str | None:
    """'hausse' / 'baisse' / None si pas assez de recul pour juger."""
    closes_before = crisis["lookback"] + crisis["prices"][:day_index]
    if len(closes_before) < TREND_LOOKBACK:
        return None
    ref = closes_before[-TREND_LOOKBACK]
    now = crisis["prices"][day_index]
    if now > ref * 1.005:
        return "hausse"
    if now < ref * 0.995:
        return "baisse"
    return None


def _check_buy(run, crisis: dict) -> str | None:
    if run.strategy_key == "trend":
        trend = _trend_at(crisis, run.day_index)
        if trend == "baisse":
            return "Tu achètes alors que la tendance est baissière sur les derniers jours : le trend trading recommande d'acheter en tendance haussière."
    return None


def _check_sell(run, crisis: dict, symbol: str) -> str | None:
    rule = STRATEGIES[run.strategy_key]
    opened_day = (run.position_opened_day or {}).get(symbol)
    if opened_day is None:
        return None
    held = _group_of(run.strategy_key, run.day_index) - _group_of(run.strategy_key, opened_day)
    if "min_hold_days" in rule and held < rule["min_hold_days"]:
        return (
            f"Tu revends après seulement {held} jour(s) de détention, alors que la stratégie "
            f"« {rule['name']} » recommande d'attendre au moins {rule['min_hold_days']} jours."
        )
    if "max_hold_days" in rule and held > rule["max_hold_days"]:
        return (
            f"Tu as gardé cette position {held} jours, plus que le maximum recommandé "
            f"({rule['max_hold_days']} jours) pour la stratégie « {rule['name']} »."
        )
    return None


def _check_session_close(run, crisis: dict) -> list[str]:
    """Day trading / scalping : toute position ouverte doit être clôturée avant la fin de sa session."""
    if run.strategy_key not in SESSION_STRATEGIES:
        return []
    cur_group = _group_of(run.strategy_key, run.day_index)
    msgs = []
    for symbol, opened_day in (run.position_opened_day or {}).items():
        if (run.positions or {}).get(symbol, 0) > 0 and _group_of(run.strategy_key, opened_day) == cur_group:
            label = "la journée" if run.strategy_key == "day_trading" else "la session de scalping"
            msgs.append(f"Position sur {symbol} non clôturée avant la fin de {label}.")
    return msgs


# ---------- Conseil au joueur (purement indicatif, basé sur la logique de la stratégie) ----------
def _pct(entry_price: float, current_price: float) -> float:
    return round((current_price / entry_price - 1) * 100, 2) if entry_price else 0.0


def advice(run, crisis: dict, symbol: str) -> dict:
    """Que dit la stratégie choisie, maintenant, pour CE joueur (ses propres achats/ventes) ?

    Reprend exactement les mêmes règles que _check_buy/_check_sell/_check_session_close
    (pas de nouvelle heuristique inventée), mais formulées en conseil proactif
    ("tu devrais...") plutôt qu'en avertissement a posteriori, et personnalisées avec
    les chiffres réels de SA position (prix d'achat, jours détenus, gain/perte).

    action : "buy" | "sell" | "hold" (attendre avant de vendre) | "wait" (attendre avant
    d'acheter) | "free" (aucune contrainte de la stratégie, à toi de juger).
    """
    rule = STRATEGIES[run.strategy_key]
    held = (run.positions or {}).get(symbol, 0.0)
    current_price = crisis["prices"][run.day_index]

    if held <= 0:
        if run.strategy_key == "trend":
            trend = _trend_at(crisis, run.day_index)
            if trend == "hausse":
                return {"action": "buy", "message": "Tu n'as aucune position : la tendance est haussière, le trend trading recommande d'acheter maintenant."}
            if trend == "baisse":
                return {"action": "wait", "message": "Tu n'as aucune position : la tendance est baissière, attends un retournement haussier avant d'acheter."}
            return {"action": "wait", "message": "Tu n'as aucune position : pas encore de tendance nette, patiente avant d'acheter."}
        if run.strategy_key == "swing":
            trend = _trend_at(crisis, run.day_index)
            if trend == "baisse":
                return {"action": "buy", "message": "Tu n'as aucune position : repli récent du cours, c'est souvent le bon moment pour acheter en swing trading (creux)."}
            return {"action": "wait", "message": "Tu n'as aucune position : pas de creux net identifié, le swing trading attend un repli avant d'acheter."}
        if run.strategy_key == "position":
            return {"action": "buy", "message": "Tu n'as aucune position : le trading de position s'achète à tout moment, sans se soucier des creux ponctuels."}
        if run.strategy_key in SESSION_STRATEGIES:
            return {"action": "buy", "message": "Tu n'as aucune position : tu peux acheter à tout moment avec cette stratégie."}
        return {"action": "wait", "message": "Tu n'as aucune position pour l'instant."}

    opened_day = (run.position_opened_day or {}).get(symbol)
    held_days = None
    entry_price = None
    gain = None
    if opened_day is not None:
        held_days = _group_of(run.strategy_key, run.day_index) - _group_of(run.strategy_key, opened_day)
        entry_price = crisis["prices"][opened_day]
        gain = _pct(entry_price, current_price)
    gain_txt = f" (ton achat : {round(entry_price, 3)}, variation {gain:+.2f} %)" if entry_price is not None else ""

    if run.strategy_key == "trend":
        trend = _trend_at(crisis, run.day_index)
        if trend == "baisse":
            return {"action": "sell", "message": f"Tu détiens {held} action(s){gain_txt} : la tendance s'est retournée à la baisse, le trend trading recommande de vendre."}
        return {"action": "hold", "message": f"Tu détiens {held} action(s){gain_txt} : la tendance reste haussière, garde la position."}

    if run.strategy_key in SESSION_STRATEGIES:
        label = "la journée" if run.strategy_key == "day_trading" else "la session de scalping"
        return {"action": "sell", "message": f"Tu détiens {held} action(s){gain_txt} : clôture cette position avant la fin de {label}."}

    if "min_hold_days" in rule and held_days is not None and held_days < rule["min_hold_days"]:
        restant = rule["min_hold_days"] - held_days
        return {"action": "hold", "message": f"Tu détiens {held} action(s) depuis {held_days} jour(s){gain_txt} : la stratégie « {rule['name']} » recommande d'attendre encore {restant} jour(s) avant de vendre."}

    if "max_hold_days" in rule and held_days is not None and held_days >= rule["max_hold_days"]:
        return {"action": "sell", "message": f"Tu détiens {held} action(s) depuis {held_days} jours{gain_txt}, au maximum recommandé ({rule['max_hold_days']} j) : c'est le moment de vendre."}

    if run.strategy_key == "swing":
        trend = _trend_at(crisis, run.day_index)
        if trend == "baisse":
            return {"action": "sell", "message": f"Tu détiens {held} action(s){gain_txt} : le cours commence à refluer, un sommet a peut-être été atteint, bon moment pour vendre."}
        return {"action": "hold", "message": f"Tu détiens {held} action(s){gain_txt} : pas encore de signal de sommet, tu peux continuer à garder la position."}

    return {"action": "free", "message": f"Tu détiens {held} action(s){gain_txt} : tu peux vendre quand tu veux, aucune contrainte supplémentaire pour cette stratégie."}


# ---------- Cycle de vie d'une tentative ----------
def start_run(db: Session, user_id: int, strategy_key: str, symbol: str, now: datetime):
    from app.models.models import StrategyRun

    if strategy_key not in STRATEGIES:
        raise RoomError("Stratégie inconnue")
    rows = _load_series(db, symbol)
    dates = [r.date for r in rows]
    lo = LOOKBACK_DAYS
    hi = len(rows) - WINDOW_DAYS - 1
    if hi <= lo:
        raise RoomError("Pas assez d'historique sur cet actif pour une salle de stratégie")
    start_row_idx = random.randint(lo, hi)
    return StrategyRun(
        user_id=user_id,
        strategy_key=strategy_key,
        symbol=symbol,
        window_start=dates[start_row_idx],
        status="active",
        started_at=now,
        day_index=0,
        cash=INITIAL_CASH,
        positions={},
        position_opened_day={},
        equity_curve=[],
        violations=[],
    )


def _finish(run, crisis: dict, status: str, now: datetime) -> None:
    curve = list(run.equity_curve or []) + [equity(run, crisis)]
    result = score_curve(curve, len(run.violations or []))
    run.equity_curve = curve
    run.status = status
    run.finished_at = now
    run.score = result["score"]
    run.return_pct = result["return_pct"]
    run.max_drawdown_pct = result["max_drawdown_pct"]


def _require_active(run):
    if run.status != "active":
        raise RoomError("Cette tentative est terminée")


def close_run(run, now: datetime) -> None:
    """Ferme la tentative avant sa fin, sans la finaliser (pas de score calculé)."""
    if run.status != "active":
        raise RoomError("Cette tentative est déjà terminée")
    run.status = "abandoned"
    run.finished_at = now


def trade(db: Session, run, side: str, quantity: float, now: datetime) -> None:
    _require_active(run)
    crisis = _crisis(db, run)
    if not quantity or quantity <= 0:
        raise RoomError("Quantité invalide")
    quantity = round(float(quantity), 6)
    price = crisis["prices"][run.day_index]
    positions = dict(run.positions or {})
    opened = dict(run.position_opened_day or {})
    violations = list(run.violations or [])
    symbol = run.symbol

    if side == "buy":
        cost = quantity * price
        if cost > run.cash + 1e-6:
            raise RoomError("Liquidités insuffisantes")
        msg = _check_buy(run, crisis)
        if msg:
            violations.append({"day": run.day_index, "message": msg})
        run.cash = run.cash - cost
        new_qty = round(positions.get(symbol, 0.0) + quantity, 6)
        positions[symbol] = new_qty
        if symbol not in opened:
            opened[symbol] = run.day_index
    elif side == "sell":
        held = positions.get(symbol, 0.0)
        if quantity > held + 1e-9:
            raise RoomError("Quantité supérieure à celle détenue")
        msg = _check_sell(run, crisis, symbol)
        if msg:
            violations.append({"day": run.day_index, "message": msg})
        run.cash = run.cash + quantity * price
        left = round(held - quantity, 6)
        if left <= 0:
            positions.pop(symbol, None)
            opened.pop(symbol, None)
        else:
            positions[symbol] = left
    else:
        raise RoomError("Sens d'ordre invalide")

    run.positions = positions
    run.position_opened_day = opened
    run.violations = violations


def advance(db: Session, run, now: datetime) -> None:
    """Passe au jour/tick suivant ; sur le dernier, termine la partie."""
    _require_active(run)
    crisis = _crisis(db, run)
    last = len(crisis["prices"]) - 1

    for msg in _check_session_close(run, crisis):
        run.violations = list(run.violations or []) + [{"day": run.day_index, "message": msg}]

    if run.day_index >= last:
        _finish(run, crisis, "finished", now)
        return
    run.equity_curve = list(run.equity_curve or []) + [equity(run, crisis)]
    run.day_index += 1


# ---------- Vue envoyée au navigateur ----------
def build_state(db: Session, run, name: str) -> dict:
    crisis = _crisis(db, run)
    idx = run.day_index
    history = [
        {
            "time": d + 1,
            "label": crisis["labels"][d],
            "open": crisis["opens"][d],
            "high": crisis["highs"][d],
            "low": crisis["lows"][d],
            "close": crisis["prices"][d],
            "volume": crisis["volumes"][d],
        }
        for d in range(idx + 1)
    ]
    price = crisis["prices"][idx]
    held = (run.positions or {}).get(run.symbol, 0.0)

    state = {
        "run_id": run.id,
        "status": run.status,
        "strategy": {"key": run.strategy_key, **STRATEGIES[run.strategy_key]},
        "symbol": run.symbol,
        "asset_name": name,
        "day": idx + 1,
        "total_steps": len(crisis["prices"]),
        "label": crisis["labels"][idx],
        "cash": round(run.cash, 2),
        "equity": round(equity(run, crisis), 2),
        "initial_cash": INITIAL_CASH,
        "price": price,
        "quantity": held,
        "history": history,
        "violations": run.violations or [],
        "is_last_step": idx >= len(crisis["prices"]) - 1,
        "advice": advice(run, crisis, run.symbol) if run.status == "active" else None,
    }
    if run.status != "active":
        state["result"] = {
            "score": run.score,
            "return_pct": run.return_pct,
            "max_drawdown_pct": run.max_drawdown_pct,
            "n_violations": len(run.violations or []),
            "completed": run.status == "finished",
        }
    return state
