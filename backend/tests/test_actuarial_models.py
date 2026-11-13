"""Tests unitaires des modèles stochastiques, obligataires, de Markowitz et du backtesting.

Chaque modèle est confronté à une valeur analytique connue (moments, prix zéro-coupon,
formules fermées) plutôt qu'à des valeurs recopiées de sa propre sortie.
"""
import math
from datetime import date

import numpy as np
import pytest

from app.actuarial.fixed_income.bond_pricing import dirty_price_from_flows, price
from app.actuarial.fixed_income.cashflows import Bond, accrued_interest, add_months, cash_flows
from app.actuarial.fixed_income.convexity import convexity
from app.actuarial.fixed_income.curve_shocks import curve_scenarios, parallel_sensitivity, shock_profile
from app.actuarial.fixed_income.duration import macaulay_duration, modified_duration
from app.actuarial.fixed_income.yield_to_maturity import yield_to_maturity
from app.actuarial.optimization.efficient_frontier import efficient_frontier
from app.actuarial.optimization.markowitz import OptimizationError, max_sharpe, min_variance, stats
from app.actuarial.risk.backtesting import kupiec_test, rolling_var_backtest
from app.actuarial.stochastic import cir, gbm, hull_white, vasicek


def within_mc_error(simulated: np.ndarray, expected: float, sigmas: float = 4.0) -> bool:
    return abs(simulated.mean() - expected) < sigmas * simulated.std(ddof=1) / math.sqrt(simulated.size)


class TestGBM:
    def test_terminal_mean_matches_closed_form(self):
        paths, _ = gbm.simulate(100, 0.08, 0.25, 1.0, 50, 20_000, seed=1)
        assert within_mc_error(paths[:, -1], gbm.expected_value(100, 0.08, 1.0))

    def test_probability_of_loss_matches_lognormal(self):
        paths, _ = gbm.simulate(100, 0.05, 0.3, 0.5, 10, 20_000, seed=2)
        assert (paths[:, -1] < 100).mean() == pytest.approx(gbm.probability_below(100, 0.05, 0.3, 0.5, 100), abs=0.015)

    def test_calibration_recovers_volatility(self):
        paths, _ = gbm.simulate(50, 0.1, 0.2, 10.0, 2_520, 1, seed=3)
        fitted = gbm.calibrate(paths[0])
        assert fitted["sigma"] == pytest.approx(0.2, rel=0.05)
        assert fitted["s0"] == pytest.approx(paths[0, -1])

    def test_reproducible_and_bounded(self):
        a, _ = gbm.simulate(100, 0.0, 0.2, 1.0, 12, 100, seed=9)
        b, _ = gbm.simulate(100, 0.0, 0.2, 1.0, 12, 100, seed=9)
        np.testing.assert_array_equal(a, b)
        with pytest.raises(ValueError):
            gbm.simulate(100, 0.0, 0.2, 1.0, 2_520, 20_000)


class TestVasicek:
    params = dict(r0=0.03, a=0.8, b=0.04, sigma=0.01)

    def test_moments(self):
        paths, _ = vasicek.simulate(**self.params, horizon=2.0, steps=24, n_simulations=20_000, seed=4)
        terminal = paths[:, -1]
        assert within_mc_error(terminal, vasicek.mean(0.03, 0.8, 0.04, 2.0))
        assert terminal.var(ddof=1) == pytest.approx(vasicek.variance(0.8, 0.01, 2.0), rel=0.05)

    def test_zero_coupon_price(self):
        paths, times = vasicek.simulate(**self.params, horizon=5.0, steps=250, n_simulations=10_000, seed=5)
        discount = np.exp(-np.trapezoid(paths, times, axis=1)).mean()
        assert discount == pytest.approx(vasicek.zero_coupon_price(0.03, 0.8, 0.04, 0.01, 5.0), rel=2e-3)

    def test_calibration(self):
        paths, _ = vasicek.simulate(0.02, 0.5, 0.04, 0.01, horizon=200.0, steps=2_400, n_simulations=1, seed=6)
        fitted = vasicek.calibrate(paths[0], dt=200.0 / 2_400)
        assert fitted["b"] == pytest.approx(0.04, abs=0.005)
        assert fitted["sigma"] == pytest.approx(0.01, rel=0.1)
        assert fitted["a"] == pytest.approx(0.5, rel=0.3)

    def test_rejects_series_without_mean_reversion(self):
        with pytest.raises(ValueError):
            vasicek.calibrate(np.linspace(0.01, 0.05, 50), dt=1 / 12)


