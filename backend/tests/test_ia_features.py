"""Tests unitaires du feature engineering (module IA).

Ces tests ne nécessitent ni base de données ni scikit-learn : ils valident
les fonctions pures de app.ia.features sur des séries synthétiques.
"""

import numpy as np

from app.ia import features as F


# --- Séries synthétiques reproductibles ---
def _trending_prices(n: int = 120, start: float = 100.0, drift: float = 0.001) -> list[float]:
    """Série de prix en légère hausse + bruit déterministe."""
    rng = np.random.default_rng(42)
    prices = [start]
    for _ in range(n - 1):
        prices.append(prices[-1] * (1.0 + drift + rng.normal(0, 0.01)))
    return prices


class TestSimpleReturns:
    def test_first_element_is_nan(self):
        r = F.simple_returns([100.0, 110.0, 105.0])
        assert np.isnan(r[0])

    def test_basic_returns(self):
        r = F.simple_returns([100.0, 110.0, 105.0])
        assert np.isclose(r[1], 0.10)    # +10%
        assert np.isclose(r[2], -5.0 / 110.0)  # -4.545%

    def test_single_price(self):
        r = F.simple_returns([100.0])
        assert len(r) == 1
        assert np.isnan(r[0])


class TestSMA:
    def test_nan_before_window(self):
        s = F.sma([1, 2, 3, 4, 5], window=3)
        assert np.isnan(s[0])
        assert np.isnan(s[1])
        assert np.isclose(s[2], 2.0)  # (1+2+3)/3
        assert np.isclose(s[3], 3.0)  # (2+3+4)/3
        assert np.isclose(s[4], 4.0)  # (3+4+5)/3

    def test_too_short(self):
        s = F.sma([1, 2], window=5)
        assert np.all(np.isnan(s))


class TestRSI:
    def test_nan_before_period(self):
        prices = [100 + i for i in range(20)]  # hausse régulière
        r = F.rsi(prices, period=14)
        # Les 14 premiers sont NaN.
        assert np.all(np.isnan(r[:14]))
        # En hausse pure, RSI devrait être élevé (proche de 100).
        assert r[14] > 90

    def test_bounded_0_100(self):
        prices = _trending_prices(60)
        r = F.rsi(prices, period=14)
        valid = r[~np.isnan(r)]
        assert np.all(valid >= 0)
        assert np.all(valid <= 100)


class TestRollingVolatility:
    def test_nan_before_window(self):
        prices = _trending_prices(30)
        v = F.rolling_volatility(prices, window=20)
        assert np.all(np.isnan(v[:19]))
        assert np.isfinite(v[19])

    def test_positive(self):
        prices = _trending_prices(30)
        v = F.rolling_volatility(prices, window=20)
        assert np.all(v[19:] > 0)


class TestMomentum:
    def test_basic(self):
        prices = [100.0, 110.0, 105.0, 120.0]
        m = F.momentum(prices, window=2)
        # m[2] = 105/100 - 1 = 0.05
        assert np.isclose(m[2], 0.05)
        # m[3] = 120/110 - 1
        assert np.isclose(m[3], 120.0 / 110.0 - 1.0)


class TestVolumeRatio:
    def test_with_volumes(self):
        vols = [1000] * 20 + [2000]  # jour 20 : volume double de la moyenne
        vr = F.volume_ratio(vols, window=20)
        assert np.isclose(vr[20], 2.0)

    def test_none_volumes(self):
        vr = F.volume_ratio([None, None, None], window=2)
        assert np.all(np.isnan(vr))


class TestBuildFeatureMatrix:
    def test_shapes(self):
        prices = _trending_prices(120)
        volumes = [10000 + i * 10 for i in range(120)]
        X, y, valid = F.build_feature_matrix(prices, volumes, horizon=5)
        assert X.shape == (120, len(F.FEATURE_COLUMNS))
        assert y.shape == (120,)
        # Les lignes valides excluent le début (features NaN) et la fin (cible NaN).
        assert len(valid) > 0
        assert max(valid) < 115  # pas de cible dans les 5 derniers jours

    def test_no_volumes(self):
        prices = _trending_prices(120)
        X, y, valid = F.build_feature_matrix(prices, None, horizon=5)
        # Doit quand même produire des features valides (volume_ratio imputé plus tard).
        assert X.shape == (120, len(F.FEATURE_COLUMNS))

    def test_short_history(self):
        prices = _trending_prices(10)
        X, y, valid = F.build_feature_matrix(prices, None, horizon=5)
        # Pas assez de données pour avoir des lignes valides (besoin de SMA50).
        assert len(valid) == 0
