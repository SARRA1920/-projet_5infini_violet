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
