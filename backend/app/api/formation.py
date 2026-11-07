from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import User
from app.services import placement

router = APIRouter(prefix="/formation", tags=["formation"])


class PlacementSubmission(BaseModel):
    # {id_question: index de l'option choisie}
    answers: dict[int, int]


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
