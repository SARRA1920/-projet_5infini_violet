"""Routes du module IA, sous /api/ia.

Toutes les routes exigent un utilisateur connecté (get_current_user) et
utilisent le pool de threads de FastAPI (les calculs scikit-learn sont
synchrones et ne bloquent pas la boucle d'événements).

Routes :
- GET  /api/ia/predict/{symbol}?horizon=5   → prédiction de cours
- GET  /api/ia/sentiment/{symbol}           → sentiment des actualités (titres filtrés)
- POST /api/ia/sentiment/analyze            → analyse d'un texte libre (FR/EN)
- GET  /api/ia/agent/{symbol}?horizon=5     → décision de l'agent de trading
- GET  /api/ia/backtest/{symbol}            → backtest walk-forward (sans fuite de données)
- GET  /api/ia/diagnostics/{symbol}         → diagnostic du modèle (IC, biais, calibration)
- POST /api/ia/retrain/{symbol}?horizon=5   → réentraîner le modèle
- GET  /api/ia/status                       → état du module (scikit-learn dispo ?)
- GET  /api/ia/news/live?limit=20           → fil d'actualités en direct (pop-ups)
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, User

from . import prediction as pred
from . import sentiment as sent
from . import agent as agent_mod
from . import news_feed
from .schemas import (
    AgentDecisionOut,
    AgentReasonOut,
    BacktestEquityPointOut,
    BacktestOut,
    BacktestTradeOut,
    CalibrationBucketOut,
    DiagnosticsOut,
    FeatureICOut,
    FeatureImportanceItemOut,
    FeatureImportanceOut,
    HeadlineSentimentOut,
    NewsFeedOut,
    NewsItemOut,
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
    """Analyse le sentiment d'un texte libre (titre de news, commentaire).

    Multilingue : lexique financier FR si le texte est français (VADER ne
    comprend pas le français), VADER ou lexique financier EN sinon. Le champ
    `source` indique le moteur réellement utilisé.
    """
    result = sent.analyze_sentiment(payload.text)
    return HeadlineSentimentOut(
        title=result.text, score=result.score, label=result.label, source=result.source
    )


@router.get("/sentiment/{symbol}", response_model=SentimentOut)
def sentiment_for_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Renvoie le sentiment agrégé des actualités d'un symbole.

    Les titres sont récupérés (RSS Yahoo Finance, repli Google News) puis
    **filtrés par alias** : seul un titre mentionnant le ticker ou un mot
    significatif du nom de l'entreprise est analysé — les actualités hors
    sujet (SpaceX, Walmart…) ne polluent plus le score. Le scoring est
    multilingue : lexique financier FR pour le français, VADER pour
    l'anglais.
    """
    asset = db.scalar(select(Asset).where(Asset.symbol == symbol.strip().upper()))
    titles = sent.fetch_headlines(symbol, company_name=asset.name if asset else None)
    avg, label, details = sent.aggregate_sentiment(titles)
    aggregate_source = details[0].source if details else ("vader" if sent._VADER_AVAILABLE else "lexicon")
    return SentimentOut(
        symbol=symbol,
        aggregate_score=avg,
        aggregate_label=label,
        headlines=[
            HeadlineSentimentOut(
                title=d.title, score=d.score, label=d.label, source=d.source
            )
            for d in details
        ],
        source=aggregate_source,
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
        threshold=decision.threshold,
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


@router.get("/feature-importance/{symbol}", response_model=FeatureImportanceOut)
def feature_importance(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Importance des features du modèle entraîné pour un actif.

    Renvoie, pour chaque feature technique (RSI, SMA, rendements…), son poids
    dans le RandomForest. La somme des importances vaut 1. Tri décroissant.
    """
    try:
        features = pred.feature_importance(db, symbol, horizon=horizon)
    except ValueError as e:
        raise _bad_request(str(e))
    return FeatureImportanceOut(
        symbol=symbol.upper(),
        horizon=horizon,
        features=[
            FeatureImportanceItemOut(name=f["name"], importance=f["importance"])
            for f in features
        ],
    )


@router.get("/diagnostics/{symbol}", response_model=DiagnosticsOut)
def diagnostics(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Diagnostic du modèle : pourquoi prédit-il (presque) toujours du positif ?

    - **feature_ic** : corrélation de Spearman de chaque feature avec le
      rendement futur — une feature dont l'IC est ≈ 0 est du bruit, même si
      son importance RandomForest est élevée (elle sert à mémoriser, pas à
      généraliser) ;
    - **biais de signe** : part de prédictions positives vs part de cibles
      positives — met en évidence l'asymétrie de la cible d'entraînement ;
    - **calibration** : moyenne du rendement réel par quintile de prédiction ;
      si elle croît de Q1 à Q5, le classement est informatif même avec un
      biais de niveau.
    """
    try:
        diag = pred.model_diagnostics(db, symbol, horizon=horizon)
    except ValueError as e:
        raise _bad_request(str(e))
    return DiagnosticsOut(
        symbol=diag.symbol,
        horizon=diag.horizon,
        n_samples=diag.n_samples,
        feature_importance=[
            FeatureImportanceItemOut(name=f["name"], importance=f["importance"])
            for f in diag.feature_importance
        ],
        feature_ic=[
            FeatureICOut(name=f["name"], ic=f["ic"]) for f in diag.feature_ic
        ],
        mean_predicted=diag.mean_predicted,
        mean_actual=diag.mean_actual,
        pct_predicted_positive=diag.pct_predicted_positive,
        pct_actual_positive=diag.pct_actual_positive,
        calibration=[
            CalibrationBucketOut(
                bucket=b.bucket, n=b.n,
                mean_predicted=b.mean_predicted, mean_actual=b.mean_actual,
            )
            for b in diag.calibration
        ],
    )


@router.get("/news/live", response_model=NewsFeedOut)
def news_live(
    limit: int = Query(20, ge=1, le=50, description="Nombre d'actualités renvoyées"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fil d'actualités **en direct** : marché + actifs suivis, avec sentiment.

    Agrège le flux RSS « Top Stories » de Yahoo Finance (actualités générales
    du marché) et les flux par actif récupérés **par rotation** (au plus 3
    sources par appel, caches 20 min) — la politesse réseau est garantie même
    avec de nombreux utilisateurs connectés. Chaque titre reçoit un id stable,
    les tickers mentionnés ([] = news marché) et un score de sentiment calculé
    par le moteur multilingue de `sentiment.py`. Le fil agrégé est partagé en
    cache 90 s : rafraîchir la page ne re-fetch jamais les sources RSS.
    """
    items = news_feed.live_news(db, limit=limit)
    return NewsFeedOut(
        updated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        items=[
            NewsItemOut(
                id=i.id,
                title=i.title,
                link=i.link,
                symbols=i.symbols,
                score=i.score,
                label=i.label,
                source=i.source,
                published=i.published.isoformat() if i.published else None,
            )
            for i in items
        ],
    )


@router.get("/backtest/{symbol}", response_model=BacktestOut)
def backtest(
    symbol: str,
    horizon: int = Query(5, ge=1, le=30),
    max_points: int = Query(120, ge=10, le=500),
    capital_fraction: float = Query(0.25, ge=0.05, le=1.0, description="Fraction du capital par position"),
    fee_bps: float = Query(10.0, ge=0.0, le=100.0, description="Frais de transaction (points de base par côté)"),
    slippage_bps: float = Query(5.0, ge=0.0, le=100.0, description="Slippage (points de base par côté)"),
    retrain_every: int = Query(5, ge=1, le=60, description="Réentraînement du modèle tous les N jours"),
    allow_short: bool = Query(False, description="Autoriser la vente à découvert (désactivé par défaut)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backtest **walk-forward** de la stratégie d'agent, sans fuite de données.

    Au jour t, le modèle n'est entraîné que sur les échantillons dont la
    cible est réalisée avant t (jamais sur les jours qu'il évalue). La
    simulation tient compte des frais de transaction, du slippage, du
    capital bloqué par position (limité à `1 / capital_fraction` positions
    simultanées) et interdit la vente à découvert par défaut — conformément
    aux règles de la plateforme. Le rendement est comparé au buy & hold sur
    la même période.
    """
    try:
        result = agent_mod.backtest(
            db,
            symbol,
            horizon=horizon,
            max_points=max_points,
            capital_fraction=capital_fraction,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            retrain_every=retrain_every,
            allow_short=allow_short,
        )
    except ValueError as e:
        raise _bad_request(str(e))
    return BacktestOut(
        symbol=result.symbol,
        horizon=result.horizon,
        n_points=result.n_points,
        n_buy=result.n_buy,
        n_sell=result.n_sell,
        n_hold=result.n_hold,
        win_rate=result.win_rate,
        total_return=result.total_return,
        avg_predicted=result.avg_predicted,
        avg_actual=result.avg_actual,
        trades=[
            BacktestTradeOut(
                index=t.index,
                action=t.action,
                predicted_return=t.predicted_return,
                actual_return=t.actual_return,
                correct=t.correct,
                train_size=t.train_size,
                train_last_index=t.train_last_index,
                opened=t.opened,
                pnl=t.pnl,
                trend_blocked=t.trend_blocked,
            )
            for t in result.trades
        ],
        buy_hold_return=result.buy_hold_return,
        final_equity=result.final_equity,
        max_drawdown=result.max_drawdown,
        information_coefficient=result.information_coefficient,
        fees_paid=result.fees_paid,
        n_opened=result.n_opened,
        n_skipped=result.n_skipped,
        n_flat=result.n_flat,
        n_trend_blocked=result.n_trend_blocked,
        equity_curve=[
            BacktestEquityPointOut(day=day, strategy=value, buy_hold=bh)
            for (day, value), (_, bh) in zip(result.equity_curve, result.buy_hold_curve)
        ],
        capital_fraction=result.capital_fraction,
        fee_bps=result.fee_bps,
        slippage_bps=result.slippage_bps,
        retrain_every=result.retrain_every,
        allow_short=result.allow_short,
    )
