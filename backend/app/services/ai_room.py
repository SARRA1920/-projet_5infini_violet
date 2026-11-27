"""Moteur de la salle Type 3 : un choc brutal est appliqué sur une vraie courbe de prix,
puis l'IA calcule et propose la suite de la courbe (modèle stochastique calibré par l'IA).

Principes
- Les PRE_SHOCK_DAYS premiers jours affichés sont de vrais cours (price_history), pour le
  contexte : le joueur voit l'actif évoluer normalement avant le choc.
- Le "jour du choc" applique une baisse brutale (tirée au hasard) sur le dernier cours réel.
  C'est la partie que Sarra voulait écrire elle-même ; ici une version simple et transparente
  (chute aléatoire entre SHOCK_MIN et SHOCK_MAX) permet d'avoir une salle complète dès
  maintenant — à remplacer facilement par sa propre génération si besoin (un seul endroit :
  `_choose_shock`).
- À partir du choc, il n'y a plus de vraies données : l'IA "calcule la suite de la courbe".
  Méthode retenue : modèle stochastique calibré par l'IA (GBM, réutilisé du module actuariat),
  dont la dérive (mu) est calibrée pour moitié sur la tendance réelle pré-choc, et pour moitié
  sur le signal du module de prédiction IA (RandomForest). Limite assumée et affichée au
  joueur (section calibration) : ce module de prédiction prédit toujours à partir de
  l'historique le plus récent de l'actif — il ne peut pas "se replacer" juste après un choc
  fictif — donc son signal sert de proxy de régime général, pas d'une vraie prévision du
  rebond post-choc.
- La trajectoire (réelle + choc + IA) est recalculée à chaque appel mais de façon
  déterministe (graine = id de la tentative), donc toujours identique pour une même partie —
  comme les autres salles, rien n'est stocké en double en base.
- Le joueur joue ensuite comme dans les salles Type 1/2 : achat/vente au jour courant, avance
  jour par jour sur la trajectoire générée par l'IA. Score identique : rendement − perte max/2.
"""
import random
from datetime import datetime

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.actuarial.stochastic import gbm

INITIAL_CASH = 100_000.0
PRE_SHOCK_DAYS = 30     # jours réels de contexte avant le choc
HORIZON_DAYS = 20       # jours générés par l'IA, joués par le joueur
SHOCK_MIN = 0.12        # chute minimale au jour du choc (12 %)
SHOCK_MAX = 0.35        # chute maximale (35 %)


class RoomError(Exception):
    """Action refusée (message affichable au joueur)."""


# ---------- Sélection de l'actif et de la fenêtre réelle ----------
def _eligible_assets(db: Session) -> list:
    from app.models.models import Asset, PriceHistory

    assets = db.scalars(select(Asset)).all()
    out = []
    for a in assets:
        n = db.scalar(select(func.count(PriceHistory.id)).where(PriceHistory.asset_id == a.id))
        if n and n >= PRE_SHOCK_DAYS + 5:
            out.append(a)
    return out


def _load_series(db: Session, symbol: str):
    from app.models.models import Asset, PriceHistory

    asset = db.scalar(select(Asset).where(Asset.symbol == symbol))
    if asset is None:
        raise RoomError("Actif inconnu")
    rows = db.scalars(
        select(PriceHistory).where(PriceHistory.asset_id == asset.id).order_by(PriceHistory.date)
    ).all()
    if len(rows) < PRE_SHOCK_DAYS + 5:
        raise RoomError("Pas assez d'historique sur cet actif pour une salle IA")
    return rows


def _choose_shock(rng: random.Random) -> float:
    """La génération du choc elle-même : un seul endroit à remplacer si Sarra veut
    brancher sa propre logique plus tard."""
    return round(rng.uniform(SHOCK_MIN, SHOCK_MAX), 3)


