"""Agent de trading : combine prédiction, indicateurs techniques et sentiment.

Approche : **policy rule-based** avec scoring de confiance et explications.
On agrège trois signaux en un score composite [-1, +1], puis on mappe vers
une décision BUY / SELL / HOLD avec un seuil.

Pourquoi pas du reinforcement learning ? Un agent RL (Q-learning) serait
plus ambitieux mais nécessite : un environnement de trading (gymnasium),
des milliers d'épisodes d'entraînement, et un historique long. Pour un
projet pédagogique avec un historique limité, la policy rule-based est
plus fiable, plus explicable et plus rapide à mettre en place. L'interface
(decide() -> AgentDecision) resterait identique pour une évolution future.

Signaux combinés :
1. **Prédiction IA** (poids 0.5) : rendement prédit sur l'horizon,
   normalisé par la volatilité réalisée.
2. **Technique** (poids 0.3) : RSI (survente < 30 → haussier, surachat > 70
   → baissier) + crossover SMA20/SMA50.
3. **Sentiment** (poids 0.2) : score moyen des titres de news.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset, PriceHistory

from . import features as F
from . import prediction as pred
from . import sentiment as sent


@dataclass
class AgentReason:
    signal: str       # "prediction" | "technique" | "sentiment"
    detail: str
    contribution: float   # contribution au score composite [-1, +1]


@dataclass
class AgentDecision:
    symbol: str
    action: str               # "BUY" | "SELL" | "HOLD"
    confidence: float         # 0.0 - 1.0
    composite_score: float    # -1.0 à +1.0
    reasons: list[AgentReason] = field(default_factory=list)
    predicted_return: float = 0.0
    horizon: int = 5


# Seuils de décision : |score| > DECISION_THRESHOLD → BUY ou SELL.
DECISION_THRESHOLD = 0.15


def _technical_signal(closes: list[float]) -> tuple[float, str]:
    """Signal technique basé sur RSI et crossover SMA20/SMA50.

    Renvoie (score [-1,+1], description).
    """
    if len(closes) < 50:
        return 0.0, "Historique insuffisant pour les indicateurs techniques"

    rsi_arr = F.rsi(closes, 14)
    sma20 = F.sma(closes, 20)
    sma50 = F.sma(closes, 50)
    last_rsi = float(rsi_arr[-1]) if np.isfinite(rsi_arr[-1]) else 50.0

    parts = []
    score = 0.0

    # RSI : survente → haussier, surachat → baissier.
    if last_rsi < 30:
        score += 0.4
        parts.append(f"RSI={last_rsi:.0f} (survente, signal haussier)")
    elif last_rsi > 70:
        score -= 0.4
        parts.append(f"RSI={last_rsi:.0f} (surachat, signal baissier)")
    else:
        parts.append(f"RSI={last_rsi:.0f} (neutre)")

    # Crossover SMA20/SMA50 : golden cross (SMA20 > SMA50) → haussier.
    last_sma20 = float(sma20[-1]) if np.isfinite(sma20[-1]) else None
    last_sma50 = float(sma50[-1]) if np.isfinite(sma50[-1]) else None
    if last_sma20 is not None and last_sma50 is not None:
        if last_sma20 > last_sma50:
            score += 0.3
            parts.append("SMA20 > SMA50 (tendance haussière)")
        else:
            score -= 0.3
            parts.append("SMA20 < SMA50 (tendance baissière)")

    score = max(-1.0, min(1.0, score))
    return score, " ; ".join(parts)


def decide(
    db: Session,
    symbol: str,
    horizon: int = 5,
) -> AgentDecision:
    """Produit une décision de trading pour `symbol`.

    Combine prédiction IA, signal technique et sentiment.
    """
    reasons: list[AgentReason] = []

    # 1. Prédiction IA (poids 0.5).
    try:
        p = pred.predict(db, symbol, horizon=horizon)
        vol = F.rolling_volatility(
            _load_recent_closes(db, symbol, n=30), 20
        )
        last_vol = float(vol[-1]) if len(vol) and np.isfinite(vol[-1]) else 0.02
        last_vol = max(last_vol, 0.005)  # éviter division par zéro
        pred_signal = max(-1.0, min(1.0, p.predicted_return / (last_vol * np.sqrt(horizon))))
        reasons.append(AgentReason(
            signal="prediction",
            detail=(
                f"Rendement prédit {horizon}j : {p.predicted_return*100:.2f}% "
                f"(volat {last_vol*100:.2f}%/j, conf {p.confidence*100:.0f}%)"
            ),
            contribution=pred_signal * 0.5,
        ))
        predicted_return = p.predicted_return
    except ValueError as e:
        # Pas assez d'historique : on continue sans prédiction.
        reasons.append(AgentReason(
            signal="prediction",
            detail=f"Prédiction indisponible : {e}",
            contribution=0.0,
        ))
        pred_signal = 0.0
        predicted_return = 0.0

    # 2. Signal technique (poids 0.3).
    closes = _load_recent_closes(db, symbol, n=120)
    tech_score, tech_desc = _technical_signal(closes)
    reasons.append(AgentReason(
        signal="technique",
        detail=tech_desc,
        contribution=tech_score * 0.3,
    ))

    # 3. Sentiment (poids 0.2).
    titles = sent.fetch_headlines(symbol)
    if titles:
        avg_score, label, _ = sent.aggregate_sentiment(titles)
        sent_signal = max(-1.0, min(1.0, avg_score))
        reasons.append(AgentReason(
            signal="sentiment",
            detail=f"{len(titles)} titres analysés, sentiment {label} (score {avg_score:.2f})",
            contribution=sent_signal * 0.2,
        ))
    else:
        reasons.append(AgentReason(
            signal="sentiment",
            detail="Pas de titres disponibles (source de news non connectée)",
            contribution=0.0,
        ))

    composite = sum(r.contribution for r in reasons)
    composite = max(-1.0, min(1.0, composite))

    # Décision.
    if composite > DECISION_THRESHOLD:
        action = "BUY"
    elif composite < -DECISION_THRESHOLD:
        action = "SELL"
    else:
        action = "HOLD"

    # Confiance : éloignement du seuil + cohérence des signaux.
    margin = abs(composite) - DECISION_THRESHOLD
    contributions = [r.contribution for r in reasons if r.contribution != 0.0]
    if len(contributions) >= 2:
        # Cohérence : les signaux pointent-ils dans le même sens ?
        same_sign = sum(1 for c in contributions if np.sign(c) == np.sign(composite))
        alignment = same_sign / len(contributions)
    else:
        alignment = 0.5
    confidence = float(max(0.0, min(1.0, 0.3 * alignment + 0.7 * max(0.0, margin * 3.0))))

    return AgentDecision(
        symbol=symbol,
        action=action,
        confidence=confidence,
        composite_score=composite,
        reasons=reasons,
        predicted_return=predicted_return,
        horizon=horizon,
    )


def _load_recent_closes(db: Session, symbol: str, n: int = 120) -> list[float]:
    """Charge les N derniers cours de clôture pour un symbole."""
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    if asset is None:
        return []
    rows = db.execute(
        select(PriceHistory.close)
        .where(PriceHistory.asset_id == asset.id)
        .order_by(PriceHistory.date.desc())
        .limit(n)
    ).all()
    closes = [float(r.close) for r in rows]
    closes.reverse()  # du plus ancien au plus récent
    return closes


# ---------------------------------------------------------------------------
# Backtest : simule la stratégie de l'agent sur l'historique passé.
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    index: int
    action: str               # "BUY" | "SELL" | "HOLD"
    predicted_return: float
    actual_return: float
    correct: bool             # le sens prédit correspond-il au sens réel ?


@dataclass
class BacktestResult:
    symbol: str
    horizon: int
    n_points: int             # nombre de jours évalués
    n_buy: int
    n_sell: int
    n_hold: int
    win_rate: float           # réussite des signaux directionnels (BUY+SELL)
    total_return: float       # somme des rendements réels selon la position
    avg_predicted: float
    avg_actual: float
    trades: list[BacktestTrade]


def backtest(
    db: Session,
    symbol: str,
    horizon: int = 5,
    max_points: int = 120,
) -> BacktestResult:
    """Simule la stratégie de l'agent sur l'historique passé.

    Pour chaque jour t où les features sont valides et le rendement futur réel
    est connu, on calcule la décision de l'agent (BUY/SELL/HOLD) au regard des
    données disponibles jusqu'à t, puis on la compare au rendement réel sur
    l'horizon. Renvoie des métriques de performance et un échantillon de trades.

    Note : le modèle est entraîné sur l'intégralité de l'historique disponible
    (y compris les points testés), ce qui introduit un léger biais d'optimisme.
    Pour un backtest rigoureux, il faudrait réentraîner sur une fenêtre
    glissante — conservé comme évolution. L'objectif ici est pédagogique :
    illustrer comment on mesure la qualité d'une stratégie.
    """
    closes, volumes, _ = pred._load_history(db, symbol)
    if len(closes) < pred.MIN_HISTORY + horizon:
        raise ValueError(
            f"Historique insuffisant pour {symbol} : {len(closes)} points "
            f"(minimum {pred.MIN_HISTORY + horizon})."
        )

    cached = pred._get_or_train(db, symbol, horizon)
    model = cached.model
    X, y, valid_idx = F.build_feature_matrix(closes, volumes, horizon=horizon)
    if not valid_idx:
        raise ValueError("Aucun point valide pour le backtest.")

    # Imputation des NaN (volumes manquants → moyenne de colonne).
    col_mean = np.nanmean(X[valid_idx], axis=0)
    X_filled = X.copy()
    nan_mask = ~np.isfinite(X_filled)
    X_filled[nan_mask] = np.take(col_mean, np.where(nan_mask)[1])

    # Indicateurs techniques précalculés une fois (gain de temps dans la boucle).
    vol_arr = F.rolling_volatility(closes, 20)
    rsi_arr = F.rsi(closes, 14)
    sma20 = F.sma(closes, 20)
    sma50 = F.sma(closes, 50)

    trades: list[BacktestTrade] = []
    n_buy = n_sell = n_hold = 0
    wins = 0
    total_return = 0.0
    sum_pred = 0.0
    sum_actual = 0.0

    for t in valid_idx:
        predicted = float(model.predict(X_filled[t].reshape(1, -1))[0])
        actual = float(y[t])

        # Volatilité au point t.
        last_vol = float(vol_arr[t]) if np.isfinite(vol_arr[t]) else 0.02
        last_vol = max(last_vol, 0.005)

        # Signal technique au point t (RSI + croisement SMA20/SMA50).
        last_rsi = float(rsi_arr[t]) if np.isfinite(rsi_arr[t]) else 50.0
        tech = 0.0
        if last_rsi < 30:
            tech += 0.4
        elif last_rsi > 70:
            tech -= 0.4
        if np.isfinite(sma20[t]) and np.isfinite(sma50[t]):
            tech += 0.3 if sma20[t] > sma50[t] else -0.3
        tech = max(-1.0, min(1.0, tech))

        # Score composite (sentiment = 0, stub non connecté).
        pred_signal = max(-1.0, min(1.0, predicted / (last_vol * np.sqrt(horizon))))
        composite = max(-1.0, min(1.0, 0.5 * pred_signal + 0.3 * tech))

        if composite > DECISION_THRESHOLD:
            action = "BUY"
        elif composite < -DECISION_THRESHOLD:
            action = "SELL"
        else:
            action = "HOLD"

        correct = False
        if action == "BUY":
            n_buy += 1
            if actual > 0:
                correct = True
                wins += 1
            total_return += actual
        elif action == "SELL":
            n_sell += 1
            if actual < 0:
                correct = True
                wins += 1
            total_return += -actual  # gain d'une position vendeuse
        else:
            n_hold += 1

        sum_pred += predicted
        sum_actual += actual
        trades.append(BacktestTrade(
            index=t, action=action,
            predicted_return=predicted, actual_return=actual, correct=correct,
        ))

    n_directional = n_buy + n_sell
    n_points = len(valid_idx)
    win_rate = wins / n_directional if n_directional > 0 else 0.0
    sample = trades[-max_points:]

    return BacktestResult(
        symbol=symbol,
        horizon=horizon,
        n_points=n_points,
        n_buy=n_buy,
        n_sell=n_sell,
        n_hold=n_hold,
        win_rate=win_rate,
        total_return=total_return,
        avg_predicted=sum_pred / n_points,
        avg_actual=sum_actual / n_points,
        trades=sample,
    )
