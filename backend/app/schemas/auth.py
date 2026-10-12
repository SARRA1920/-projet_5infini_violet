from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.models import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    """Utilisateur renvoyé par l'API, sans le mot de passe."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    username: str
    role: UserRole


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
