"""Tests de la simulation d'ordre : avertissements d'exposition et de liquidités."""
from decimal import Decimal

import pytest

from app.services.risk import MAX_SINGLE_ASSET_WEIGHT, MIN_CASH_WEIGHT, order_warnings


class TestOrderWarnings:
    def test_small_buy_no_warning(self):
        _, _, warnings = order_warnings(
            True, Decimal("3000"), Decimal("85512.63"), Decimal("100139.78"), Decimal("6500")
        )
        assert warnings == []

    def test_concentration_warning(self):
        """6 500 + 40 000 = 46 500 sur 100 139,78 -> 46,4 % : au-dessus de 30 %."""
        asset_weight, cash_weight, warnings = order_warnings(
            True, Decimal("40000"), Decimal("85512.63"), Decimal("100139.78"), Decimal("6500")
        )
        assert asset_weight == pytest.approx(Decimal("0.4644"), abs=Decimal("0.0001"))
        assert asset_weight > MAX_SINGLE_ASSET_WEIGHT
        assert len(warnings) == 1 and "46,4 %" in warnings[0]

    def test_low_cash_warning(self):
        """Il resterait 4 000 sur 100 000 : 4 % de cash, sous le minimum de 5 %."""
        _, cash_weight, warnings = order_warnings(
            True, Decimal("6000"), Decimal("10000"), Decimal("100000"), Decimal("80000")
        )
        assert cash_weight < MIN_CASH_WEIGHT
        assert any("liquidités" in text for text in warnings)

    def test_insufficient_cash(self):
        _, _, warnings = order_warnings(
            True, Decimal("20000"), Decimal("10000"), Decimal("100000"), Decimal("0")
        )
        assert any("insuffisant" in text for text in warnings)

    def test_sell_never_warns(self):
        _, cash_weight, warnings = order_warnings(
            False, Decimal("5000"), Decimal("1000"), Decimal("100000"), Decimal("50000")
        )
        assert warnings == []
        assert cash_weight == pytest.approx(Decimal("0.06"))
