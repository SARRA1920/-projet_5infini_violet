from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class ShockKind(str, Enum):
    CREDIT = "credit"
    REAL_ESTATE = "real_estate"


class BankOut(BaseModel):
    id: int
    name: str
    bank_type: str
    total_loans: Decimal
    total_deposits: Decimal
    equity_capital: Decimal
    real_estate_share: Decimal
    capital_ratio: Decimal


class StressRequest(BaseModel):
    shock: ShockKind
    # Pourcentage d'intensité : 10 signifie 10 %.
    intensity: Decimal = Field(ge=0, le=100)


class StressRow(BaseModel):
    name: str
    bank_type: str
    loss: Decimal
    equity_before: Decimal
    equity_after: Decimal
    ratio_before: Decimal
    ratio_after: Decimal | None
    below_threshold: bool


class StressResult(BaseModel):
    shock: ShockKind
    intensity: Decimal
    threshold: Decimal
    below_count: int
    results: list[StressRow]
