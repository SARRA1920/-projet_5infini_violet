from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import Portfolio, User, UserRole
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Crée un compte et son portefeuille (100 000 de cash)."""
    email = body.email.lower()
    username = body.username.strip()

    existing = db.scalar(
        select(User).where(or_(User.email == email, User.username == username))
    )
    if existing is not None:
        if existing.email == email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cet e-mail est déjà utilisé")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ce nom d'utilisateur est déjà utilisé",
        )

    user = User(
        email=email,
        username=username,
        hashed_password=hash_password(body.password),
        role=UserRole.USER,
    )
    user.portfolios.append(Portfolio())
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="E-mail ou nom d'utilisateur déjà utilisé",
        )
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """Vérifie e-mail et mot de passe, puis renvoie un jeton JWT."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou mot de passe incorrect",
        )
    return TokenResponse(access_token=create_access_token(user.id, user.role.value))


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)):
    """Identité portée par le jeton. Sert à vérifier qu'il est valide."""
    return current_user
