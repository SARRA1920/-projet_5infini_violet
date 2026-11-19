"""Feature engineering pour le module IA.

Fonctions pures : prennent des séries de prix OHLCV (listes de float ou
tableaux numpy) et renvoient des features exploitables par scikit-learn.
Aucun accès à la base de données ici — la lecture de price_history se fait
dans prediction.py et les services.

Les features calculées pour le jour t (à partir des cours jusqu'à t inclus) :
- ret_1, ret_5, ret_10 : rendements sur 1, 5 et 10 jours ;
- sma_20, sma_50 : moyennes mobiles simples (ramenées à un ratio prix/sma) ;
- rsi_14 : RSI de Wilder (0-100) ;
- vol_20 : volatilité réalisée sur 20 jours (écart-type des rendements) ;
- momentum_10 : momentum = P_t / P_(t-10) - 1 ;
- volume_ratio_20 : volume du jour / volume moyen 20 jours.

Features ajoutées pour rendre les baisses VISIBLES du modèle (la première
version ne voyait que des niveaux — le RandomForest prédisait systématiquement
du positif car la cible moyenne d'un titre qui monte est positive, sans jamais
« voir » qu'il était en train de chuter) :
- drawdown_20 : distance au plus haut des 20 derniers jours (≤ 0, fortement
  négatif en pleine chute) ;
- sma20_slope : pente de la SMA20 sur 5 jours (direction de la tendance) ;
- bb_pos : position du prix dans les bandes de Bollinger ((P - SMA20)/(2·σ20),
  négatif sous la bande médiane).

La cible (target) est le rendement cumulé sur les `horizon` jours suivants :
target_t = P_(t+horizon) / P_t - 1.
"""

from __future__ import annotations

import numpy as np


def _to_array(values: list[float]) -> np.ndarray:
    return np.asarray(values, dtype=float)


def simple_returns(prices: list[float]) -> np.ndarray:
    """Rendements simples quotidiens r_t = P_t / P_(t-1) - 1.

    Le premier élément vaut NaN (pas de jour précédent).
    """
    p = _to_array(prices)
    if len(p) < 2:
        return np.full_like(p, np.nan)
    r = np.empty_like(p)
    r[0] = np.nan
    r[1:] = p[1:] / p[:-1] - 1.0
    return r


def sma(prices: list[float], window: int) -> np.ndarray:
    """Moyenne mobile simple ; NaN tant que moins de `window` valeurs."""
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    if len(p) < window:
        return out
    csum = np.cumsum(p)
    csum[window:] = csum[window:] - csum[:-window]
    out[window - 1:] = csum[window - 1:] / window
    return out


def rsi(prices: list[float], period: int = 14) -> np.ndarray:
    """RSI de Wilder (0-100) ; NaN sur les `period` premiers jours.

    Reproduit la logique de app.services.analysis.rsi pour rester cohérent.
    """
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    if len(p) <= period:
        return out
    changes = np.diff(p)
    gains = np.where(changes > 0, changes, 0.0)
    losses = np.where(changes < 0, -changes, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()

    def _to_rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0 if ag > 0 else 50.0
        rs = ag / al
        return 100.0 - 100.0 / (1.0 + rs)

    out[period] = _to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, len(p)):
        g = gains[i - 1]
        l = losses[i - 1]
        avg_gain = (avg_gain * (period - 1) + g) / period
        avg_loss = (avg_loss * (period - 1) + l) / period
        out[i] = _to_rsi(avg_gain, avg_loss)
    return out


def rolling_volatility(prices: list[float], window: int = 20) -> np.ndarray:
    """Écart-type des rendements sur `window` jours (volatilité réalisée).

    NaN-aware : le rendement NaN du premier jour est ignoré (nanstd), donc la
    première fenêtre valide (à l'indice window-1) utilise window-1 rendements.
    """
    r = simple_returns(prices)
    out = np.full_like(r, np.nan)
    if len(r) < window:
        return out
    for i in range(window - 1, len(r)):
        out[i] = np.nanstd(r[i - window + 1 : i + 1], ddof=1)
    return out


def momentum(prices: list[float], window: int = 10) -> np.ndarray:
    """Momentum = P_t / P_(t-window) - 1."""
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    if len(p) <= window:
        return out
    out[window:] = p[window:] / p[:-window] - 1.0
    return out


def rolling_max(prices: list[float], window: int = 20) -> np.ndarray:
    """Plus haut des `window` derniers cours (jour t inclus) ; NaN avant t >= window."""
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    if len(p) < window:
        return out
    for i in range(window - 1, len(p)):
        out[i] = p[i - window + 1 : i + 1].max()
    return out


def drawdown(prices: list[float], window: int = 20) -> np.ndarray:
    """Distance au plus haut des `window` derniers jours : P_t / max(P) - 1.

    Valeur ≤ 0 : 0 au sommet, fortement négatif en pleine chute. C'est la
    feature qui rend la baisse visible du modèle (le prix/sma ne suffit pas :
    il reste positif tant que le prix est au-dessus de sa moyenne, même en
    train de chuter).
    """
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    if len(p) < window:
        return out
    high = rolling_max(p, window)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = p / high - 1.0
    return out


