"""Tests unitaires des mesures de risque du module Actuariat (valeurs connues)."""
import math

import numpy as np
import pytest
from scipy.stats import norm

from app.actuarial.risk.expected_shortfall import (
    historical_es,
    monte_carlo_es,
    parametric_es,
)
from app.actuarial.risk.risk_metrics import (
    annualized_return,
    cumulative_return,
    herfindahl_index,
    risk_contributions,
    sharpe_ratio,
    sortino_ratio,
)
from app.actuarial.risk.var import (
    historical_var,
    loss_quantile,
    monte_carlo_var,
    parametric_var,
    simulate_portfolio_returns,
)


class TestHistoricalVar:
    def test_reads_quantile_without_interpolation(self):
        """Pertes 1..100 : le quantile 95 % (inverted_cdf) est la 95e perte."""
        returns = -np.arange(1, 101) / 1000
        assert historical_var(returns, 0.95) == pytest.approx(0.095)
        assert historical_var(returns, 0.99) == pytest.approx(0.099)

    def test_square_root_of_time(self):
        returns = -np.arange(1, 101) / 1000
        assert historical_var(returns, 0.95, 10) == pytest.approx(0.095 * math.sqrt(10))

    def test_gains_only_gives_negative_var(self):
        """Pas de bornage à 0 : le pire quantile est encore un gain."""
        assert historical_var(np.full(50, 0.01), 0.95) == pytest.approx(-0.01)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            historical_var(np.array([0.01]), 1.0)
        with pytest.raises(ValueError):
            historical_var(np.array([0.01]), 0.95, 0)
        with pytest.raises(ValueError):
            loss_quantile(np.array([]), 0.95)


class TestParametric:
    def test_var_matches_normal_formula(self):
        returns = np.array([0.01, -0.01, 0.02, -0.02, 0.0])
        mu, sigma = returns.mean(), returns.std(ddof=1)
        expected = -mu * 10 + norm.ppf(0.99) * sigma * math.sqrt(10)
        assert parametric_var(returns, 0.99, 10) == pytest.approx(expected)

    def test_es_of_standard_normal(self):
        """Pour N(0, 1) à 95 % : ES = φ(1,645) / 0,05 ≈ 2,0627."""
        rng = np.random.default_rng(0)
        returns = rng.standard_normal(200_000)
        returns = (returns - returns.mean()) / returns.std(ddof=1)
        assert parametric_es(returns, 0.95) == pytest.approx(2.0627, abs=1e-3)

    def test_es_is_at_least_var(self):
        rng = np.random.default_rng(1)
        returns = rng.normal(0.0005, 0.01, 500)
        for confidence in (0.95, 0.99):
            assert parametric_es(returns, confidence) >= parametric_var(returns, confidence)
            assert historical_es(returns, confidence) >= historical_var(returns, confidence)


class TestMonteCarlo:
    def test_reproducible_with_seed(self):
        rng = np.random.default_rng(2)
        assets = rng.normal(0, 0.01, (250, 3))
        weights = np.array([0.3, 0.3, 0.2])
        first = simulate_portfolio_returns(assets, weights, 10, 2_000, seed=42)
        second = simulate_portfolio_returns(assets, weights, 10, 2_000, seed=42)
        np.testing.assert_array_equal(first, second)

    def test_converges_to_parametric_for_normal_data(self):
        """Petits rendements normaux : VaR MC ≈ VaR paramétrique (à 5 % près)."""
        rng = np.random.default_rng(3)
        assets = rng.normal(0, 0.01, (2_000, 1))
        simulated = simulate_portfolio_returns(assets, np.array([1.0]), 1, 100_000, seed=7)
        assert monte_carlo_var(simulated, 0.99) == pytest.approx(parametric_var(assets[:, 0], 0.99), rel=0.05)
        assert monte_carlo_es(simulated, 0.99) >= monte_carlo_var(simulated, 0.99)

    def test_rejects_mismatched_weights(self):
        with pytest.raises(ValueError):
            simulate_portfolio_returns(np.zeros((10, 2)), np.array([1.0]))


class TestPerformance:
    def test_cumulative_and_annualized_return(self):
        returns = np.full(252, 0.001)
        assert cumulative_return(returns) == pytest.approx(1.001**252 - 1)
        assert annualized_return(returns) == pytest.approx(1.001**252 - 1)

    def test_sharpe_known_value(self):
        """Moyenne 0, écart-type 1,1547 % : Sharpe nul ; avec rf, négatif."""
        returns = np.array([0.01, -0.01, 0.01, -0.01])
        assert sharpe_ratio(returns) == pytest.approx(0.0)
        assert sharpe_ratio(returns, 0.0252) < 0

    def test_sortino_uses_downside_only(self):
        returns = np.array([0.02, -0.01, 0.02, -0.01])
        downside = math.sqrt((0.01**2 + 0.01**2) / 4)
        assert sortino_ratio(returns) == pytest.approx(0.005 / downside * math.sqrt(252))

    def test_ratios_undefined_without_dispersion(self):
        assert sharpe_ratio(np.full(10, 0.01)) is None
        assert sortino_ratio(np.full(10, 0.01)) is None


class TestRiskDecomposition:
    def test_contributions_sum_to_volatility(self):
        cov = np.array([[0.04, 0.006], [0.006, 0.01]])
        weights = np.array([0.6, 0.4])
        result = risk_contributions(weights, cov)
        assert result["volatility"] == pytest.approx(math.sqrt(weights @ cov @ weights))
        assert result["component"].sum() == pytest.approx(result["volatility"])
        assert result["share"].sum() == pytest.approx(1.0)

    def test_uncorrelated_equal_assets_share_risk_equally(self):
        result = risk_contributions(np.array([0.5, 0.5]), np.eye(2) * 0.01)
        np.testing.assert_allclose(result["share"], [0.5, 0.5])

    def test_herfindahl(self):
        assert herfindahl_index([1, 1, 1, 1]) == pytest.approx(0.25)
        assert herfindahl_index([5]) == pytest.approx(1.0)
        assert herfindahl_index([0, 0]) is None
