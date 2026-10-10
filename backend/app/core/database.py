import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# L'URL vient d'une variable d'environnement (définie dans docker-compose.yml).
# Le nom d'hôte "db" correspond au nom du service PostgreSQL dans docker-compose.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:password@db:5432/salle_marche",
)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    """Classe de base dont héritent tous les modèles."""


def get_db():
    """Dépendance FastAPI : ouvre une session, la ferme à la fin de la requête."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
