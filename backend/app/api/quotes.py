import logging

from fastapi import APIRouter, HTTPException

from app.services.quotes import live_quotes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("")
def quotes():
    """Derniers cours enregistrés par l'import Twelve Data (price_history)."""
    try:
        return live_quotes()
    except Exception as exc:
        logger.exception("Lecture des cours impossible")
        raise HTTPException(status_code=502, detail="Cours indisponibles") from exc
