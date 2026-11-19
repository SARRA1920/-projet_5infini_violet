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
3. **Sentiment** (poids 0.2) : score moyen des titres de news **filtrés**
   (titre pertinent pour le ticker / l'entreprise uniquement).

Corrections apportées au backtest (voir `backtest`) :
- **Plus de fuite de données** : validation *walk-forward* — au jour t, le
  RandomForest n'est entraîné que sur des échantillons dont la cible est
  intégralement réalisée AVANT t (`s + horizon <= t`), jamais sur les
  mêmes jours qu'il évalue. La première version entraînait sur tout
  l'historique puis « testait » sur ces mêmes jours : le modèle
  mémorisait le passé (win rate ~95 % illusoire).
- **Réalisme de l'exécution** : frais de transaction + slippage par côté,
  fraction du capital par position (le capital est bloqué `horizon` jours),
  nombre de positions simultanées limité, vente à découvert interdite par
  défaut (cohérent avec la règle plateforme « vente à découvert
  interdite »), benchmark buy & hold sur la même période, courbe
  d'équité mark-to-market, drawdown maximal et coefficient
  d'information (corrélation de Spearman prédit/réel).
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
    threshold: float = 0.25   # seuil utilisé (affiché par le frontend)


# Seuil de décision : |score| > DECISION_THRESHOLD → BUY ou SELL.
# Relevé de 0.15 à 0.25 (recommandation « adjust decision thresholds ») :
# à 0.15, une prédiction à peine positive + un léger biais technique
# suffisait à déclencher des achats en pleine baisse (jours 128–134 du
# backtest). 0.25 exige un consensus plus net des trois signaux.
DECISION_THRESHOLD = 0.25


def _trend_gate(
    action: str, sma20: float | None, sma50: float | None
) -> tuple[str, bool]:
    """Filtre de tendance : bloque l'achat en tendance baissière confirmée.

    Recommandation « add a trend filter » : SMA20 < SMA50 (cross de mort
    actif) interdit le BUY — c'est exactement le scénario des jours 128–134,
    où le score composite restait légèrement positif pendant que le titre
    chutait de 7,8 %. Symétriquement, le SELL (vente à découvert) est bloqué
    en tendance haussière. Renvoie (action_filtrée, bloquée ?).
    """
    if sma20 is None or sma50 is None or sma20 == sma50:
        return action, False
    if action == "BUY" and sma20 < sma50:
        return "HOLD", True
    if action == "SELL" and sma20 > sma50:
        return "HOLD", True
    return action, False


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

    Combine prédiction IA, signal technique et sentiment. Le sentiment
    n'utilise que des titres pertinents (ticker / nom d'entreprise).
    """
    reasons: list[AgentReason] = []

    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))

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

    # 3. Sentiment (poids 0.2) — titres filtrés par ticker / entreprise.
    titles = sent.fetch_headlines(symbol, company_name=asset.name if asset else None)
    if titles:
        avg_score, label, _ = sent.aggregate_sentiment(titles)
        sent_signal = max(-1.0, min(1.0, avg_score))
        reasons.append(AgentReason(
            signal="sentiment",
            detail=f"{len(titles)} titres pertinents analysés, sentiment {label} (score {avg_score:.2f})",
            contribution=sent_signal * 0.2,
        ))
    else:
        reasons.append(AgentReason(
            signal="sentiment",
            detail="Aucun titre pertinent disponible (source de news non connectée ou filtrage strict)",
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

    # Filtre de tendance : ne jamais acheter en tendance baissière confirmée
    # (ni vendre à découvert en tendance haussière). La décision est ramenée
    # à HOLD avec une raison explicite — l'utilisateur voit POURQUOI l'achat
    # a été bloqué. La confiance est plafonnée à 0.5 : le signal de score
    # reste positif mais la tendance s'y oppose.
    sma20_arr = F.sma(closes, 20)
    sma50_arr = F.sma(closes, 50)
    last_sma20 = float(sma20_arr[-1]) if len(sma20_arr) and np.isfinite(sma20_arr[-1]) else None
    last_sma50 = float(sma50_arr[-1]) if len(sma50_arr) and np.isfinite(sma50_arr[-1]) else None
    action, blocked = _trend_gate(action, last_sma20, last_sma50)
    if blocked:
        direction = "baissière" if last_sma20 < last_sma50 else "haussière"
        blocked_action = "Achat" if composite > 0 else "Vente"
        reasons.append(AgentReason(
            signal="filtre",
            detail=(
                f"Filtre de tendance : {blocked_action.lower()} bloqué — "
                f"SMA20 {'<' if last_sma20 < last_sma50 else '>'} SMA50 "
                f"(tendance {direction} confirmée)"
            ),
            contribution=0.0,
        ))

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
    if blocked:
        confidence = min(confidence, 0.5)

    return AgentDecision(
        symbol=symbol,
        action=action,
        confidence=confidence,
        composite_score=composite,
        reasons=reasons,
        predicted_return=predicted_return,
        horizon=horizon,
        threshold=DECISION_THRESHOLD,
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
# Backtest walk-forward : simule la stratégie sur l'historique passé SANS
# fuite de données, avec coûts de transaction et contraintes de capital.
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    index: int                     # jour t de la décision
    action: str                    # "BUY" | "SELL" | "HOLD"
    predicted_return: float
    actual_return: float
    correct: bool                  # le sens prédit correspond-il au sens réel ?
    train_size: int = 0            # échantillons d'entraînement utilisés au jour t
    train_last_index: int = -1     # dernier indice d'entraînement (<= t - horizon)
    opened: bool = False           # la décision a-t-elle ouvert une position ?
    pnl: float | None = None       # P&L net de la position ouverte (fraction)
    trend_blocked: bool = False    # achat/vente annulés par le filtre de tendance


@dataclass
class BacktestResult:
    symbol: str
    horizon: int
    n_points: int                  # nombre de décisions évaluées (walk-forward)
    n_buy: int
    n_sell: int
    n_hold: int
    win_rate: float                # réussite des signaux directionnels (BUY+SELL)
    total_return: float            # rendement NET de la stratégie (courbe d'équité)
    avg_predicted: float
    avg_actual: float
    trades: list[BacktestTrade]
    # --- Métriques ajoutées par la version walk-forward ---
    buy_hold_return: float = 0.0   # rendement du simple buy & hold sur la période
    final_equity: float = 1.0
    max_drawdown: float = 0.0
    information_coefficient: float = 0.0   # Spearman(prédit, réel)
    fees_paid: float = 0.0
    n_opened: int = 0              # positions réellement ouvertes
    n_skipped: int = 0             # signaux ignorés (slots pleins ou cash insuffisant)
    n_flat: int = 0                # SELL non exécutés (vente à découvert interdite)
    n_trend_blocked: int = 0       # BUY/SELL annulés par le filtre de tendance
    equity_curve: list[tuple[int, float]] = field(default_factory=list)
    buy_hold_curve: list[tuple[int, float]] = field(default_factory=list)
    # Paramètres de la simulation (traçabilité)
    capital_fraction: float = 0.25
    fee_bps: float = 10.0
    slippage_bps: float = 5.0
    retrain_every: int = 5
    allow_short: bool = False


def backtest(
    db: Session,
    symbol: str,
    horizon: int = 5,
    max_points: int = 120,
    *,
    capital_fraction: float = 0.25,
    fee_bps: float = 10.0,
    slippage_bps: float = 5.0,
    retrain_every: int = 5,
    min_train_samples: int = 20,
    allow_short: bool = False,
    n_estimators: int = 200,
) -> BacktestResult:
    """Backtest **walk-forward** de la stratégie de l'agent, sans fuite de données.

    Principe (corrige la fuite de la première version) : au jour t, le modèle
    n'est entraîné que sur les échantillons `s` dont la cible (rendement
    realized sur [s, s+horizon]) est **intégralement connue au jour t**, i.e.
    `s + horizon <= t`. Il ne voit donc jamais le futur qu'il prédit, et la
    performance mesurée est une vraie performance hors échantillon.

    Réalisme de l'exécution :
    - chaque position engage `capital_fraction` de l'équité et bloque ce
      capital pendant `horizon` jours ; les positions simultanées sont
      limitées à `1 / capital_fraction` slots ;
    - frais de courtage + slippage (`fee_bps` + `slippage_bps`, par côté) ;
    - `allow_short=False` (défaut) : un signal SELL ne se traduit pas par une
      position courte — conformément à la règle plateforme « vente à
      découvert interdite », l'agent reste en cash (la qualité de l'appel est
      quand même mesurée dans le win rate) ;
    - benchmark **buy & hold** sur exactement la même fenêtre, pour comparer
      la stratégie à l'alternative triviale.

    Note : le sentiment n'entre pas dans le backtest (pas d'historique de
    news archivé) — le score composite vaut 0.5·prédiction + 0.3·technique.
    """
    closes, volumes, _ = pred._load_history(db, symbol)
    n = len(closes)
    if n < pred.MIN_HISTORY + horizon:
        raise ValueError(
            f"Historique insuffisant pour {symbol} : {n} points "
            f"(minimum {pred.MIN_HISTORY + horizon})."
        )

    X, y, valid_idx = F.build_feature_matrix(closes, volumes, horizon=horizon)
    valid_arr = np.array(valid_idx, dtype=int)
    if len(valid_arr) <= min_train_samples:
        raise ValueError(
            f"Pas assez de points valides pour un backtest walk-forward "
            f"({len(valid_arr)} <= {min_train_samples})."
        )

    # Indicateurs techniques précalculés une fois (regardent tous le PASSÉ
    # uniquement — aucune fuite possible).
    vol_arr = F.rolling_volatility(closes, 20)
    rsi_arr = F.rsi(closes, 14)
    sma20_arr = F.sma(closes, 20)
    sma50_arr = F.sma(closes, 50)

    cost_rate = (fee_bps + slippage_bps) / 10000.0   # coût par côté

    # --- 1. Décisions walk-forward -------------------------------------
    decisions: list[dict] = []
    n_trend_blocked = 0
    model = None
    col_mean: np.ndarray | None = None
    last_fit_t: int | None = None
    last_train_size = 0
    last_train_last = -1

    for t in valid_idx:
        # Échantillons dont la cible est réalisée avant t : s + horizon <= t.
        train_samples = valid_arr[valid_arr + horizon <= t]
        if len(train_samples) < min_train_samples:
            continue  # pas assez de passé : aucune décision (aucune fuite)

        # Réentraînement périodique (fenêtre glissante, coûts maîtrisés).
        if (
            model is None
            or last_fit_t is None
            or (t - last_fit_t) >= retrain_every
        ):
            X_tr = X[train_samples].copy()
            col_mean = np.nanmean(X_tr, axis=0)
            nan_rows, nan_cols = np.where(~np.isfinite(X_tr))
            if nan_rows.size:
                X_tr[nan_rows, nan_cols] = np.take(col_mean, nan_cols)
            model = pred.fit_model(X_tr, y[train_samples], n_estimators=n_estimators)
            last_fit_t = t
            last_train_size = len(train_samples)
            last_train_last = int(train_samples[-1])

        row = X[t].copy()
        bad = ~np.isfinite(row)
        if bad.any():
            # Imputation avec les moyennes de la fenêtre d'entraînement
            # uniquement (pas de statistiques calculées sur le futur).
            row[bad] = np.take(col_mean, np.where(bad)[0])
        predicted = float(model.predict(row.reshape(1, -1))[0])
        actual = float(y[t])

        last_vol = float(vol_arr[t]) if np.isfinite(vol_arr[t]) else 0.02
        last_vol = max(last_vol, 0.005)
        pred_signal = max(-1.0, min(1.0, predicted / (last_vol * np.sqrt(horizon))))

        tech = 0.0
        last_rsi = float(rsi_arr[t]) if np.isfinite(rsi_arr[t]) else 50.0
        if last_rsi < 30:
            tech += 0.4
        elif last_rsi > 70:
            tech -= 0.4
        if np.isfinite(sma20_arr[t]) and np.isfinite(sma50_arr[t]):
            tech += 0.3 if sma20_arr[t] > sma50_arr[t] else -0.3
        tech = max(-1.0, min(1.0, tech))

        composite = max(-1.0, min(1.0, 0.5 * pred_signal + 0.3 * tech))
        if composite > DECISION_THRESHOLD:
            action = "BUY"
        elif composite < -DECISION_THRESHOLD:
            action = "SELL"
        else:
            action = "HOLD"

        # Filtre de tendance (identique à decide()) : pas d'achat quand la
        # SMA20 est sous la SMA50, pas de short au-dessus. La décision est
        # comptabilisée comme HOLD « bloqué » — traçable dans le journal.
        s20 = float(sma20_arr[t]) if np.isfinite(sma20_arr[t]) else None
        s50 = float(sma50_arr[t]) if np.isfinite(sma50_arr[t]) else None
        raw_action = action
        action, blocked = _trend_gate(action, s20, s50)
        if blocked:
            n_trend_blocked += 1

        correct = (
            actual > 0 if action == "BUY" else actual < 0 if action == "SELL" else False
        )
        decisions.append({
            "t": int(t), "action": action, "predicted": predicted,
            "actual": actual, "correct": bool(correct),
            "train_size": last_train_size, "train_last": last_train_last,
            "gated": blocked, "raw_action": raw_action,
        })

    if not decisions:
        raise ValueError(
            "Aucun jour évaluable en walk-forward : augmentez l'historique "
            "ou réduisez min_train_samples."
        )

    n_buy = sum(1 for d in decisions if d["action"] == "BUY")
    n_sell = sum(1 for d in decisions if d["action"] == "SELL")
    n_hold = sum(1 for d in decisions if d["action"] == "HOLD")
    directional = n_buy + n_sell
    wins = sum(1 for d in decisions if d["action"] in ("BUY", "SELL") and d["correct"])
    win_rate = wins / directional if directional else 0.0

    # Coefficient d'information : corrélation de Spearman prédit vs réel.
    predicted_all = np.array([d["predicted"] for d in decisions])
    actual_all = np.array([d["actual"] for d in decisions])
    ic = 0.0
    try:
        from scipy.stats import spearmanr

        if np.std(predicted_all) > 0 and np.std(actual_all) > 0:
            ic = float(spearmanr(predicted_all, actual_all).statistic)
            if np.isnan(ic):
                ic = 0.0
    except ImportError:
        pass

    # --- 2. Simulation de portefeuille (coûts, slots, capital bloqué) ---
    max_slots = max(1, int(round(1.0 / capital_fraction)))
    cash = 1.0
    open_positions: list[dict] = []   # {entry, exit, size, dir}
    equity_curve: list[tuple[int, float]] = []
    fees_paid = 0.0
    n_opened = n_skipped = n_flat = 0
    pnl_by_day: dict[int, float] = {}  # jour d'entrée → P&L net de la position
    dec_by_day = {d["t"]: d for d in decisions}
    first_day, last_day = decisions[0]["t"], decisions[-1]["t"]

    for day in range(first_day, last_day + 1):
        # a) Règlement des positions arrivées à échéance aujourd'hui.
        for pos in [p for p in open_positions if p["exit"] == day]:
            ret = closes[day] / closes[pos["entry"]] - 1.0
            gross = pos["size"] * (1.0 + pos["dir"] * ret)
            proceeds = gross * (1.0 - cost_rate)
            cash += proceeds
            fees_paid += pos["size"] * cost_rate
            # P&L net = produit de sortie − capital engagé (taille + frais d'entrée).
            pnl_by_day[pos["entry"]] = proceeds - pos["size"] * (1.0 + cost_rate)
            open_positions.remove(pos)

        # b) Exécution de la décision du jour (si signal directionnel).
        dec = dec_by_day.get(day)
        if dec is not None and dec["action"] in ("BUY", "SELL"):
            direction = 1.0 if dec["action"] == "BUY" else -1.0
            if direction < 0 and not allow_short:
                n_flat += 1        # short interdit : on reste en cash
            elif len(open_positions) >= max_slots:
                n_skipped += 1     # capital bloqué : signal ignoré
            else:
                equity_now = equity_curve[-1][1] if equity_curve else 1.0
                size = min(capital_fraction * equity_now, cash)
                if size <= 1e-9:
                    n_skipped += 1
                else:
                    cash -= size * (1.0 + cost_rate)
                    fees_paid += size * cost_rate
                    open_positions.append({
                        "entry": day, "exit": day + horizon,
                        "size": size, "dir": direction,
                    })
                    n_opened += 1
                    dec["opened"] = True

        # c) Valeur liquidative mark-to-market.
        mtm = cash
        for pos in open_positions:
            ret_mark = closes[day] / closes[pos["entry"]] - 1.0
            mtm += pos["size"] * (1.0 + pos["dir"] * ret_mark)
        equity_curve.append((day, mtm))

    final_equity = equity_curve[-1][1]
    total_return = final_equity - 1.0
    buy_hold_return = closes[last_day] / closes[first_day] - 1.0

    # Drawdown maximal de la courbe d'équité.
    curve_vals = [v for _, v in equity_curve]
    peak = -np.inf
    max_dd = 0.0
    for v in curve_vals:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak)

    # Courbe buy & hold sur la même fenêtre (base 1.0 au premier jour évalué).
    base = closes[first_day]
    buy_hold_curve = [(day, closes[day] / base) for day, _ in equity_curve]

    # P&L net des positions ouvertes (pour le tableau de trades).
    for d in decisions:
        if d.get("opened"):
            d["pnl"] = pnl_by_day.get(d["t"])

    trades = [
        BacktestTrade(
            index=d["t"], action=d["action"],
            predicted_return=d["predicted"], actual_return=d["actual"],
            correct=d["correct"], train_size=d["train_size"],
            train_last_index=d["train_last"], opened=d.get("opened", False),
            pnl=d.get("pnl"), trend_blocked=d.get("gated", False),
        )
        for d in decisions[-max_points:]
    ]

    return BacktestResult(
        symbol=symbol,
        horizon=horizon,
        n_points=len(decisions),
        n_buy=n_buy,
        n_sell=n_sell,
        n_hold=n_hold,
        win_rate=win_rate,
        total_return=total_return,
        avg_predicted=float(np.mean(predicted_all)),
        avg_actual=float(np.mean(actual_all)),
        trades=trades,
        buy_hold_return=buy_hold_return,
        final_equity=final_equity,
        max_drawdown=max_dd,
        information_coefficient=ic,
        fees_paid=fees_paid,
        n_opened=n_opened,
        n_skipped=n_skipped,
        n_flat=n_flat,
        n_trend_blocked=n_trend_blocked,
        equity_curve=equity_curve,
        buy_hold_curve=buy_hold_curve,
        capital_fraction=capital_fraction,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
        retrain_every=retrain_every,
        allow_short=allow_short,
    )