def sma_slope(sma_arr: np.ndarray, lookback: int = 5) -> np.ndarray:
    """Pente relative de la SMA : SMA(t) / SMA(t-lookback) - 1.

    Positive en tendance haussière, négative en tendance baissière. NaN tant
    que la SMA n'est pas définie sur lookback + 1 jours.
    """
    out = np.full_like(sma_arr, np.nan)
    if len(sma_arr) <= lookback:
        return out
    shifted = np.full_like(sma_arr, np.nan)
    shifted[lookback:] = sma_arr[:-lookback]
    with np.errstate(divide="ignore", invalid="ignore"):
        out = sma_arr / shifted - 1.0
    return out


def bollinger_pos(prices: list[float], window: int = 20) -> np.ndarray:
    """Position du prix dans les bandes de Bollinger : (P - SMA) / (2·σ).

    Négatif sous la bande médiane (pression vendeuse), positif au-dessus.
    Convention : σ = 0 (cours parfaitement plats) → 0.0 plutôt que NaN, pour
    ne pas invalider toute la matrice sur les séries peu volatiles.
    """
    p = _to_array(prices)
    out = np.full_like(p, np.nan)
    mid = sma(p, window)
    sigma = rolling_volatility(p, window)
    for i in range(len(p)):
        if np.isfinite(mid[i]) and np.isfinite(sigma[i]):
            out[i] = (p[i] - mid[i]) / (2.0 * sigma[i]) if sigma[i] > 0 else 0.0
    return out


def volume_ratio(volumes: list[float | None], window: int = 20) -> np.ndarray:
    """Volume du jour / volume moyen sur les `window` jours précédents.

    La moyenne exclut le jour courant (définition standard du volume relatif).
    Renvoie NaN si le volume est manquant ou insuffisant. Les volumes None
    sont traités comme NaN.
    """
    v = np.array([float(x) if x is not None else np.nan for x in volumes], dtype=float)
    out = np.full_like(v, np.nan)
    if len(v) <= window:
        return out
    for i in range(window, len(v)):
        window_slice = v[i - window : i]
        if np.all(np.isnan(window_slice)):
            continue
        window_mean = float(np.nanmean(window_slice))
        if window_mean > 0 and not np.isnan(v[i]):
            out[i] = v[i] / window_mean
    return out


FEATURE_COLUMNS = [
    "ret_1",
    "ret_5",
    "ret_10",
    "price_sma20_ratio",
    "price_sma50_ratio",
    "rsi_14",
    "vol_20",
    "momentum_10",
    "volume_ratio_20",
    # Features « visibles de la baisse » (ajout v3 — voir docstring du module).
    "drawdown_20",
    "sma20_slope",
    "bb_pos",
]


def build_feature_matrix(
    closes: list[float],
    volumes: list[float | None] | None = None,
    horizon: int = 5,
) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Construit la matrice de features X et le vecteur cible y.

    Paramètres
    ----------
    closes : cours de clôture ordonnés du plus ancien au plus récent.
    volumes : volumes journaliers (peut contenir des None). Si None, la
        feature volume_ratio_20 vaut NaN (imputée à 1.0 ensuite).
    horizon : nombre de jours futurs pour la cible (rendement cumulé).

    Renvoie
    -------
    X : ndarray de forme (n_samples, len(FEATURE_COLUMNS)).
    y : ndarray de forme (n_samples,) — rendement futur sur `horizon` jours.
    valid_indices : indices des lignes valides (features définies + cible
        définie, i.e. il reste au moins `horizon` jours après t).
    """
    closes_arr = _to_array(closes)
    n = len(closes_arr)
    if volumes is None:
        volumes_arr = np.full(n, np.nan)
    else:
        volumes_arr = np.array(
            [float(x) if x is not None else np.nan for x in volumes], dtype=float
        )

    # Features au niveau jour.
    ret1 = simple_returns(closes)
    ret5 = momentum(closes, 5)  # rendement sur 5 jours = momentum(5)
    ret10 = momentum(closes, 10)
    sma20 = sma(closes, 20)
    sma50 = sma(closes, 50)
    rsi14 = rsi(closes, 14)
    vol20 = rolling_volatility(closes, 20)
    mom10 = momentum(closes, 10)
    vol_ratio = volume_ratio(volumes_arr.tolist(), 20)

    price_sma20 = closes_arr / sma20
    price_sma50 = closes_arr / sma50

    # Features « visibles de la baisse » : drawdown au plus haut récent,
    # pente de la SMA20 et position dans les bandes de Bollinger.
    drawdown_20 = drawdown(closes, 20)
    sma20_slope = sma_slope(sma20, 5)
    bb_pos = bollinger_pos(closes, 20)

    # Cible : rendement cumulé sur `horizon` jours futurs.
    target = np.full(n, np.nan)
    if n > horizon:
        target[: n - horizon] = closes_arr[horizon:] / closes_arr[: n - horizon] - 1.0

    X = np.column_stack(
        [ret1, ret5, ret10, price_sma20, price_sma50, rsi14, vol20, mom10,
         vol_ratio, drawdown_20, sma20_slope, bb_pos]
    )
    y = target

    # Lignes valides : toutes les features définies + cible définie.
    feature_finite = np.all(np.isfinite(X), axis=1)
    target_finite = np.isfinite(y)
    valid_mask = feature_finite & target_finite
    valid_indices = np.where(valid_mask)[0].tolist()
    return X, y, valid_indices
