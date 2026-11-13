from fastapi import APIRouter, Depends

from app.api.deps import require_admin
from app.models.models import User

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/session")
def admin_session(admin: User = Depends(require_admin)):
    """Confirme que le jeton appartient à un administrateur."""
    role = getattr(admin.role, "value", admin.role)
    return {"username": admin.username, "email": admin.email, "role": role}
