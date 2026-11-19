"""Prédiction de cours : entraînement et inférence.

Pipeline :
1. Lire l'historique de price_history pour un symbole (closes + volumes).
2. Construire la matrice de features via features.build_feature_matrix.
3. Entraîner un RandomForestRegressor sur la cible (rendement futur).
4. Prédire le rendement sur `horizon` jours à partir de la dernière ligne.
5. Estimer un intervalle de confiance via les arbres (quantiles 10/90).

Le modèle est entraîné à la demande et mis en cache en mémoire par symbole.
Pour un projet pédagogique avec peu d'historique, c'est suffisant et évite
la gestion de fichiers .joblib. Un endpoint /api/ia/retrain/{symbol} permet
de forcer le réentraînement.

Si l'historique est trop court (< MIN_HISTORY points) ou scikit-learn absent,
on renvoie une erreur explicite plutôt qu'un résultat trompeur.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset, PriceHistory

from . import features as F

# Seuil minimal d'historique pour entraîner un modèle crédible.
# Relevé de 60 à 120 (recommandation « expand training data ») : 60 points
# ne couvrent qu'un seul régime de marché — le RandomForest apprend alors
# par cœur la seule tendance qu'il a vue. 120 points (~6 mois) permettent
# d'observer au moins deux régimes (hausse + correction).
MIN_HISTORY = 120
# Durée de vie du cache modèle en secondes (10 minutes).
CACHE_TTL = 600


@dataclass
class _CachedModel:
    model: object
    last_close: float
    last_features: np.ndarray
    trained_at: float
    n_samples: int


_model_cache: dict[str, _CachedModel] = {}


def _get_sklearn():
    """Import scikit-learn paresseusement pour garder le module importable
    même si la dépendance n'est pas installée (tests unitaires sur features)."""
    from sklearn.ensemble import RandomForestRegressor

    return RandomForestRegressor


def _load_history(db: Session, symbol: str) -> tuple[list[float], list[float | None], Asset]:
    """Charge les cours de clôture et volumes ordonnés pour un symbole."""
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    if asset is None:
        raise ValueError(f"Actif inconnu : {symbol}")

    rows = db.execute(
        select(PriceHistory.date, PriceHistory.close, PriceHistory.volume)
        .where(PriceHistory.asset_id == asset.id)
        .order_by(PriceHistory.date)
    ).all()
    if len(rows) < 2:
        raise ValueError(f"Pas assez d'historique pour {symbol} ({len(rows)} points)")

    closes = [float(r.close) for r in rows]
    volumes = [float(r.volume) if r.volume is not None else None for r in rows]
    return closes, volumes, asset


# Hyper-paramètres du RandomForest, partagés entre la prédiction en direct
# et le backtest walk-forward (un seul endroit à ajuster).
MODEL_PARAMS = {
    "max_depth": 8,
    "min_samples_leaf": 5,
    "random_state": 42,
    "n_jobs": -1,
}


def fit_model(X_train: np.ndarray, y_train: np.ndarray, n_estimators: int = 200):
    """Entraîne un RandomForestRegressor sur les échantillons fournis.

    Utilisé par prediction._train (historique complet) et par le backtest
    walk-forward de agent.py (fenêtre glissante : uniquement le passé). Les
    imputations de NaN doivent être faites par l'appelant AVANT l'appel.
    """
    RF = _get_sklearn()
    model = RF(n_estimators=n_estimators, **MODEL_PARAMS)
    model.fit(X_train, y_train)
    return model


def _train(closes: list[float], volumes: list[float | None], horizon: int) -> _CachedModel:
    """Entraîne le RandomForest sur l'historique donné."""
    X, y, valid_idx = F.build_feature_matrix(closes, volumes, horizon=horizon)
    if len(valid_idx) < 20:
        raise ValueError(
            f"Pas assez d'échantillons entraînement après feature engineering "
            f"({len(valid_idx)} < 20). Historique trop court ou trop de NaN."
        )
    X_train = X[valid_idx]
    y_train = y[valid_idx]

    # Imputation : les volumes manquants deviennent 1.0 (volume moyen).
    col_mean = np.nanmean(X_train, axis=0)
    inds = np.where(np.isnan(X_train))
    X_train = X_train.copy()
    X_train[inds] = np.take(col_mean, inds[1])

    model = fit_model(X_train, y_train)

    # Dernière ligne de features pour la prédiction immédiate.
    last_row = X[-1].copy()
    nan_mask = ~np.isfinite(last_row)
    if nan_mask.any():
        last_row[nan_mask] = col_mean[nan_mask]

    return _CachedModel(
        model=model,
        last_close=closes[-1],
        last_features=last_row,
        trained_at=time.time(),
        n_samples=len(valid_idx),
    )


