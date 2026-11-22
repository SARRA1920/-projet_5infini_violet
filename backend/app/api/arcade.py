"""Salles de jeu : nouvelle section, distincte de la Formation (app.api.formation).

Type 1 : vraie crise BVMT tirée au hasard à chaque partie (app.services.events).
Type 2 : test de stratégie de trading sur une vraie action (app.services.strategy).
Types 3 et 4 : à venir.
"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, EventRun, StrategyRun, User
from app.services import events as event_rooms
from app.services import strategy as strategy_rooms

router = APIRouter(prefix="/salles-de-jeu", tags=["salles-de-jeu"])


def _names(db: Session) -> dict[str, str]:
    return {a.symbol: a.name for a in db.scalars(select(Asset)).all()}


@router.get("/active")
def get_active_runs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Renvoie les tentatives en cours de l'utilisateur (une par type, s'il y en a une).

    Permet au front de proposer de reprendre une partie déjà démarrée plutôt que de
    se contenter de bloquer un nouveau démarrage avec une erreur 409.
    """
    event_run = db.scalars(
        select(EventRun).where(EventRun.user_id == user.id, EventRun.status == "active")
    ).first()
    strategy_run = db.scalars(
        select(StrategyRun).where(StrategyRun.user_id == user.id, StrategyRun.status == "active")
    ).first()
    return {
        "event_run_id": event_run.id if event_run is not None else None,
        "strategy_run_id": strategy_run.id if strategy_run is not None else None,
    }


# ---------- Type 1 : vraie crise tirée au hasard ----------
class EventTradeRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


def _own_event_run(db: Session, run_id: int, user: User) -> EventRun:
    run = db.get(EventRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tentative introuvable")
    return run


@router.get("/events")
def list_events(user: User = Depends(get_current_user)):
    """Catalogue des crises possibles (sans dire laquelle sera tirée)."""
    return event_rooms.list_events()


@router.post("/events/start")
def start_event_run(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Démarre une tentative : une crise est tirée au hasard dans le catalogue."""
    now = datetime.utcnow()
    actives = db.scalars(
        select(EventRun).where(EventRun.user_id == user.id, EventRun.status == "active")
    ).all()
    if actives:
        raise HTTPException(status.HTTP_409_CONFLICT, "Une salle est déjà en cours : termine-la d'abord")
    try:
        run = event_rooms.start_run(user.id, now)
    except event_rooms.RoomError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.add(run)
    db.commit()
    return event_rooms.build_state(run, _names(db))


@router.get("/event-runs/{run_id}")
def get_event_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_event_run(db, run_id, user)
    return event_rooms.build_state(run, _names(db))


@router.post("/event-runs/{run_id}/trade")
def event_run_trade(
    run_id: int,
    body: EventTradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _own_event_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        event_rooms.trade(run, body.symbol, body.side, body.quantity, now)
    except event_rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return event_rooms.build_state(run, _names(db))


@router.post("/event-runs/{run_id}/next")
def event_run_next(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_event_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        event_rooms.advance(run, now)
    except event_rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return event_rooms.build_state(run, _names(db))


# ---------- Type 2 : test de stratégie ----------
class StrategyStartRequest(BaseModel):
    strategy_key: str
    symbol: str


class StrategyTradeRequest(BaseModel):
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


def _own_strategy_run(db: Session, run_id: int, user: User) -> StrategyRun:
    run = db.get(StrategyRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tentative introuvable")
    return run


@router.get("/strategies")
def list_strategies(user: User = Depends(get_current_user)):
    return strategy_rooms.list_strategies()


@router.post("/strategies/start")
def start_strategy_run(
    body: StrategyStartRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    now = datetime.utcnow()
    actives = db.scalars(
        select(StrategyRun).where(StrategyRun.user_id == user.id, StrategyRun.status == "active")
    ).all()
    if actives:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Une salle de stratégie est déjà en cours : termine-la d'abord"
        )
    try:
        run = strategy_rooms.start_run(db, user.id, body.strategy_key, body.symbol, now)
    except strategy_rooms.RoomError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.add(run)
    db.commit()
    return strategy_rooms.build_state(db, run, _names(db).get(run.symbol, run.symbol))


@router.get("/strategy-runs/{run_id}")
def get_strategy_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_strategy_run(db, run_id, user)
    return strategy_rooms.build_state(db, run, _names(db).get(run.symbol, run.symbol))


@router.post("/strategy-runs/{run_id}/trade")
def strategy_run_trade(
    run_id: int,
    body: StrategyTradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _own_strategy_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        strategy_rooms.trade(db, run, body.side, body.quantity, now)
    except strategy_rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return strategy_rooms.build_state(db, run, _names(db).get(run.symbol, run.symbol))


@router.post("/strategy-runs/{run_id}/next")
def strategy_run_next(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_strategy_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        strategy_rooms.advance(db, run, now)
    except strategy_rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return strategy_rooms.build_state(db, run, _names(db).get(run.symbol, run.symbol))
