from decimal import ROUND_HALF_UP, Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.models import Asset, Portfolio, Position, Transaction, TransactionSide, User
from app.schemas.trading import (
    OrderPreviewOut,
    OrderRequest,
    PortfolioOut,
    PositionOut,
    RiskOut,
    TransactionOut,
)
from app.services.prices import PriceUnavailableError, get_current_price
from app.services.risk import (
    INITIAL_CASH,
    annualized_volatility,
    historical_var,
    max_drawdown,
    order_warnings,
    portfolio_daily_returns,
)
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


def _pct(value: float | None) -> Decimal | None:
    """Fraction -> pourcentage arrondi à 2 décimales (0.0184 -> 1.84)."""
    if value is None:
        return None
    return _money(Decimal(str(value * 100)))


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


@router.post("/orders/preview", response_model=OrderPreviewOut)
def preview_order(
    body: OrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Simule un ordre (rien n'est enregistré) et signale les risques éventuels."""
    try:
        price = get_current_price(db, body.symbol).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    except PriceUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    snapshot = get_portfolio(db=db, current_user=current_user)
    symbol = body.symbol.strip().upper()
    value_before = next(
        (p.market_value or Decimal("0") for p in snapshot.positions if p.symbol == symbol),
        Decimal("0"),
    )
    amount = _money(body.quantity * price)
    is_buy = body.side == TransactionSide.BUY
    asset_weight, cash_weight, warnings = order_warnings(
        is_buy, amount, snapshot.cash, snapshot.total_value, value_before
    )
    if not snapshot.valuation_complete:
        warnings.append("Certaines positions n'ont pas de cours : les pourcentages sont approximatifs.")
    return OrderPreviewOut(
        symbol=symbol,
        side=body.side,
        quantity=body.quantity,
        price=price,
        amount=amount,
        cash_after=snapshot.cash - amount if is_buy else snapshot.cash + amount,
        asset_weight_pct=_money(asset_weight * 100),
        cash_weight_pct=_money(cash_weight * 100),
        warnings=warnings,
    )


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


@router.get("/risk", response_model=RiskOut)
def get_risk(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Performance et indicateurs de risque du portefeuille de l'utilisateur connecté."""
    portfolio = _user_portfolio(db, current_user)
    total_value = get_portfolio(db=db, current_user=current_user).total_value
    returns = [daily for _, daily in portfolio_daily_returns(db, portfolio.id)]
    volatility = annualized_volatility(returns)
    var_95 = historical_var(returns, 0.95)
    drawdown = max_drawdown(returns)
    realized = db.scalar(
        select(func.coalesce(func.sum(Transaction.realized_pnl), 0)).where(
            Transaction.portfolio_id == portfolio.id
        )
    )
    return RiskOut(
        total_value=total_value,
        initial_capital=INITIAL_CASH,
        total_return_pct=_money((total_value / INITIAL_CASH - 1) * 100),
        realized_pnl_total=_money(Decimal(realized)),
        days_used=len(returns),
        volatility_pct=_pct(volatility),
        var_95_pct=_pct(var_95),
        var_95_amount=None if var_95 is None else _money(Decimal(str(var_95)) * total_value),
        max_drawdown_pct=_pct(drawdown),
        max_drawdown_amount=None if drawdown is None else _money(Decimal(str(drawdown)) * total_value),
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
