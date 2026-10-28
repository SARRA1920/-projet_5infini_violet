from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, Portfolio, Position, Transaction, User
from app.schemas.trading import OrderRequest, PortfolioOut, PositionOut, TransactionOut
from app.services.prices import PriceUnavailableError, get_current_price
from app.services.trading import (
    CASH_STEP,
    InsufficientFundsError,
    InsufficientPositionError,
    InvalidOrderError,
    PortfolioNotFoundError,
    place_order,
)

router = APIRouter(prefix="/trading", tags=["trading"])


def _user_portfolio(db: Session, user: User) -> Portfolio:
    """Premier portefeuille (par id) de l'utilisateur connecté."""
    portfolio = db.scalar(
        select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id).limit(1)
    )
    if portfolio is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aucun portefeuille")
    return portfolio


def _money(value: Decimal) -> Decimal:
    return value.quantize(CASH_STEP, rounding=ROUND_HALF_UP)


def _transaction_out(transaction: Transaction) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        symbol=transaction.asset.symbol,
        side=transaction.side,
        quantity=transaction.quantity,
        price=transaction.price,
        stop_loss=transaction.stop_loss,
        take_profit=transaction.take_profit,
        realized_pnl=transaction.realized_pnl,
        executed_at=transaction.executed_at,
    )


@router.post("/orders", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def create_order(
    body: OrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Passe un ordre au marché sur le portefeuille de l'utilisateur connecté."""
    portfolio = _user_portfolio(db, current_user)
    try:
        transaction = place_order(
            db,
            portfolio.id,
            body.symbol,
            body.side,
            body.quantity,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
    except (InvalidOrderError, InsufficientFundsError, InsufficientPositionError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except (PriceUnavailableError, PortfolioNotFoundError) as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    db.commit()
    db.refresh(transaction)
    return _transaction_out(transaction)


@router.get("/portfolio", response_model=PortfolioOut)
def get_portfolio(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cash et positions ouvertes valorisées au dernier cours connu."""
    portfolio = _user_portfolio(db, current_user)
    rows = db.execute(
        select(Position, Asset)
        .join(Asset, Position.asset_id == Asset.id)
        .where(Position.portfolio_id == portfolio.id, Position.is_open.is_(True))
        .order_by(Asset.symbol)
    ).all()

    positions = []
    positions_value = Decimal("0.00")
    complete = True
    for position, asset in rows:
        out = PositionOut(
            symbol=asset.symbol,
            name=asset.name,
            quantity=position.quantity,
            average_buy_price=position.average_buy_price,
            current_price=None,
            market_value=None,
            unrealized_pnl=None,
            unrealized_pnl_pct=None,
        )
        try:
            price = get_current_price(db, asset.symbol)
        except PriceUnavailableError as exc:
            out.price_error = str(exc)
            complete = False
        else:
            cost = position.quantity * position.average_buy_price
            out.current_price = price
            out.market_value = _money(position.quantity * price)
            out.unrealized_pnl = _money(position.quantity * price - cost)
            if position.average_buy_price:
                out.unrealized_pnl_pct = _money(
                    (price - position.average_buy_price) / position.average_buy_price * 100
                )
            positions_value += out.market_value
        positions.append(out)

    return PortfolioOut(
        cash=portfolio.cash_balance,
        positions=positions,
        positions_value=positions_value,
        total_value=portfolio.cash_balance + positions_value,
        valuation_complete=complete,
    )


@router.get("/transactions", response_model=list[TransactionOut])
def transactions(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Historique des ordres du portefeuille, du plus récent au plus ancien."""
    portfolio = _user_portfolio(db, current_user)
    rows = db.scalars(
        select(Transaction)
        .options(joinedload(Transaction.asset))
        .where(Transaction.portfolio_id == portfolio.id)
        .order_by(Transaction.executed_at.desc(), Transaction.id.desc())
        .limit(limit)
    ).all()
    return [_transaction_out(t) for t in rows]
