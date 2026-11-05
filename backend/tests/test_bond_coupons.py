"""Tests for the bond coupon service: pay_daily_bond_coupons."""
from decimal import Decimal

from app.models.models import Position
from app.services.bond_service import pay_daily_bond_coupons
from app.services.trading import place_order
from app.models.models import TransactionSide


class TestBondCoupons:
    def test_pays_coupon_to_bond_holders(self, db, seed_data):
        """A portfolio holding bonds receives interest."""
        portfolio = seed_data["portfolio"]

        # Buy 100 TLT @ 95 = 9,500 invested
        place_order(db, portfolio.id, "TLT", TransactionSide.BUY, quantity=Decimal("100"))
        db.commit()

        cash_before = portfolio.cash_balance

        pay_daily_bond_coupons(db)

        # Daily interest = 9500 * (0.04 / 365) ≈ 1.04
        assert portfolio.cash_balance > cash_before

        interest = portfolio.cash_balance - cash_before
        expected_min = Decimal("9500") * Decimal("0.04") / Decimal("365") - Decimal("0.01")
        expected_max = Decimal("9500") * Decimal("0.04") / Decimal("365") + Decimal("0.01")
        assert expected_min <= interest <= expected_max

    def test_no_coupon_for_stock_holders(self, db, seed_data):
        """A portfolio holding only stocks receives nothing."""
        portfolio = seed_data["portfolio"]

        place_order(db, portfolio.id, "AAPL", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        cash_before = portfolio.cash_balance

        paid_count, total_paid = pay_daily_bond_coupons(db)

        assert paid_count == 0
        assert total_paid == Decimal("0.00")
        assert portfolio.cash_balance == cash_before

    def test_no_coupon_for_empty_portfolio(self, db, seed_data):
        """A portfolio with no positions receives nothing."""
        portfolio = seed_data["portfolio"]
        cash_before = portfolio.cash_balance

        paid_count, total_paid = pay_daily_bond_coupons(db)

        assert paid_count == 0
        assert portfolio.cash_balance == cash_before

    def test_coupon_amount_proportional_to_holding(self, db, seed_data):
        """The more bonds you hold, the more interest you receive."""
        portfolio = seed_data["portfolio"]

        # Small buy: 10 TLT @ 95 = 950
        place_order(db, portfolio.id, "TLT", TransactionSide.BUY, quantity=Decimal("10"))
        db.commit()

        paid_count_1, total_paid_1 = pay_daily_bond_coupons(db)

        # Large buy: 1000 TLT @ 95 = 95,000
        place_order(db, portfolio.id, "TLT", TransactionSide.BUY, quantity=Decimal("1000"))
        db.commit()

        paid_count_2, total_paid_2 = pay_daily_bond_coupons(db)

        # The second payment must be much larger
        assert total_paid_2 > total_paid_1 * 10