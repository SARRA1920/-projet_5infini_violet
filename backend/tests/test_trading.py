"""Tests for the trading engine: place_order (buy, sell, validations)."""
from decimal import Decimal

import pytest

from app.models.models import Position, Transaction, TransactionSide
from app.services.trading import (
    InsufficientFundsError,
    InsufficientPositionError,
    InvalidOrderError,
    PortfolioNotFoundError,
    place_order,
)


# ============================================================
# BUYS
# ============================================================

class TestBuy:
    def test_buy_creates_new_position(self, db, seed_data):
        """A buy creates a new position with the correct average price."""
        portfolio = seed_data["portfolio"]

        tx = place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
        )
        db.commit()

        assert tx.side == TransactionSide.BUY
        assert tx.quantity == Decimal("10")
        assert tx.price == Decimal("172")

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position is not None
        assert position.quantity == Decimal("10")
        assert position.average_buy_price == Decimal("172")
        assert position.is_open is True

    def test_buy_deducts_cash(self, db, seed_data):
        """A buy deducts the exact amount from cash."""
        portfolio = seed_data["portfolio"]
        cash_before = portfolio.cash_balance

        place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
        )
        db.commit()

        expected_cost = Decimal("10") * Decimal("172")
        assert portfolio.cash_balance == cash_before - expected_cost

    def test_buy_insufficient_funds(self, db, seed_data):
        """A buy with insufficient cash raises an error."""
        portfolio = seed_data["portfolio"]

        with pytest.raises(InsufficientFundsError):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.BUY,
                quantity=Decimal("100000"),
            )

    def test_buy_updates_existing_position_average(self, db, seed_data):
        """A second buy updates the average buy price."""
        portfolio = seed_data["portfolio"]

        # First buy: 10 @ 172
        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        # Add a new price entry for the second buy
        from app.models.models import PriceHistory
        from datetime import date, timedelta
        db.add(PriceHistory(
            asset_id=seed_data["aapl"].id,
            date=date.today() + timedelta(days=1),
            open=Decimal("180"), high=Decimal("185"),
            low=Decimal("178"), close=Decimal("180"), volume=2000000,
        ))
        db.flush()

        # Second buy: 10 @ 180
        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.quantity == Decimal("20")
        # Average = (10*172 + 10*180) / 20 = 176
        assert position.average_buy_price == Decimal("176.0000")

    def test_buy_with_stop_loss_and_take_profit(self, db, seed_data):
        """SL and TP are recorded on both the transaction AND the position."""
        portfolio = seed_data["portfolio"]

        tx = place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
            stop_loss=Decimal("160"),
            take_profit=Decimal("190"),
        )
        db.commit()

        # Check transaction
        assert tx.stop_loss == Decimal("160.0000")
        assert tx.take_profit == Decimal("190.0000")

        # Check position
        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.stop_loss == Decimal("160.0000")
        assert position.take_profit == Decimal("190.0000")

    def test_buy_stop_loss_must_be_below_price(self, db, seed_data):
        """Stop loss must be below the current price."""
        portfolio = seed_data["portfolio"]

        with pytest.raises(InvalidOrderError, match="stop loss"):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.BUY,
                quantity=Decimal("10"),
                stop_loss=Decimal("200"),
            )

    def test_buy_take_profit_must_be_above_price(self, db, seed_data):
        """Take profit must be above the current price."""
        portfolio = seed_data["portfolio"]

        with pytest.raises(InvalidOrderError, match="take profit"):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.BUY,
                quantity=Decimal("10"),
                take_profit=Decimal("150"),
            )

    def test_second_buy_without_sl_tp_keeps_old_values(self, db, seed_data):
        """A second buy without SL/TP keeps the old SL/TP on the position."""
        portfolio = seed_data["portfolio"]

        # First buy with SL/TP
        place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
            stop_loss=Decimal("160"),
            take_profit=Decimal("190"),
        )
        db.commit()

        # Second buy without SL/TP
        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("5"))
        db.commit()

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.quantity == Decimal("15")
        # Old SL/TP should still be there
        assert position.stop_loss == Decimal("160.0000")
        assert position.take_profit == Decimal("190.0000")

    def test_second_buy_with_new_sl_tp_overwrites_old(self, db, seed_data):
        """A second buy with new SL/TP overwrites the old values."""
        portfolio = seed_data["portfolio"]

        # First buy with SL=160, TP=190
        place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
            stop_loss=Decimal("160"),
            take_profit=Decimal("190"),
        )
        db.commit()

        # Second buy with SL=155, TP=195
        place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("5"),
            stop_loss=Decimal("155"),
            take_profit=Decimal("195"),
        )
        db.commit()

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.stop_loss == Decimal("155.0000")
        assert position.take_profit == Decimal("195.0000")