class TestCIR:
    params = dict(r0=0.03, a=0.6, b=0.04, sigma=0.05)

    def test_moments_and_positivity(self):
        paths, _ = cir.simulate(**self.params, horizon=2.0, steps=24, n_simulations=20_000, seed=7)
        terminal = paths[:, -1]
        assert np.all(paths >= 0)
        assert within_mc_error(terminal, cir.mean(0.03, 0.6, 0.04, 2.0))
        assert terminal.var(ddof=1) == pytest.approx(cir.variance(0.03, 0.6, 0.04, 0.05, 2.0), rel=0.05)

    def test_zero_coupon_price(self):
        paths, times = cir.simulate(**self.params, horizon=5.0, steps=250, n_simulations=10_000, seed=8)
        discount = np.exp(-np.trapezoid(paths, times, axis=1)).mean()
        assert discount == pytest.approx(cir.zero_coupon_price(0.03, 0.6, 0.04, 0.05, 5.0), rel=2e-3)

    def test_feller(self):
        assert cir.feller(0.6, 0.04, 0.05)
        assert not cir.feller(0.1, 0.01, 0.2)

    def test_calibration(self):
        paths, _ = cir.simulate(0.04, 0.5, 0.04, 0.05, horizon=200.0, steps=2_400, n_simulations=1, seed=10)
        fitted = cir.calibrate(paths[0], dt=200.0 / 2_400)
        assert fitted["b"] == pytest.approx(0.04, abs=0.006)
        assert fitted["sigma"] == pytest.approx(0.05, rel=0.15)


class TestHullWhite:
    curve = hull_white.ZeroCurve([0.5, 2, 5, 10], [0.03, 0.035, 0.04, 0.042])

    def test_reprices_initial_curve(self):
        paths, times = hull_white.simulate(self.curve, 0.3, 0.01, horizon=5.0, steps=250, n_simulations=10_000, seed=11)
        discount = np.exp(-np.trapezoid(paths, times, axis=1)).mean()
        assert discount == pytest.approx(self.curve.discount(5.0), rel=2e-3)

    def test_mean_follows_alpha(self):
        paths, _ = hull_white.simulate(self.curve, 0.3, 0.01, horizon=3.0, steps=36, n_simulations=20_000, seed=12)
        assert within_mc_error(paths[:, -1], hull_white.mean(self.curve, 0.3, 0.01, 3.0))

    def test_flat_curve_forward_equals_rate(self):
        flat = hull_white.ZeroCurve([1.0], [0.05])
        assert float(flat.forward(3.0)) == pytest.approx(0.05)

    def test_invalid_curve(self):
        with pytest.raises(ValueError):
            hull_white.ZeroCurve([2, 1], [0.03, 0.04])


SETTLE = date(2026, 1, 15)


