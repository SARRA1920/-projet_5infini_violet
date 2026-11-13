from datetime import datetime

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, CrisisRun, User, UserRole
from app.services import crisis as rooms
from app.services import placement, progression

router = APIRouter(prefix="/formation", tags=["formation"])


class PlacementSubmission(BaseModel):
    # {id_question: index de l'option choisie}
    answers: dict[int, int]


@router.post("/guide/seen")
def mark_guide_seen(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Marque le guide d'accueil comme vu (terminé ou passé). Sans effet si déjà fait."""
    if user.guide_seen_at is None:
        user.guide_seen_at = datetime.utcnow()
        db.commit()
    return {"guide_seen_at": user.guide_seen_at}


@router.get("/placement")
def get_placement(user: User = Depends(get_current_user)):
    """Glossaire et questions du QCM (sans les réponses)."""
    return {"already_done": user.level is not None, "level": user.level, **placement.public_quiz()}


@router.post("/placement")
def submit_placement(
    body: PlacementSubmission,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Note le QCM et enregistre le niveau. Une seule passation par utilisateur."""
    if user.level is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Le test de niveau a déjà été passé")
    result = placement.grade(body.answers)
    user.level = result["level"]
    user.placement_score = result["score"]
    user.placement_done_at = datetime.utcnow()
    db.commit()
    return result


# ---------- Salles de crise ----------
class TradeRequest(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    quantity: float = Field(gt=0)


def _is_admin(user: User) -> bool:
    return getattr(user.role, "value", user.role) == UserRole.ADMIN.value


def _require_placed(user: User) -> None:
    if not _is_admin(user) and user.level is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passe d'abord le test de niveau")


def _names(db: Session) -> dict[str, str]:
    return {a.symbol: a.name for a in db.scalars(select(Asset)).all()}


def _own_run(db: Session, run_id: int, user: User) -> CrisisRun:
    run = db.get(CrisisRun, run_id)
    if run is None or run.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tentative introuvable")
    if rooms.expire_if_needed(run, datetime.utcnow()):
        db.commit()
    return run


@router.get("/rooms")
def list_rooms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_placed(user)
    now = datetime.utcnow()
    runs = db.scalars(select(CrisisRun).where(CrisisRun.user_id == user.id)).all()
    for r in runs:
        rooms.expire_if_needed(r, now)
    db.commit()
    result = []
    for key in rooms.list_keys():
        crisis = rooms.load_crisis(key)
        mine = [r for r in runs if r.crisis_key == key]
        done = [r for r in mine if r.status != "active" and r.score is not None]
        validated = any(progression.is_validating(r) for r in mine)
        active = next((r for r in mine if r.status == "active"), None)
        meta = crisis["meta"]
        result.append(
            {
                "key": key,
                "name": meta["name"],
                "level": meta["level"],
                "story": meta["story"],
                "total_days": len(crisis["calendar"]),
                "time_limit_seconds": rooms.time_limit_seconds(crisis),
                "start": crisis["calendar"][0],
                "end": crisis["calendar"][-1],
                "locked": not rooms.can_enter(user.level, _is_admin(user), crisis),
                "attempts": len(done),
                "best_score": max((r.score for r in done), default=None),
                "active_run_id": active.id if active else None,
                "validated": validated,
            }
        )
    return result


@router.post("/rooms/{key}/start")
def start_room(key: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Entre dans une salle : reprend la tentative en cours, ou en crée une nouvelle."""
    _require_placed(user)
    now = datetime.utcnow()
    try:
        crisis = rooms.load_crisis(key)
    except rooms.RoomError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if not rooms.can_enter(user.level, _is_admin(user), crisis):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cette salle est réservée à un niveau supérieur")

    actives = db.scalars(
        select(CrisisRun).where(CrisisRun.user_id == user.id, CrisisRun.status == "active")
    ).all()
    for r in actives:
        rooms.expire_if_needed(r, now)
    for r in actives:
        if r.status == "active":
            if r.crisis_key == key:
                db.commit()
                return rooms.build_state(r, now, _names(db))
            raise HTTPException(status.HTTP_409_CONFLICT, "Une autre salle est déjà en cours : termine-la d'abord")

    run = rooms.start_run(user.id, key, now)
    db.add(run)
    db.commit()
    return rooms.build_state(run, now, _names(db))


@router.get("/runs/{run_id}")
def get_run(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(db, run_id, user)
    return rooms.build_state(run, datetime.utcnow(), _names(db))


@router.post("/runs/{run_id}/trade")
def run_trade(
    run_id: int,
    body: TradeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    run = _own_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        rooms.trade(run, body.symbol, body.side, body.quantity, now)
    except rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    db.commit()
    return rooms.build_state(run, now, _names(db))


@router.post("/runs/{run_id}/next")
def run_next(run_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    run = _own_run(db, run_id, user)
    now = datetime.utcnow()
    try:
        rooms.advance(run, now)
    except rooms.RoomError as exc:
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    promotion = None
    if run.status == "finished" and not _is_admin(user):
        all_runs = db.scalars(select(CrisisRun).where(CrisisRun.user_id == user.id)).all()
        promotion = progression.apply_promotion(user, all_runs)
    db.commit()
    state = rooms.build_state(run, now, _names(db))
    if promotion:
        state["promotion"] = promotion
    return state


@router.get("/progress")
def get_progress(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Avancement vers le niveau suivant : salles validées parmi celles du niveau actuel."""
    _require_placed(user)
    runs = db.scalars(select(CrisisRun).where(CrisisRun.user_id == user.id)).all()
    return progression.progress(user.level, runs)


@router.get("/leaderboard")
def get_leaderboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Classement général et par salle (tentatives terminées, tous les joueurs avec leur pseudo)."""
    return progression.leaderboard(db, user.id)
