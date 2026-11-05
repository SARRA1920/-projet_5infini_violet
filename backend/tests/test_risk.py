"""Tests des indicateurs de risque : volatilité, VaR et drawdown."""
import pytest

from app.services.risk import annualized_volatility, historical_var, max_drawdown


class TestVolatility:
    def test_not_enough_data(self):
        assert annualized_volatility([]) is None
        assert annualized_volatility([0.01]) is None

    def test_known_value(self):
        """Écart-type de [+1 %, -1 %, +1 %, -1 %] = 1,1547 % ; x racine(252) = 18,33 %."""
        assert annualized_volatility([0.01, -0.01, 0.01, -0.01]) == pytest.approx(0.1833, abs=1e-4)

    def test_constant_returns_have_no_volatility(self):
        assert annualized_volatility([0.01, 0.01, 0.01]) == 0


class TestVar:
    def test_no_data(self):
        assert historical_var([]) is None

    def test_reads_the_five_percent_worst_day(self):
        """20 jours : on lit le 2e pire jour (indice int(0,05 x 20) = 1) -> perte de 3 %."""
        returns = [-0.05, -0.03] + [0.0] * 18
        assert historical_var(returns, 0.95) == pytest.approx(0.03)

    def test_gains_only_gives_zero_loss(self):
        assert historical_var([0.01] * 20, 0.95) == 0.0


class TestDrawdown:
    def test_no_data(self):
        assert max_drawdown([]) is None

    def test_known_value(self):
        """Valeur : 1,10 puis 0,88 (-20 % depuis le sommet) puis 0,924 -> drawdown 20 %."""
        assert max_drawdown([0.10, -0.20, 0.05]) == pytest.approx(0.20)

    def test_always_rising(self):
        assert max_drawdown([0.01, 0.02]) == 0.0
