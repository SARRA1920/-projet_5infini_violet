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
    """Sentiment d'un titre de news."""

    title: str
    score: float = Field(..., description="-1 (négatif) à +1 (positif)")
    label: str = Field(..., description="'positif' | 'neutre' | 'négatif'")


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


class RetrainOut(BaseModel):
    """Résultat d'un réentraînement forcé."""

    symbol: str
    n_samples: int
    message: str
