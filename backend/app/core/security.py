import os
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8


def hash_password(password: str) -> str:
    """Hache un mot de passe avec Argon2."""
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Vérifie un mot de passe. Un hash invalide compte comme un échec."""
    try:
        return password_hash.verify(password, hashed)
    except Exception:
        return False


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET manquant : ajoutez-le dans le fichier .env")
    return secret


def create_access_token(user_id: int, role: str) -> str:
    """Jeton d'identité, valable 8 heures. Il ne contient ni cash ni positions."""
    expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, _jwt_secret(), algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Décode un jeton. Lève jwt.PyJWTError s'il est invalide ou expiré."""
    return jwt.decode(token, _jwt_secret(), algorithms=[ALGORITHM])