class TestBonds:
    def test_zero_coupon(self):
        bond = Bond(100, 0.0, 1, date(2031, 1, 15), day_count="30/360")
        flows = cash_flows(bond, SETTLE)
        assert dirty_price_from_flows(flows, 0.05, 1) == pytest.approx(100 / 1.05**5)
        assert macaulay_duration(flows, 0.05, 1) == pytest.approx(5.0)
        assert modified_duration(flows, 0.05, 1) == pytest.approx(5 / 1.05)

    def test_par_bond_and_known_duration(self):
        bond = Bond(100, 0.05, 1, date(2029, 1, 15), day_count="30/360")
        flows = cash_flows(bond, SETTLE)
        assert price(bond, SETTLE, 0.05)["clean"] == pytest.approx(100.0)
        expected = (5 / 1.05 + 2 * 5 / 1.05**2 + 3 * 105 / 1.05**3) / 100
        assert macaulay_duration(flows, 0.05, 1) == pytest.approx(expected)

    def test_ytm_round_trip(self):
        bond = Bond(1000, 0.0375, 2, date(2034, 6, 30))
        clean = price(bond, SETTLE, 0.0461)["clean"]
        assert yield_to_maturity(bond, SETTLE, clean) == pytest.approx(0.0461, abs=1e-9)

    def test_duration_and_convexity_match_finite_differences(self):
        bond = Bond(100, 0.04, 2, date(2036, 3, 1))
        flows = cash_flows(bond, SETTLE)
        y, h = 0.045, 1e-5
        p0, up, down = (dirty_price_from_flows(flows, y + d, 2) for d in (0, h, -h))
        assert modified_duration(flows, y, 2) == pytest.approx((down - up) / (2 * h * p0), rel=1e-5)
        assert convexity(flows, y, 2) == pytest.approx((up + down - 2 * p0) / (p0 * h**2), rel=1e-3)

    def test_accrued_interest_half_period(self):
        bond = Bond(100, 0.06, 2, date(2030, 7, 15))
        accrued = accrued_interest(bond, date(2026, 4, 15))
        assert accrued == pytest.approx(3.0 * 90 / 181)

    def test_end_of_month_and_validation(self):
        assert add_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
        with pytest.raises(ValueError):
            Bond(100, 0.05, 3, date(2030, 1, 1))
        with pytest.raises(ValueError):
            cash_flows(Bond(100, 0.05, 1, date(2025, 1, 1)), SETTLE)

    def test_parallel_shocks(self):
        bond = Bond(100, 0.04, 2, date(2036, 3, 1))
        flows = cash_flows(bond, SETTLE)
        rows = parallel_sensitivity(flows, 0.045, 2, modified_duration(flows, 0.045, 2), convexity(flows, 0.045, 2))
        up_100 = next(r for r in rows if r["shift_bp"] == 100)
        assert up_100["price"] == pytest.approx(dirty_price_from_flows(flows, 0.055, 2))
        assert abs(up_100["approx_error"]) < abs(up_100["duration_approx"] - up_100["price"])

    def test_curve_scenarios_on_flat_curve(self):
        bond = Bond(100, 0.04, 2, date(2036, 3, 1))
        flows = cash_flows(bond, SETTLE)
        rows = {r["scenario"]: r for r in curve_scenarios(flows, 2, lambda t: np.full_like(np.asarray(t, float), 0.045), 50)}
        assert rows["parallel+"]["price"] == pytest.approx(dirty_price_from_flows(flows, 0.05, 2))
        assert float(shock_profile("steepening", 0.01, 0.0)) == pytest.approx(-0.01)
        assert float(shock_profile("butterfly", 0.01, 5.0)) == pytest.approx(-0.01)


class TestMarkowitz:
    mu = np.array([0.08, 0.12])
    cov = np.diag([0.04, 0.09])

    def test_min_variance_is_inverse_variance(self):
        weights = min_variance(self.cov)
        np.testing.assert_allclose(weights, [0.09 / 0.13, 0.04 / 0.13], atol=1e-5)

    def test_max_sharpe_is_tangency(self):
        raw = np.linalg.solve(self.cov, self.mu - 0.02)
        np.testing.assert_allclose(max_sharpe(self.mu, self.cov, 0.02), raw / raw.sum(), atol=1e-4)

    def test_weight_cap_and_infeasibility(self):
        mu = np.array([0.05, 0.10, 0.20])
        weights = max_sharpe(mu, np.diag([0.04, 0.04, 0.04]), max_weight=0.4)
        assert weights.max() <= 0.4 + 1e-6
        assert weights.sum() == pytest.approx(1.0)
        with pytest.raises(OptimizationError):
            min_variance(np.eye(2), max_weight=0.4)

    def test_short_selling_only_when_allowed(self):
        mu = np.array([0.02, 0.15])
        cov = np.array([[0.04, 0.035], [0.035, 0.04]])
        assert max_sharpe(mu, cov).min() >= -1e-9
        assert max_sharpe(mu, cov, allow_short=True, max_weight=1.0).sum() == pytest.approx(1.0)

    def test_frontier_is_monotonic(self):
        frontier = efficient_frontier(self.mu, self.cov, points=10)
        returns = [p["expected_return"] for p in frontier]
        vols = [p["volatility"] for p in frontier]
        assert returns == sorted(returns)
        assert vols == sorted(vols)
        assert vols[0] == pytest.approx(stats(min_variance(self.cov), self.mu, self.cov)["volatility"], rel=1e-4)


class TestBacktesting:
    def test_kupiec_known_values(self):
        """250 jours, VaR 99 %, aucune exception : LR = -2 x 250 x ln(0,99) ≈ 5,025."""
        result = kupiec_test(250, 0, 0.99)
        assert result["lr_statistic"] == pytest.approx(-500 * math.log(0.99))
        assert result["rejected"]
        assert kupiec_test(200, 10, 0.95)["p_value"] == pytest.approx(1.0)

    def test_rolling_backtest_on_normal_returns(self):
        returns = np.random.default_rng(13).normal(0, 0.01, 1_000)
        result = rolling_var_backtest(returns, 0.95, window=250)
        assert result["observations"] == 750
        assert 0.03 < result["exception_rate"] < 0.07