# ============================================================
# SELLS
# ============================================================

class TestSell:
    def test_sell_success(self, db, seed_data):
        """A successful sell adds cash and reduces the position."""
        portfolio = seed_data["portfolio"]

        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()
        cash_after_buy = portfolio.cash_balance

        tx = place_order(db, portfolio.id, "AAPL", TransactionSide.SELL, quantity=Decimal("5"))
        db.commit()

        expected_revenue = Decimal("5") * Decimal("172")
        assert portfolio.cash_balance == cash_after_buy + expected_revenue

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.quantity == Decimal("5")

    def test_sell_insufficient_position(self, db, seed_data):
        """Selling more than you own raises an error."""
        portfolio = seed_data["portfolio"]

        with pytest.raises(InsufficientPositionError):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.SELL,
                quantity=Decimal("10"),
            )

    def test_sell_closes_position_and_clears_sl_tp(self, db, seed_data):
        """When you sell everything, the position is closed and SL/TP are cleared."""
        portfolio = seed_data["portfolio"]

        # Buy with SL/TP
        place_order(
            db, portfolio.id, "AAPL", TransactionSide.BUY,
            quantity=Decimal("10"),
            stop_loss=Decimal("160"),
            take_profit=Decimal("190"),
        )
        db.commit()

        # Sell everything
        place_order(db, portfolio.id, "AAPL", TransactionSide.SELL, quantity=Decimal("10"))
        db.commit()

        position = db.query(Position).filter_by(portfolio_id=portfolio.id).first()
        assert position.quantity == Decimal("0")
        assert position.is_open is False
        assert position.closed_at is not None
        # SL/TP should be cleared
        assert position.stop_loss is None
        assert position.take_profit is None

    def test_sell_cannot_have_stop_loss(self, db, seed_data):
        """A sell cannot have a stop loss."""
        portfolio = seed_data["portfolio"]

        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        with pytest.raises(InvalidOrderError, match="Stop loss"):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.SELL,
                quantity=Decimal("5"),
                stop_loss=Decimal("160"),
            )


# ============================================================
# GENERAL VALIDATIONS
# ============================================================

class TestValidations:
    def test_zero_quantity_rejected(self, db, seed_data):
        """A quantity of 0 is rejected."""
        portfolio = seed_data["portfolio"]

        with pytest.raises(InvalidOrderError, match="strictement positive"):
            place_order(
                db, portfolio.id, "AAPL", TransactionSide.BUY,
                quantity=Decimal("0"),
            )

    def test_unknown_portfolio(self, db, seed_data):
        """A non-existent portfolio raises an error."""
        with pytest.raises(PortfolioNotFoundError):
            place_order(
                db, 99999, "AAPL", TransactionSide.BUY,
                quantity=Decimal("10"),
            )

    def test_transaction_is_recorded(self, db, seed_data):
        """Each order creates an entry in the transactions table."""
        portfolio = seed_data["portfolio"]

        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        txs = db.query(Transaction).filter_by(portfolio_id=portfolio.id).all()
        assert len(txs) == 1
        assert txs[0].side == TransactionSide.BUY
        assert txs[0].quantity == Decimal("10")