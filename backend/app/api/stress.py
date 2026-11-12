from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Bank, User
from app.schemas.stress import BankOut, StressRequest, StressResult, StressRow
from app.services.stress import CAPITAL_THRESHOLD, apply_shock

router = APIRouter(prefix="/stress", tags=["stress"])


def _bank_out(bank: Bank) -> BankOut:
    return BankOut(
        id=bank.id,
        name=bank.name,
        bank_type=bank.bank_type.value,
        total_loans=bank.total_loans,
        total_deposits=bank.total_deposits,
        equity_capital=bank.equity_capital,
        real_estate_share=bank.real_estate_share,
        capital_ratio=bank.capital_ratio,
    )


@router.get("/banks", response_model=list[BankOut])
def list_banks(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Banques synthétiques, dans l'ordre du nom."""
    banks = db.scalars(select(Bank).order_by(Bank.name)).all()
    return [_bank_out(bank) for bank in banks]


@router.post("/run", response_model=StressResult)
def run_stress(
    body: StressRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Applique un choc à toutes les banques. La base n'est pas modifiée."""
    banks = db.scalars(select(Bank).order_by(Bank.name)).all()
    rows = [StressRow(**apply_shock(bank, body.shock.value, body.intensity)) for bank in banks]
    return StressResult(
        shock=body.shock,
        intensity=body.intensity,
        threshold=(CAPITAL_THRESHOLD * 100),
        below_count=sum(1 for row in rows if row.below_threshold),
        results=rows,
    )