# ---------- Calibration IA : GBM + signal du module de prédiction ----------
def _calibrate(db: Session, symbol: str, pre_shock_closes: list[float]) -> dict:
    stats = gbm.calibrate(np.array(pre_shock_closes))
    mu_hist = stats["mu"]
    sigma = stats["sigma"] * 1.25  # volatilité relevée après un choc (régime plus agité)

    prediction_used = False
    predicted_return = None
    confidence = None
    note = "Dérive basée uniquement sur la tendance réelle pré-choc (signal IA indisponible)."
    mu_final = mu_hist

    try:
        from app.ia import prediction as ia_prediction

        horizon = min(30, HORIZON_DAYS)
        result = ia_prediction.predict(db, symbol, horizon=horizon)
        predicted_return = result.predicted_return
        confidence = result.confidence
        mu_signal = (predicted_return / horizon) * 252  # annualisé, approximation
        mu_final = 0.5 * mu_hist + 0.5 * mu_signal
        prediction_used = True
        note = (
            "Dérive = moyenne entre la tendance réelle pré-choc et le signal du module de "
            "prédiction IA. Limite importante : ce module prédit toujours à partir de "
            "l'historique le plus récent de l'actif (il ne peut pas se replacer juste après "
            "un choc fictif) — c'est donc un indicateur de régime général, pas une vraie "
            "prévision du rebond lui-même."
        )
    except (ValueError, ImportError) as exc:
        note += f" ({exc})"

    return {
        "mu_annualise": round(mu_final, 4),
        "sigma_annualise": round(sigma, 4),
        "mu_historique_pre_choc": round(mu_hist, 4),
        "prediction_ia_utilisee": prediction_used,
        "rendement_predit_ia": round(predicted_return, 4) if predicted_return is not None else None,
        "confiance_ia": round(confidence, 2) if confidence is not None else None,
        "note": note,
    }


# ---------- Construction déterministe de la trajectoire complète ----------
def _timeline(db: Session, run) -> dict:
    rows = _load_series(db, run.symbol)
    dates = [r.date for r in rows]
    try:
        start_idx = dates.index(run.window_start)
    except ValueError:
        raise RoomError("Fenêtre de données introuvable (historique modifié depuis le début de la partie)")

    pre = rows[start_idx : start_idx + PRE_SHOCK_DAYS]
    labels = [r.date.isoformat() for r in pre]
    opens = [float(r.open) for r in pre]
    highs = [float(r.high) for r in pre]
    lows = [float(r.low) for r in pre]
    closes = [float(r.close) for r in pre]
    volumes = [int(r.volume) if r.volume else 0 for r in pre]
    avg_volume = (sum(volumes) / len(volumes)) if volumes else 0.0

    last_close = closes[-1]
    shock_close = round(last_close * (1 - run.shock_pct), 3)
    labels.append(f"{pre[-1].date.isoformat()} · choc")
    opens.append(last_close)
    highs.append(last_close)
    lows.append(shock_close)
    closes.append(shock_close)
    volumes.append(round(avg_volume))
    shock_index = len(closes) - 1

    calibration = _calibrate(db, run.symbol, closes[:shock_index])

    paths, _times = gbm.simulate(
        s0=shock_close,
        mu=calibration["mu_annualise"],
        sigma=calibration["sigma_annualise"],
        horizon=HORIZON_DAYS * gbm.DAILY_DT,
        steps=HORIZON_DAYS,
        n_simulations=1,
        seed=run.id,
    )
    ai_closes = paths[0][1:].tolist()  # on saute s0 (= le choc, déjà enregistré)

    rng = random.Random((run.id or 0) * 7919 + 3)
    prev_close = shock_close
    for i, c in enumerate(ai_closes):
        c = round(float(c), 3)
        o = prev_close
        spread = abs(c - o) * 0.2 + 0.001
        h = max(o, c) + rng.uniform(0, spread)
        l = max(min(o, c) - rng.uniform(0, spread), 0.01)
        v = max(0, round(avg_volume * rng.uniform(0.6, 1.3)))
        labels.append(f"{pre[-1].date.isoformat()} +{i + 1}j (IA)")
        opens.append(round(o, 3))
        highs.append(round(h, 3))
        lows.append(round(l, 3))
        closes.append(c)
        volumes.append(v)
        prev_close = c

    return {
        "labels": labels,
        "opens": opens,
        "highs": highs,
        "lows": lows,
        "prices": closes,
        "volumes": volumes,
        "shock_index": shock_index,
        "calibration": calibration,
    }


