import traceback
from fastapi import APIRouter, HTTPException

from app.services.quotes import live_quotes

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("")
def quotes():
    """Derniers cours enregistrés par l'import Twelve Data (price_history)."""
    try:
        return live_quotes()
    except Exception as exc:
        print(traceback.format_exc()) # <--- ADD THIS LINE
        raise HTTPException(status_code=502, detail="Cours indisponibles") from exc