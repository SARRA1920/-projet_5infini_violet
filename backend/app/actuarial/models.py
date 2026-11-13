"""Tables propres au module Actuariat (ajoutées par migration, sans toucher aux tables existantes).

Types portables (JSON et non JSONB) : les tests tournent sur SQLite en mémoire.
"""

from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Provenance d'une donnée ou d'un résultat, affichée à l'utilisateur.
DATA_SOURCES = (
    "real_market_data",  # cours importés (price_history) et positions réelles du simulateur
    "synthetic",  # données générées, clairement identifiées comme telles
    "user_assumption",  # paramètres saisis par l'utilisateur
    "simulated",  # sortie d'un modèle (Monte Carlo, trajectoires…)
)


class ActuarialRun(Base):
    """Calcul lancé par un utilisateur : paramètres, graine et résumé des résultats.

    Sert à l'historique du laboratoire de modèles et à la reproductibilité
    (même modèle + mêmes paramètres + même graine = même résultat).
    """

    __tablename__ = "actuarial_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    portfolio_id: Mapped[int | None] = mapped_column(
        ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(40))
    params: Mapped[dict] = mapped_column(JSON)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_source: Mapped[str] = mapped_column(String(30))
    summary: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class BondTerms(Base):
    """Caractéristiques contractuelles d'une obligation présente dans `assets`.

    Table vide par défaut : une ligne n'est ajoutée que si les caractéristiques
    sont connues, avec leur provenance dans `source`. Rien n'est déduit ni inventé.
    """

    __tablename__ = "bond_terms"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), unique=True)
    face_value: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    coupon_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6))  # 0.045 pour 4,5 % par an
    coupon_frequency: Mapped[int] = mapped_column(Integer)  # versements par an : 1, 2, 4, 12
    issue_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    maturity_date: Mapped[date_type] = mapped_column(Date)
    day_count: Mapped[str] = mapped_column(String(20), default="ACT/365")
    source: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
