import enum
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


# ---------- Énumérations ----------
class UserRole(str, enum.Enum):
    USER = "user"
    ADMIN = "admin"


class AssetType(str, enum.Enum):
    STOCK = "stock"          # actions
    BOND = "bond"            # obligations
    COMMODITY = "commodity"  # matières premières
    FOREX = "forex"          # devises


class TransactionSide(str, enum.Enum):
    BUY = "buy"
    SELL = "sell"


class BankType(str, enum.Enum):
    CONVENTIONAL = "conventional"
    NON_CONVENTIONAL = "non_conventional"


# ---------- Utilisateurs ----------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolios: Mapped[list["Portfolio"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------- Actifs financiers ----------
class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True)  # ex: AAPL
    name: Mapped[str] = mapped_column(String(150))
    asset_type: Mapped[AssetType] = mapped_column(Enum(AssetType))


# ---------- Historique de cours (données de marché journalières) ----------
class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("asset_id", "date", name="uq_price_asset_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    date: Mapped[date_type] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    asset: Mapped["Asset"] = relationship()


# ---------- Portefeuille ----------
class Portfolio(Base):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(100), default="Portefeuille principal")
    cash_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("100000.00"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="portfolios")
    positions: Mapped[list["Position"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="portfolio", cascade="all, delete-orphan"
    )


# ---------- Position : état actuel d'un actif dans un portefeuille ----------
class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("portfolio_id", "asset_id", name="uq_portfolio_asset"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("0"))
    average_buy_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), default=Decimal("0"))
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    portfolio: Mapped["Portfolio"] = relationship(back_populates="positions")
    asset: Mapped["Asset"] = relationship()


# ---------- Transaction : historique immuable des ordres ----------
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    side: Mapped[TransactionSide] = mapped_column(Enum(TransactionSide))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    portfolio: Mapped["Portfolio"] = relationship(back_populates="transactions")
    asset: Mapped["Asset"] = relationship()


# ---------- Banque synthétique (module Stress Testing) ----------
class Bank(Base):
    __tablename__ = "banks"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150), unique=True)
    bank_type: Mapped[BankType] = mapped_column(Enum(BankType))
    total_loans: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_deposits: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    equity_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    real_estate_share: Mapped[Decimal] = mapped_column(Numeric(5, 4))  # part des actifs, ex: 0.35
    capital_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4))      # ratio de solvabilité
