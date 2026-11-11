"""Tests unitaires du modèle fréquence-sévérité et du capital économique (valeurs analytiques)."""
import math

import numpy as np
import pytest

from app.actuarial.loss_models import frequency, severity
from app.actuarial.loss_models.aggregate_losses import compound_moments, simulate
from app.actuarial.loss_models.capital import risk_measures


class TestFrequency:
    def test_poisson_mle_is_mean(self):
        fit = frequency.fit_poisson([2, 4, 3, 5, 1])
        assert fit["params"]["lam"] == pytest.approx(3.0)
        assert fit["standard_errors"]["lam"] == pytest.approx(math.sqrt(3 / 5))

    def test_negative_binomial_recovers_parameters(self):
        counts = np.random.default_rng(0).negative_binomial(3.0, 0.3, 5_000)
        fit = frequency.fit_negative_binomial(counts)
        assert fit["params"]["r"] == pytest.approx(3.0, rel=0.1)
        assert fit["params"]["p"] == pytest.approx(0.3, rel=0.1)
        assert fit["aic"] < frequency.fit_poisson(counts)["aic"]

    def test_negative_binomial_needs_overdispersion(self):
        with pytest.raises(ValueError, match="surdispersion"):
            frequency.fit_negative_binomial([3, 3, 3, 4, 3])

    def test_moments_annualize_and_stress(self):
        nb = {"r": 2.0, "p": 0.4}
        mean, variance = frequency.moments("negative_binomial", nb)
        assert mean == pytest.approx(3.0)
        assert variance == pytest.approx(3.0 + 9 / 2)
        assert frequency.moments("negative_binomial", frequency.annualize("negative_binomial", nb, 12))[0] == pytest.approx(36)
        assert frequency.moments("negative_binomial", frequency.stress("negative_binomial", nb, 1.5))[0] == pytest.approx(4.5)
        assert frequency.stress("poisson", {"lam": 2.0}, 2.0) == {"lam": 4.0}

    def test_invalid(self):
        with pytest.raises(ValueError):
            frequency.fit_poisson([1, -1, 2])
        with pytest.raises(ValueError):
            frequency.validate("negative_binomial", {"r": 1, "p": 1.5})


class TestSeverity:
    rng = np.random.default_rng(1)

    def test_lognormal_closed_form(self):
        data = self.rng.lognormal(8.0, 1.2, 20_000)
        fit = severity.fit("lognormal", data)
        assert fit["params"]["mu"] == pytest.approx(8.0, abs=0.03)
        assert fit["params"]["sigma"] == pytest.approx(1.2, abs=0.03)
        mu, sigma = fit["params"]["mu"], fit["params"]["sigma"]
        assert fit["mean"] == pytest.approx(math.exp(mu + sigma**2 / 2))

    def test_gamma_fit(self):
        data = self.rng.gamma(2.5, 1_000, 20_000)
        fit = severity.fit("gamma", data)
        assert fit["params"]["shape"] == pytest.approx(2.5, rel=0.05)
        assert fit["params"]["scale"] == pytest.approx(1_000, rel=0.05)

    def test_pareto_with_known_threshold(self):
        data = (self.rng.pareto(2.5, 20_000) + 1) * 500
        fit = severity.fit("pareto", data, threshold=500)
        assert fit["params"]["alpha"] == pytest.approx(2.5, rel=0.05)
        assert fit["params"]["xm"] == 500
        with pytest.raises(ValueError):
            severity.fit("pareto", data, threshold=10_000)

    def test_aic_prefers_true_model(self):
        data = self.rng.lognormal(5, 1.5, 3_000)
        fits = {m: severity.fit(m, data) for m in ("gamma", "lognormal")}
        assert fits["lognormal"]["aic"] < fits["gamma"]["aic"]

    def test_pareto_infinite_moments(self):
        assert severity.moments("pareto", {"alpha": 0.9, "xm": 1}) == (None, None)
        mean, variance = severity.moments("pareto", {"alpha": 1.5, "xm": 1})
        assert mean == pytest.approx(3.0)
        assert variance is None

    def test_stress_scales_mean_and_widens_tail(self):
        base = {"shape": 4.0, "scale": 100.0}
        shocked = severity.stress("gamma", base, severity_multiplier=1.2, tail_multiplier=1.5)
        assert severity.moments("gamma", shocked)[0] == pytest.approx(1.2 * 400)
        cv = lambda p: math.sqrt(severity.moments("gamma", p)[1]) / severity.moments("gamma", p)[0]  # noqa: E731
        assert cv(shocked) == pytest.approx(1.5 * cv(base))
        assert severity.stress("lognormal", {"mu": 1, "sigma": 1}, 2, 1)["mu"] == pytest.approx(1 + math.log(2))


class TestAggregate:
    freq = ("poisson", {"lam": 12.0})
    sev = ("lognormal", {"mu": 7.0, "sigma": 0.8})

    def test_mean_and_variance_match_collective_model(self):
        totals, counts = simulate(*self.freq, *self.sev, n_years=100_000, seed=2)
        expected = compound_moments(*self.freq, *self.sev)
        assert totals.mean() == pytest.approx(expected["mean"], rel=0.01)
        assert totals.var(ddof=1) == pytest.approx(expected["variance"], rel=0.03)
        assert counts.mean() == pytest.approx(12.0, rel=0.01)

    def test_negative_binomial_compound_variance(self):
        freq = ("negative_binomial", {"r": 4.0, "p": 0.25})
        totals, _ = simulate(*freq, "gamma", {"shape": 2.0, "scale": 50.0}, n_years=100_000, seed=3)
        expected = compound_moments(*freq, "gamma", {"shape": 2.0, "scale": 50.0})
        assert totals.var(ddof=1) == pytest.approx(expected["variance"], rel=0.03)

    def test_deductible_and_limit(self):
        totals, counts = simulate("poisson", {"lam": 5.0}, "gamma", {"shape": 2.0, "scale": 100.0},
                                  n_years=2_000, seed=4, deductible=50, limit=100)
        assert np.all(totals <= counts * 100 + 1e-9)
        gross, _ = simulate("poisson", {"lam": 5.0}, "gamma", {"shape": 2.0, "scale": 100.0}, n_years=2_000, seed=4)
        assert totals.mean() < gross.mean()

    def test_reproducible_and_bounded(self):
        a, _ = simulate(*self.freq, *self.sev, n_years=500, seed=9)
        b, _ = simulate(*self.freq, *self.sev, n_years=500, seed=9)
        np.testing.assert_array_equal(a, b)
        with pytest.raises(ValueError):
            simulate("poisson", {"lam": 1_000.0}, *self.sev, n_years=200_000)


class TestCapital:
    def test_capital_is_var_minus_mean(self):
        totals = np.arange(1, 1001, dtype=float)
        rows = {r["confidence"]: r for r in risk_measures(totals)}
        assert rows[0.995]["var"] == 995
        assert rows[0.995]["capital_var"] == pytest.approx(995 - 500.5)
        assert rows[0.99]["tvar"] == pytest.approx(np.arange(990, 1001).mean())
        assert all(r["tvar"] >= r["var"] for r in rows.values())