def _get_or_train(db: Session, symbol: str, horizon: int) -> _CachedModel:
    """Récupère le modèle en cache ou entraîne s'il est absent/expiré."""
    cache_key = f"{symbol}:{horizon}"
    cached = _model_cache.get(cache_key)
    if cached is not None and (time.time() - cached.trained_at) < CACHE_TTL:
        return cached

    closes, volumes, _ = _load_history(db, symbol)
    if len(closes) < MIN_HISTORY:
        raise ValueError(
            f"Historique insuffisant pour {symbol} : {len(closes)} points "
            f"(minimum {MIN_HISTORY}). Importez plus de données."
        )
    model = _train(closes, volumes, horizon)
    _model_cache[cache_key] = model
    return model


@dataclass
class PredictionResult:
    symbol: str
    horizon: int
    last_close: float
    predicted_return: float       # fraction, ex 0.023 = +2,3 %
    predicted_close: float        # prix projeté
    interval_low: float           # quantile 10 % du rendement
    interval_high: float          # quantile 90 % du rendement
    interval_low_close: float
    interval_high_close: float
    confidence: float             # 0-1, basé sur la cohérence des arbres
    n_samples: int                # taille de l'échantillon d'entraînement


def predict(db: Session, symbol: str, horizon: int = 5) -> PredictionResult:
    """Prédit le rendement cumulé sur `horizon` jours pour `symbol`."""
    if horizon < 1 or horizon > 30:
        raise ValueError("horizon doit être entre 1 et 30 jours")
    cached = _get_or_train(db, symbol, horizon)

    model = cached.model
    x = cached.last_features.reshape(1, -1)

    # Prédiction ponctuelle (moyenne des arbres).
    point_pred = float(model.predict(x)[0])

    # Distribution des arbres pour l'intervalle de confiance.
    tree_preds = np.array([t.predict(x)[0] for t in model.estimators_])
    q_low = float(np.percentile(tree_preds, 10))
    q_high = float(np.percentile(tree_preds, 90))

    # Confiance : inverse de la dispersion des arbres (normalisée).
    spread = q_high - q_low
    confidence = float(max(0.0, min(1.0, 1.0 - spread * 5.0)))

    last_close = cached.last_close
    return PredictionResult(
        symbol=symbol,
        horizon=horizon,
        last_close=last_close,
        predicted_return=point_pred,
        predicted_close=last_close * (1.0 + point_pred),
        interval_low=q_low,
        interval_high=q_high,
        interval_low_close=last_close * (1.0 + q_low),
        interval_high_close=last_close * (1.0 + q_high),
        confidence=confidence,
        n_samples=cached.n_samples,
    )


def retrain(db: Session, symbol: str, horizon: int = 5) -> int:
    """Force le réentraînement du modèle pour un symbole. Renvoie n_samples."""
    closes, volumes, _ = _load_history(db, symbol)
    if len(closes) < MIN_HISTORY:
        raise ValueError(
            f"Historique insuffisant pour {symbol} : {len(closes)} points "
            f"(minimum {MIN_HISTORY})."
        )
    model = _train(closes, volumes, horizon)
    _model_cache[f"{symbol}:{horizon}"] = model
    return model.n_samples


def clear_cache() -> None:
    """Vide le cache des modèles (utile pour les tests)."""
    _model_cache.clear()


