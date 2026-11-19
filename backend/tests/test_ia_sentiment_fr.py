"""Tests du sentiment multilingue FR/EN et du filtrage des titres.

Vérifie les trois corrections de sentiment.py :
1. les textes FRANÇAIS reçoivent un score non nul et correctement signé
   (VADER seul renvoyait 0.0 sur le français) ;
2. la négation française inverse la valence (« ne … pas bons » → négatif) ;
3. le filtrage par alias élimine les titres hors sujet (SpaceX, Walmart…).
"""

import pytest

from app.ia import sentiment as sent


class TestFrenchSentiment:
    def test_french_positive(self):
        """« bénéfices record » doit être positif — VADER renverrait 0.0."""
        r = sent.analyze_sentiment("Apple annonce des bénéfices record au troisième semestre")
        assert r.label == "positif"
        assert r.score > 0.1
        assert r.source == "lexicon-fr"

    def test_french_positive_without_accents(self):
        """Insensible aux accents : « benefices » ≡ « bénéfices »."""
        r = sent.analyze_sentiment("apple annonce des benefices record au 3e semestre")
        assert r.label == "positif"
        assert r.score > 0.1

    def test_french_negative(self):
        r = sent.analyze_sentiment("La banque avertit d'une récession et de pertes importantes")
        assert r.label == "négatif"
        assert r.score < -0.1

    def test_french_negation_flips_valence(self):
        """« bons » est positif, mais « ne … pas bons » doit devenir négatif."""
        positive = sent.analyze_sentiment("les résultats sont bons")
        negated = sent.analyze_sentiment("les résultats ne sont pas bons")
        assert positive.score > 0
        assert negated.score < 0

    def test_french_negation_without_elision(self):
        r = sent.analyze_sentiment("l'entreprise n'a aucun croissance")  # elision + négation
        assert r.score <= 0

    def test_french_intensifier(self):
        """« fortement » amplifie la valence de « chute »."""
        plain = sent.analyze_sentiment("les actions chutent après l'annonce")
        strong = sent.analyze_sentiment("les actions chutent fortement après l'annonce")
        assert plain.score < 0
        assert strong.score < plain.score  # plus négatif

    def test_french_dampener(self):
        """« légèrement » atténue la valence (l'adverbe suit le verbe)."""
        plain = sent.analyze_sentiment("le cours remonte")
        mild = sent.analyze_sentiment("le cours remonte légèrement")
        assert plain.score > 0
        assert mild.score > 0
        assert abs(mild.score) < abs(plain.score)

    def test_mixed_language_french_wins(self):
        """Un titre FR contenant une marque anglaise reste traité en français."""
        r = sent.analyze_sentiment("Le cours de l'action Tesla chute après l'avertissement")
        assert r.label == "négatif"


class TestEnglishSentiment:
    def test_english_finance_positive(self):
        """« beats » n'est PAS dans le lexique VADER : le lexique financier EN
        doit prendre le relais et produire un score positif."""
        r = sent.analyze_sentiment("Apple beats earnings expectations")
        assert r.label == "positif"
        assert r.score > 0.1

    def test_english_negative(self):
        r = sent.analyze_sentiment("Apple misses forecasts and warns of weak demand")
        assert r.label == "négatif"
        assert r.score < 0

    def test_english_negation(self):
        positive = sent.analyze_sentiment("the company reports strong growth")
        negated = sent.analyze_sentiment("the company does not report strong growth")
        assert positive.score > 0
        assert negated.score < positive.score

    def test_unrecognized_text_is_neutral(self):
        r = sent.analyze_sentiment("xyzzy qwerty flurb")
        assert r.label == "neutre"
        assert r.score == 0.0

    def test_empty_text(self):
        r = sent.analyze_sentiment("")
        assert r.label == "neutre"
        assert r.score == 0.0


class TestAggregate:
    def test_aggregate_mixed(self):
        avg, label, details = sent.aggregate_sentiment(
            ["Apple publie des bénéfices records", "La demande chute fortement"]
        )
        assert len(details) == 2
        assert -1.0 <= avg <= 1.0
        assert label in ("positif", "neutre", "négatif")

    def test_aggregate_empty(self):
        avg, label, details = sent.aggregate_sentiment([])
        assert avg == 0.0 and label == "neutre" and details == []


class TestHeadlineFiltering:
    def test_aliases_for_symbol_and_company(self):
        aliases = sent._aliases_for("AAPL", "Apple Inc.")
        assert "aapl" in aliases
        assert "apple" in aliases
        # « Inc » est un mot générique : jamais utilisé comme alias.
        assert "inc" not in aliases

    def test_aliases_forex(self):
        aliases = sent._aliases_for("EUR/USD", "Euro / Dollar")
        assert {"eur", "usd"} <= aliases

    def test_no_aliases_returns_none(self):
        """Ticker trop court sans nom d'entreprise → pas de filtrage (None)."""
        assert sent._aliases_for("X", None) is None

    def test_filter_drops_off_topic_headlines(self):
        """Le cas remonté par la critique : titres SpaceX/Walmart dans AAPL."""
        titles = [
            "Prediction: SpaceX Will Be the Largest Company in the World by 2040",
            "Walmart, Costco see some panic-buying ahead of the holidays",
            "Apple unveils new iPhone with faster chip",
            "Apple's services revenue grows double digits",
            "Markets rally as the Fed pauses rate hikes",
        ]
        aliases = sent._aliases_for("AAPL", "Apple Inc.")
        kept = sent._filter_relevant(titles, aliases)
        assert kept == [
            "Apple unveils new iPhone with faster chip",
            "Apple's services revenue grows double digits",
        ]

    def test_filter_accepts_plural_and_accents(self):
        titles = ["Les actions d'Apple rebondissent", "Rien à voir avec la pomme"]
        aliases = sent._aliases_for("AAPL", "Apple Inc.")
        kept = sent._filter_relevant(titles, aliases)
        # « Apple » matche ; le second titre ne mentionne ni AAPL ni Apple.
        assert kept == ["Les actions d'Apple rebondissent"]

    def test_filter_deduplicates(self):
        titles = ["Apple hits record high", "apple hits record high"]
        aliases = sent._aliases_for("AAPL", "Apple Inc.")
        kept = sent._filter_relevant(titles, aliases)
        assert len(kept) == 1

    def test_filter_without_aliases_keeps_titles(self):
        titles = ["Anything goes", "Second title"]
        assert sent._filter_relevant(titles, None) == titles

    def test_fetch_headlines_filters_without_network(self, monkeypatch):
        """fetch_headlines applique le filtrage à ce que renvoient les flux."""
        raw = [
            "Prediction: SpaceX Will Be the Largest Company in the World by 2040",
            "Apple beats earnings expectations",
        ]

        def fake_rss(url, limit=30):
            return raw

        monkeypatch.setattr(sent, "_fetch_rss_titles", fake_rss)
        sent.clear_headline_cache()
        titles = sent.fetch_headlines("AAPL", company_name="Apple Inc.")
        sent.clear_headline_cache()
        assert titles == ["Apple beats earnings expectations"]
