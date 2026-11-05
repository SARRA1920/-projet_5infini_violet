"""Tests de l'analyse technique : moyenne mobile, RSI, signaux et rejeu de stratégie."""
import pytest

from app.services.analysis import (
    crossover_signal,
    rsi,
    rsi_signal,
    simulate,
    sma,
    trend_signal,
)


class TestSma:
    def test_window_five(self):
        """(100 + 102 + 101 + 103 + 104) / 5 = 102 ; avant, pas assez de jours."""
        assert sma([100, 102, 101, 103, 104], 5) == [None, None, None, None, 102.0]

    def test_window_two_slides(self):
        assert sma([100, 102, 101, 103], 2) == [None, 101.0, 101.5, 102.0]


class TestRsi:
    def test_not_enough_data(self):
        assert rsi([1, 2, 3], 14) == [None, None, None]

    def test_only_gains_is_100(self):
        values = rsi([float(i) for i in range(1, 30)], 14)
        assert values[:14] == [None] * 14
        assert values[-1] == 100.0

    def test_only_losses_is_0(self):
        values = rsi([float(i) for i in range(30, 1, -1)], 14)
        assert values[-1] == pytest.approx(0.0)

    def test_equal_gains_and_losses_is_50(self):
        """100, 101, 100, 101... : autant de hausses que de baisses de 1."""
        closes = [100.0 + (i % 2) for i in range(15)]
        assert rsi(closes, 14)[14] == pytest.approx(50.0)


class TestSignals:
    def test_crossover_on_rising_prices(self):
        """MM2 passe au-dessus de MM3 dès que les deux existent : investi."""
        assert crossover_signal([1, 2, 3, 4, 5], 2, 3) == [None, None, True, True, True]

    def test_trend_below_average_is_out(self):
        """Cours 9 sous sa moyenne 9,5, puis 8 sous 8,5 : en liquidités."""
        assert trend_signal([10, 9, 8], 2) == [None, False, False]

    def test_rsi_signal_buys_oversold_and_sells_overbought(self):
        """Longue baisse (RSI proche de 0 : achat), puis forte hausse (RSI > 70 : vente)."""
        closes = [float(100 - i) for i in range(30)] + [70.0 + 3 * i for i in range(1, 30)]
        signal = rsi_signal(closes, 14)
        assert signal[:14] == [None] * 14
        assert signal[14] is True
        assert signal[-1] is False


class TestSimulate:
    def test_always_invested_follows_the_price(self):
        """100 -> 110 -> 121 avec 10 000 de départ : 11 000 puis 12 100, sans baisse."""
        out = simulate([100, 110, 121], [True, True, True], start=0)
        assert out["curve"] == pytest.approx([10000, 11000, 12100])
        assert out["return_pct"] == pytest.approx(21.0)
        assert out["max_drawdown_pct"] == 0
        assert out["entries"] == 1
        assert out["time_in_market_pct"] == 100
        assert out["return_to_risk"] is None

    def test_cash_day_keeps_capital_flat(self):
        """Investi le 1er jour (+10 %), puis en liquidités : le -10 % suivant est évité."""
        out = simulate([100, 110, 99], [True, False, False], start=0)
        assert out["curve"] == pytest.approx([10000, 11000, 11000])
        assert out["time_in_market_pct"] == pytest.approx(50.0)

    def test_drawdown(self):
        """10 000 -> 12 000 -> 9 000 : chute de 25 % depuis le sommet."""
        out = simulate([100, 120, 90], [True, True, True], start=0)
        assert out["max_drawdown_pct"] == pytest.approx(25.0)
        assert out["return_to_risk"] == pytest.approx(-10.0 / 25.0)

    def test_counts_each_new_entry(self):
        out = simulate([100, 101, 102, 103, 104], [True, False, True, False, True], start=0)
        assert out["entries"] == 2
