"""Routes du module IA, sous /api/ia.

Toutes les routes exigent un utilisateur connecté (get_current_user) et
utilisent le pool de threads de FastAPI (les calculs scikit-learn sont
synchrones et ne bloquent pas la boucle d'événements).

Routes :
- GET  /api/ia/predict/{symbol}?horizon=5   → prédiction de cours
- GET  /api/ia/sentiment/{symbol}           → sentiment des actualités
- POST /api/ia/sentiment/analyze            → analyse d'un texte libre
- GET  /api/ia/agent/{symbol}?horizon=5     → décision de l'agent de trading
- POST /api/ia/retrain/{symbol}?horizon=5   → réentraîner le modèle
- GET  /api/ia/status                       → état du module (scikit-learn dispo ?)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User

from . import prediction as pred
from . import sentiment as sent
from . import agent as agent_mod
from .schemas import (
    AgentDecisionOut,
    AgentReasonOut,
    HeadlineSentimentOut,
    PredictionOut,
    RetrainOut,
    SentimentOut,
)

router = APIRouter(prefix="/api/ia", tags=["ia"])


def _bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)


@router.get("/status")
def ia_status(
    current_user: User = Depends(get_current_user),
):
    """État du module IA : dépendances disponibles et modèle en cache."""
    try:
        import sklearn  # noqa: F401

        sklearn_ok = True
    except ImportError:
        sklearn_ok = False

    return {
        "scikit_learn_available": sklearn_ok,
        "vader_available": sent._VADER_AVAILABLE,
        "cached_models": len(pred._model_cache),
        "min_history": pred.MIN_HISTORY,
    }


@router.get("/predict/{symbol}", response_model=PredictionOut)
def predict(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30, description="Nombre de jours projetés"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Prédit le rendement cumulé sur `horizon` jours pour un actif."""
    try:
        result = pred.predict(db, symbol, horizon=horizon)
    except ValueError as e:
        raise _bad_request(str(e))
    return PredictionOut(
        symbol=result.symbol,
        horizon=result.horizon,
        last_close=result.last_close,
        predicted_return=result.predicted_return,
        predicted_close=result.predicted_close,
        interval_low=result.interval_low,
        interval_high=result.interval_high,
        interval_low_close=result.interval_low_close,
        interval_high_close=result.interval_high_close,
        confidence=result.confidence,
        n_samples=result.n_samples,
    )


class AnalyzeTextIn(BaseModel):
    text: str


@router.post("/sentiment/analyze", response_model=HeadlineSentimentOut)
def analyze_text(
    payload: AnalyzeTextIn,
    current_user: User = Depends(get_current_user),
):
    """Analyse le sentiment d'un texte libre (titre de news, commentaire)."""
    result = sent.analyze_sentiment(payload.text)
    return HeadlineSentimentOut(title=result.text, score=result.score, label=result.label)


@router.get("/sentiment/{symbol}", response_model=SentimentOut)
def sentiment_for_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Renvoie le sentiment agrégé des actualités d'un symbole.

    Pour l'instant, `fetch_headlines` est un stub qui renvoie une liste vide
    tant qu'aucune source de news réelle n'est connectée. Le frontend peut
    utiliser /api/ia/sentiment/analyze pour analyser ses propres textes.
    """
    titles = sent.fetch_headlines(symbol)
    avg, label, details = sent.aggregate_sentiment(titles)
    return SentimentOut(
        symbol=symbol,
        aggregate_score=avg,
        aggregate_label=label,
        headlines=[
            HeadlineSentimentOut(title=d.title, score=d.score, label=d.label)
            for d in details
        ],
        source="vader" if sent._VADER_AVAILABLE else "lexicon",
    )


@router.get("/agent/{symbol}", response_model=AgentDecisionOut)
def agent_decision(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Décision de l'agent de trading (BUY/SELL/HOLD) pour un actif."""
    decision = agent_mod.decide(db, symbol, horizon=horizon)
    return AgentDecisionOut(
        symbol=decision.symbol,
        action=decision.action,
        confidence=decision.confidence,
        composite_score=decision.composite_score,
        predicted_return=decision.predicted_return,
        horizon=decision.horizon,
        reasons=[
            AgentReasonOut(
                signal=r.signal, detail=r.detail, contribution=r.contribution
            )
            for r in decision.reasons
        ],
    )


@router.post("/retrain/{symbol}", response_model=RetrainOut)
def retrain(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Force le réentraînement du modèle de prédiction pour un symbole."""
    try:
        n = pred.retrain(db, symbol, horizon=horizon)
    except ValueError as e:
        raise _bad_request(str(e))
    return RetrainOut(
        symbol=symbol,
        n_samples=n,
        message=f"Modèle réentraîné sur {n} échantillons pour {symbol}.",
    )
