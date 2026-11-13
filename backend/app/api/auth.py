import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.mail import MailDeliveryError, MailNotConfiguredError, send_password_reset
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import PasswordReset, Portfolio, User, UserRole
from app.schemas.auth import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)

RESET_TOKEN_MINUTES = 30

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


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Envoie un lien à usage unique. Le jeton n'est pas renvoyé dans la réponse."""
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun compte avec cet e-mail")

    now = _now()
    pending = db.scalars(
        select(PasswordReset).where(
            PasswordReset.user_id == user.id,
            PasswordReset.used_at.is_(None),
        )
    ).all()
    for old in pending:
        old.used_at = now

    token = secrets.token_urlsafe(32)
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=_token_hash(token),
            expires_at=now + timedelta(minutes=RESET_TOKEN_MINUTES),
        )
    )
    try:
        send_password_reset(user.email, token)
    except MailNotConfiguredError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="L'envoi d'e-mail n'est pas configuré.",
        )
    except MailDeliveryError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="L'e-mail n'a pas pu être envoyé. Réessayez dans un moment.",
        )
    db.commit()
    return ForgotPasswordResponse(detail="Un e-mail vient d'être envoyé. Ouvrez le lien qu'il contient.")


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    """Remplace le mot de passe si le code est encore valable, puis l'invalide."""
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == _token_hash(body.reset_token)))
    now = _now()
    if reset is None or reset.used_at is not None or reset.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ce code n'est plus valable. Recommencez depuis « Mot de passe oublié ».",
        )
    user = db.get(User, reset.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Compte introuvable")
    user.hashed_password = hash_password(body.password)
    reset.used_at = now
    db.commit()


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)):
    """Identité portée par le jeton. Sert à vérifier qu'il est valide."""
    return current_user
