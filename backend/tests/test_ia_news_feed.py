"""Tests du fil d'actualités en direct (news_feed + route /api/ia/news/live).

Les fetchers RSS sont remplacés par des fixtures locales (aucun réseau) :
on vérifie l'association titre → tickers, le scoring de sentiment, la
déduplication, la limite, le cache d'agrégation (politesse réseau) et le
contrat HTTP de l'endpoint. Même pattern que test_ia_api.py.
"""
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.database import get_db
from app.main import app
from app.models.models import User, UserRole
from app.ia import news_feed


@pytest.fixture(autouse=True)
def _clear_news_cache():
    news_feed.clear_feed_cache()
    yield
    news_feed.clear_feed_cache()


@pytest.fixture
def client(db):
    """Client HTTP branché sur la session de test, utilisateur authentifié."""
    user = User(email="news@example.com", username="newsuser",
                hashed_password="x", role=UserRole.USER)
    db.add(user)
    db.flush()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


def _market_fixture(*_args, **_kwargs):
    """Titres du flux « marché » : généralistes + Apple + Tesla, en doublon."""
    return [
        {"title": "Les indices américains rebondissent avant la réserve fédérale",
         "link": "https://example.com/1", "published": None},
        {"title": "Apple publie des bénéfices record portés par les ventes d'iPhone",
         "link": "https://example.com/2", "published": None},
        {"title": "Les indices américains rebondissent avant la réserve fédérale",
         "link": "https://example.com/1", "published": None},
        {"title": "Wall Street chute fortement après un avertissement sur la croissance",
         "link": "https://example.com/3", "published": None},
    ]


def _asset_fixture(symbol, company_name=None):
    """Titres du flux par actif : uniquement appelé pour AAPL dans les tests."""
    if symbol != "AAPL":
        return []
    return [
        {"title": "Apple annonce un rachat massif de ses propres actions",
         "link": "https://example.com/aapl", "published": None},
    ]


class TestMatchingAndScoring:
    def test_match_symbols_tags_tickers(self, db):
        """Un titre mentionnant « Apple » est tagué AAPL, un titre général non."""
        patterns = news_feed._build_alias_patterns([("AAPL", "Apple Inc.")])
        assert news_feed._match_symbols(
            "Apple publie des bénéfices record", patterns
        ) == ["AAPL"]
        assert news_feed._match_symbols(
            "Les indices américains rebondissent", patterns
        ) == []

    def test_item_id_stable(self):
        """Deux variantes du même titre (casse/accents) → même empreinte."""
        assert news_feed._item_id("Apple Strengthens") == \
            news_feed._item_id("apple strengthens")


class TestLiveNews:
    def test_scoring_tags_and_dedup(self, db, seed_data, monkeypatch):
        """Le fil agrège marché + actifs, score chaque titre et déduplique."""
        monkeypatch.setattr(news_feed, "_market_items", _market_fixture)
        monkeypatch.setattr(news_feed, "_asset_items", _asset_fixture)

        items = news_feed.live_news(db, limit=20)

        titles = [i.title for i in items]
        # Doublon retiré : le titre général n'apparaît qu'une fois.
        assert titles.count(
            "Les indices américains rebondissent avant la réserve fédérale"
        ) == 1
        # Le titre Apple du flux marché ET celui du flux AAPL sont présents.
        assert any("bénéfices record" in t for t in titles)
        assert any("rachat massif" in t for t in titles)

        apple_item = next(i for i in items if "bénéfices record" in i.title)
        assert apple_item.symbols == ["AAPL"]
        assert apple_item.label == "positif"
        assert 0.0 < apple_item.score <= 1.0
        assert apple_item.id  # empreinte stable présente

        market_item = next(
            i for i in items
            if "rebondissent" in i.title
        )
        assert market_item.symbols == []  # news générale du marché

        negative = next(i for i in items if "chute" in i.title)
        assert negative.label == "négatif"

        for item in items:
            assert -1.0 <= item.score <= 1.0
            assert item.label in ("positif", "neutre", "négatif")

    def test_limit_is_respected(self, db, seed_data, monkeypatch):
        """Le paramètre limit tronque le fil (tri récent d'abord)."""
        monkeypatch.setattr(news_feed, "_market_items", _market_fixture)
        monkeypatch.setattr(news_feed, "_asset_items", _asset_fixture)

        assert len(news_feed.live_news(db, limit=2)) == 2
        assert len(news_feed.live_news(db, limit=50)) <= news_feed._MAX_FEED_ITEMS

    def test_aggregation_cache_no_refetch(self, db, seed_data, monkeypatch):
        """Deux appels dans la fenêtre de cache → une seule agrégation RSS."""
        monkeypatch.setattr(news_feed, "_market_items", _market_fixture)
        monkeypatch.setattr(news_feed, "_asset_items", _asset_fixture)
        calls = {"market": 0}
        original = news_feed._market_items

        def counting(*args, **kwargs):
            calls["market"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(news_feed, "_market_items", counting)
        first = news_feed.live_news(db, limit=20)
        second = news_feed.live_news(db, limit=20)
        assert calls["market"] == 1
        assert [i.id for i in first] == [i.id for i in second]


class TestNewsEndpoint:
    def test_contract(self, client, seed_data, monkeypatch):
        """GET /api/ia/news/live : contrat HTTP complet (id, score, symbols…)."""
        monkeypatch.setattr(news_feed, "_market_items", _market_fixture)
        monkeypatch.setattr(news_feed, "_asset_items", _asset_fixture)

        resp = client.get("/api/ia/news/live", params={"limit": 10})
        assert resp.status_code == 200
        data = resp.json()
        assert data["updated_at"]
        assert 0 < len(data["items"]) <= 10
        for item in data["items"]:
            assert item["id"]
            assert item["title"]
            assert isinstance(item["symbols"], list)
            assert -1.0 <= item["score"] <= 1.0
            assert item["label"] in ("positif", "neutre", "négatif")
            assert item["source"] in ("vader", "lexicon", "lexicon-fr")

    def test_requires_authentication(self, db, monkeypatch):
        """Sans utilisateur connecté, la route est protégée (401/403)."""
        app.dependency_overrides[get_db] = lambda: db
        try:
            client = TestClient(app)
            resp = client.get("/api/ia/news/live")
            assert resp.status_code in (401, 403)
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_db, None)

    def test_empty_when_sources_down(self, client, monkeypatch):
        """Sources RSS coupées → fil vide mais réponse 200 (jamais d'erreur)."""
        monkeypatch.setattr(news_feed, "_market_items", lambda *a, **k: [])
        monkeypatch.setattr(news_feed, "_asset_items", lambda *a, **k: [])

        resp = client.get("/api/ia/news/live")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
