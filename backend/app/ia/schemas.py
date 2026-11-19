"""Schémas Pydantic pour les réponses du module IA."""

from pydantic import BaseModel, Field


class PredictionPointOut(BaseModel):
    """Un point de la prévision (pour le graphique frontend)."""

    label: str = Field(..., description="Étiquette temporelle, ex 'J+5'")
    value: float = Field(..., description="Prix projeté")


class PredictionOut(BaseModel):
    """Résultat d'une prédiction de cours."""

    symbol: str
    horizon: int = Field(..., description="Nombre de jours projetés")
    last_close: float = Field(..., description="Dernier cours connu")
    predicted_return: float = Field(..., description="Rendement prédit en fraction (0.023 = +2,3%)")
    predicted_close: float = Field(..., description="Prix projeté")
    interval_low: float = Field(..., description="Borne basse du rendement (quantile 10%)")
    interval_high: float = Field(..., description="Borne haute du rendement (quantile 90%)")
    interval_low_close: float
    interval_high_close: float
    confidence: float = Field(..., description="Score de confiance 0-1")
    n_samples: int = Field(..., description="Taille de l'échantillon d'entraînement")


class HeadlineSentimentOut(BaseModel):
    """Sentiment d'un titre ou d'un texte libre."""

    title: str
    score: float = Field(..., description="-1 (négatif) à +1 (positif)")
    label: str = Field(..., description="'positif' | 'neutre' | 'négatif'")
    source: str | None = Field(
        None, description="Moteur utilisé : 'vader' | 'lexicon' | 'lexicon-fr'"
    )


class SentimentOut(BaseModel):
    """Résultat de l'analyse de sentiment pour un actif."""

    symbol: str
    aggregate_score: float
    aggregate_label: str
    headlines: list[HeadlineSentimentOut]
    source: str = Field(..., description="'vader' ou 'lexicon'")


class AgentReasonOut(BaseModel):
    signal: str
    detail: str
    contribution: float


class AgentDecisionOut(BaseModel):
    """Décision de l'agent de trading."""

    symbol: str
    action: str = Field(..., description="'BUY' | 'SELL' | 'HOLD'")
    confidence: float = Field(..., description="0.0 - 1.0")
    composite_score: float = Field(..., description="-1.0 à +1.0")
    predicted_return: float
    horizon: int
    reasons: list[AgentReasonOut]
    threshold: float = Field(
        0.25, description="Seuil de décision utilisé (affiché tel quel par le frontend)"
    )


class RetrainOut(BaseModel):
    """Résultat d'un réentraînement forcé."""

    symbol: str
    n_samples: int
    message: str


class FeatureImportanceItemOut(BaseModel):
    """Une feature et son importance (somme des importances = 1)."""

    name: str
    importance: float = Field(..., description="Importance normalisée (somme = 1)")


class FeatureImportanceOut(BaseModel):
    """Importance des features du modèle RandomForest pour un actif."""

    symbol: str
    horizon: int
    features: list[FeatureImportanceItemOut]


class FeatureICOut(BaseModel):
    """Corrélation de Spearman d'une feature avec le rendement futur."""

    name: str
    ic: float = Field(
        -1.0, description="-1 à +1 ; |IC| proche de 0 = feature non informative"
    )


class CalibrationBucketOut(BaseModel):
    """Moyenne réelle par quintile de prédiction (calibration du classement)."""

    bucket: str = Field(..., description="'Q1' (prédictions basses) … 'Q5' (hautes)")
    n: int
    mean_predicted: float
    mean_actual: float


