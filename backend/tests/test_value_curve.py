"""Tests de la courbe de performance simulée (composition actuelle sur l'historique)."""
from datetime import date
from decimal import Decimal

import pytest

from app.services.risk import value_curve


class TestValueCurve:
    def test_last_point_is_today_and_goes_back(self):
        """Le 2 janvier (aujourd'hui) vaut 99. Ce jour-là le rendement est -10 %,
        donc le 1er janvier valait 99 / 0,90 = 110."""
        returns = [(date(2026, 1, 1), 0.10), (date(2026, 1, 2), -0.10)]
        points = value_curve(returns, Decimal("99"))
        assert points[-1] == (date(2026, 1, 2), pytest.approx(99.0))
        assert points[0] == (date(2026, 1, 1), pytest.approx(110.0))

    def test_empty(self):
        assert value_curve([], Decimal("100")) == []