def feature_importance(db: Session, symbol: str, horizon: int = 5) -> list[dict]:
    """Renvoie l'importance de chaque feature pour le modèle entraîné.

    Les importances proviennent de ``model.feature_importances_`` (RandomForest) :
    elles mesurent à quel point chaque feature réduit l'impureté moyenne sur
    l'ensemble des 200 arbres. La somme vaut 1. Les features sont triées par
    importance décroissante pour un affichage immédiat sous forme de barres.
    """
    cached = _get_or_train(db, symbol, horizon)
    importances = cached.model.feature_importances_
    pairs = sorted(
        zip(F.FEATURE_COLUMNS, importances.tolist()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return [{"name": name, "importance": float(val)} for name, val in pairs]


@dataclass
class CalibrationBucket:
    bucket: str          # "Q1" .. "Q5" (quintile de prédiction)
    n: int
    mean_predicted: float
    mean_actual: float


@dataclass
class ModelDiagnostics:
    """Diagnostic du modèle : pourquoi prédit-il (presque) toujours du positif ?

    Répond à la recommandation « re-evaluate features » avec des mesures
    concrètes plutôt qu'à l'intuition :
    - feature_ic : corrélation de Spearman de chaque feature avec le rendement
      futur, sur l'échantillon d'entraînement — montre quelles features sont
      réellement informatives (|IC| proche de 0 → bruit) ;
    - biais de signe : moyenne des prédictions vs moyenne des cibles, et part
      de prédictions positives vs part de cibles positives. La cause racine du
      « toujours positif » est l'asymétrie de la cible : sur un titre qui a
      monté, la moyenne des rendements futurs est positive, et un régresseur
      recentre ses prédictions autour de cette moyenne ;
    - calibration par quintile : le modèle classe-t-il correctement ? Si la
      moyenne réelle croît du quintile Q1 (prédictions basses) à Q5 (hautes),
      le classement est utile même avec un biais de niveau.
    """

    symbol: str
    horizon: int
    n_samples: int
    feature_importance: list[dict]
    feature_ic: list[dict]           # {"name", "ic"} trié par |IC| décroissant
    mean_predicted: float
    mean_actual: float
    pct_predicted_positive: float
    pct_actual_positive: float
    calibration: list[CalibrationBucket]


def model_diagnostics(db: Session, symbol: str, horizon: int = 5) -> ModelDiagnostics:
    """Analyse le modèle entraîné : IC par feature, biais de signe, calibration."""
    from scipy.stats import spearmanr

    cached = _get_or_train(db, symbol, horizon)
    closes, volumes, _ = _load_history(db, symbol)
    X, y, valid_idx = F.build_feature_matrix(closes, volumes, horizon=horizon)
    X_valid = X[valid_idx]
    y_valid = y[valid_idx]

    # IC de Spearman feature → rendement futur (échantillon d'entraînement).
    ics = []
    for j, name in enumerate(F.FEATURE_COLUMNS):
        col = X_valid[:, j]
        if np.std(col) == 0:
            ic = 0.0
        else:
            rho = spearmanr(col, y_valid).statistic
            ic = 0.0 if np.isnan(rho) else float(rho)
        ics.append({"name": name, "ic": ic})
    ics.sort(key=lambda d: abs(d["ic"]), reverse=True)

    # Biais de signe : prédictions in-sample vs cibles réelles.
    preds = cached.model.predict(X_valid)
    pct_pred_pos = float(np.mean(preds > 0))
    pct_actual_pos = float(np.mean(y_valid > 0))

    # Calibration par quintile de prédiction.
    order = np.argsort(preds)
    buckets = []
    n = len(preds)
    for q in range(5):
        sel = order[q * n // 5 : (q + 1) * n // 5]
        if len(sel) == 0:
            continue
        buckets.append(CalibrationBucket(
            bucket=f"Q{q + 1}",
            n=int(len(sel)),
            mean_predicted=float(np.mean(preds[sel])),
            mean_actual=float(np.mean(y_valid[sel])),
        ))

    importances = cached.model.feature_importances_
    pairs = sorted(
        zip(F.FEATURE_COLUMNS, importances.tolist()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    return ModelDiagnostics(
        symbol=symbol,
        horizon=horizon,
        n_samples=len(valid_idx),
        feature_importance=[
            {"name": name, "importance": float(val)} for name, val in pairs
        ],
        feature_ic=ics,
        mean_predicted=float(np.mean(preds)),
        mean_actual=float(np.mean(y_valid)),
        pct_predicted_positive=pct_pred_pos,
        pct_actual_positive=pct_actual_pos,
        calibration=buckets,
    )