class DiagnosticsOut(BaseModel):
    """Diagnostic du modèle : IC par feature, biais de signe, calibration.

    Répond à la question « pourquoi le RandomForest prédit-il (presque)
    toujours du positif ? » : la moyenne de la cible d'entraînement est
    positive (titre historiquement montant), et le régresseur recentre ses
    prédictions autour. Les champs mesurent ce biais et la qualité du
    classement indépendamment du niveau.
    """

    symbol: str
    horizon: int
    n_samples: int = Field(..., description="Échantillons d'entraînement analysés")
    feature_importance: list[FeatureImportanceItemOut]
    feature_ic: list[FeatureICOut]
    mean_predicted: float = Field(..., description="Moyenne des prédictions (in-sample)")
    mean_actual: float = Field(..., description="Moyenne des cibles réelles")
    pct_predicted_positive: float = Field(
        ..., description="Part de prédictions > 0 (0-1)"
    )
    pct_actual_positive: float = Field(..., description="Part de cibles > 0 (0-1)")
    calibration: list[CalibrationBucketOut]


class BacktestTradeOut(BaseModel):
    """Un trade simulé du backtest (décision walk-forward)."""

    index: int
    action: str = Field(..., description="'BUY' | 'SELL' | 'HOLD'")
    predicted_return: float
    actual_return: float
    correct: bool = Field(..., description="Le sens prédit correspond-il au sens réel ?")
    train_size: int = Field(0, description="Échantillons d'entraînement disponibles au jour t")
    train_last_index: int = Field(
        -1,
        description="Dernier indice d'entraînement ; garantit train_last_index + horizon <= index (pas de fuite)",
    )
    opened: bool = Field(False, description="La décision a-t-elle ouvert une position ?")
    pnl: float | None = Field(None, description="P&L net de la position (frais inclus), si ouverte")
    trend_blocked: bool = Field(
        False, description="Achat/vente annulés par le filtre de tendance (SMA20 vs SMA50)"
    )


class BacktestEquityPointOut(BaseModel):
    """Un point des courbes d'équité (base 1.0 au premier jour évalué)."""

    day: int
    strategy: float = Field(..., description="Équité de la stratégie (frais inclus)")
    buy_hold: float = Field(..., description="Équité du buy & hold sur la même période")


class BacktestOut(BaseModel):
    """Résultat du backtest walk-forward de la stratégie d'agent."""

    symbol: str
    horizon: int
    n_points: int = Field(..., description="Nombre de décisions évaluées hors échantillon")
    n_buy: int
    n_sell: int
    n_hold: int
    win_rate: float = Field(..., description="Taux de réussite des signaux directionnels")
    total_return: float = Field(..., description="Rendement NET de la stratégie (frais inclus)")
    avg_predicted: float
    avg_actual: float
    trades: list[BacktestTradeOut]
    # --- Métriques walk-forward et réalisme ---
    buy_hold_return: float = Field(0.0, description="Rendement du buy & hold sur la même période")
    final_equity: float = Field(1.0, description="Équité finale (départ = 1.0)")
    max_drawdown: float = Field(0.0, description="Drawdown maximal de la courbe d'équité (fraction)")
    information_coefficient: float = Field(
        0.0, description="Corrélation de Spearman entre rendements prédits et réels"
    )
    fees_paid: float = Field(0.0, description="Frais + slippage payés (fraction de l'équité initiale)")
    n_opened: int = Field(0, description="Positions réellement ouvertes")
    n_skipped: int = Field(0, description="Signaux ignorés (slots pleins ou cash insuffisant)")
    n_flat: int = Field(0, description="Signaux SELL restés en cash (vente à découvert interdite)")
    n_trend_blocked: int = Field(
        0, description="Signaux BUY/SELL annulés par le filtre de tendance"
    )
    equity_curve: list[BacktestEquityPointOut] = Field(
        default_factory=list, description="Courbes d'équité stratégie vs buy & hold"
    )
    capital_fraction: float = Field(0.25, description="Fraction du capital par position")
    fee_bps: float = Field(10.0, description="Frais de transaction (points de base par côté)")
    slippage_bps: float = Field(5.0, description="Slippage (points de base par côté)")
    retrain_every: int = Field(5, description="Réentraînement du modèle tous les N jours")
    allow_short: bool = Field(False, description="Vente à découvert autorisée ?")