# ---------- Valeur et score ----------
def equity(run, timeline: dict) -> float:
    price = timeline["prices"][run.day_index]
    total = run.cash
    for symbol, qty in (run.positions or {}).items():
        total += qty * price
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


# ---------- Cycle de vie d'une tentative ----------
def start_run(db: Session, user_id: int, now: datetime, symbol: str | None = None):
    from app.models.models import AiRun

    if symbol:
        rows = _load_series(db, symbol)
    else:
        eligible = _eligible_assets(db)
        if not eligible:
            raise RoomError("Aucun actif n'a assez d'historique pour une salle IA")
        asset = random.choice(eligible)
        symbol = asset.symbol
        rows = _load_series(db, symbol)

    hi = len(rows) - PRE_SHOCK_DAYS
    if hi <= 0:
        raise RoomError("Pas assez d'historique sur cet actif pour une salle IA")
    start_idx = random.randint(0, hi - 1)
    shock_pct = _choose_shock(random)

    return AiRun(
        user_id=user_id,
        symbol=symbol,
        window_start=rows[start_idx].date,
        shock_pct=shock_pct,
        status="active",
        started_at=now,
        day_index=PRE_SHOCK_DAYS,  # le jeu commence le jour du choc
        cash=INITIAL_CASH,
        positions={},
        equity_curve=[],
    )


def _finish(run, timeline: dict, status: str, now: datetime) -> None:
    curve = list(run.equity_curve or []) + [equity(run, timeline)]
    result = score_curve(curve)
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
    timeline = _timeline(db, run)
    if not quantity or quantity <= 0:
        raise RoomError("Quantité invalide")
    quantity = round(float(quantity), 6)
    price = timeline["prices"][run.day_index]
    positions = dict(run.positions or {})
    symbol = run.symbol

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


def advance(db: Session, run, now: datetime) -> None:
    """Passe au jour suivant de la trajectoire IA ; sur le dernier, termine la partie."""
    _require_active(run)
    timeline = _timeline(db, run)
    last = len(timeline["prices"]) - 1
    if run.day_index >= last:
        _finish(run, timeline, "finished", now)
        return
    run.equity_curve = list(run.equity_curve or []) + [equity(run, timeline)]
    run.day_index += 1


# ---------- Vue envoyée au navigateur ----------
def build_state(db: Session, run, name: str) -> dict:
    timeline = _timeline(db, run)
    idx = run.day_index
    shock_index = timeline["shock_index"]

    def kind_of(d: int) -> str:
        if d < shock_index:
            return "reel"
        if d == shock_index:
            return "choc"
        return "ia"

    history = [
        {
            "time": d + 1,
            "label": timeline["labels"][d],
            "open": timeline["opens"][d],
            "high": timeline["highs"][d],
            "low": timeline["lows"][d],
            "close": timeline["prices"][d],
            "volume": timeline["volumes"][d],
            "kind": kind_of(d),
        }
        for d in range(idx + 1)
    ]
    price = timeline["prices"][idx]
    held = (run.positions or {}).get(run.symbol, 0.0)

    state = {
        "run_id": run.id,
        "status": run.status,
        "symbol": run.symbol,
        "asset_name": name,
        "shock_pct": run.shock_pct,
        "day": idx - shock_index + 1,
        "total_steps": HORIZON_DAYS + 1,
        "pre_shock_days": PRE_SHOCK_DAYS,
        "label": timeline["labels"][idx],
        "cash": round(run.cash, 2),
        "equity": round(equity(run, timeline), 2),
        "initial_cash": INITIAL_CASH,
        "price": price,
        "quantity": held,
        "history": history,
        "is_last_step": idx >= len(timeline["prices"]) - 1,
        "calibration": timeline["calibration"],
    }
    if run.status != "active":
        state["result"] = {
            "score": run.score,
            "return_pct": run.return_pct,
            "max_drawdown_pct": run.max_drawdown_pct,
            "completed": run.status == "finished",
        }
    return state
