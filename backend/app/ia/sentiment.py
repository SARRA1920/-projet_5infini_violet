"""Analyse de sentiment des actualités financières.

Approche actuelle : **VADER** (Valence Aware Dictionary and sEntiment
Reasoner), un lexique rules-based pur Python, sans téléchargement de modèle.
Léger, rapide, fonctionne hors-ligne — idéal pour un projet pédagogique.

Évolution prévue : remplacer VADER par **FinBERT** (ProsusAI/finbert),
pré-entraîné sur du texte financier. FinBERT est plus précis mais pèse
~420 Mo ; son intégration nécessite d'ajouter `transformers` + `torch` au
build Docker et de télécharger le modèle au premier démarrage. L'interface
publique (fonction `analyze_sentiment`) restera identique.

Source de news : pour l'instant un endpoint qui analyse un texte fourni par
l'utilisateur ou des titres simulés. L'intégration d'une API de news réelles
(NewsAPI, RSS Reuters/Bloomberg) est prévue mais nécessite une clé API —
on garde l'architecture prête (fonction `fetch_headlines` en stub).
"""

from __future__ import annotations

from dataclasses import dataclass

# Lexique financier minimal (français + anglais) pour un fallback sans VADER.
# Score entre -1 (très négatif) et +1 (très positif).
_FINANCIAL_LEXICON: dict[str, float] = {
    # Positif
    "hausse": 0.6, "bullish": 0.7, "rally": 0.6, "gain": 0.5, "profits": 0.5,
    "record": 0.5, "croissance": 0.6, "growth": 0.6, "beat": 0.5, "surpasse": 0.5,
    "optimiste": 0.5, "optimistic": 0.5, "dividende": 0.3, "dividend": 0.3,
    "acquisition": 0.4, "acquisition": 0.4, "breakthrough": 0.6,
    "rebond": 0.4, "rebound": 0.4, "remontée": 0.4,
    # Négatif
    "baisse": -0.6, "bearish": -0.7, "crash": -0.8, "loss": -0.5, "pertes": -0.5,
    " chute": -0.6, "chute": -0.6, "faillite": -0.8, "bankruptcy": -0.8,
    "récession": -0.6, "recession": -0.6, "warns": -0.5, "avertit": -0.5,
    "déclin": -0.5, "decline": -0.5, "miss": -0.4, "décevant": -0.4,
    "volatilité": -0.2, "volatility": -0.2, "incertitude": -0.3, "uncertainty": -0.3,
    "sell": -0.4, "vendre": -0.3, "downgrade": -0.5, "dégradation": -0.5,
}

_VADER_AVAILABLE = False
try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    _VADER_ANALYZER = SentimentIntensityAnalyzer()
    _VADER_AVAILABLE = True
except ImportError:
    _VADER_ANALYZER = None


@dataclass
class SentimentResult:
    text: str
    score: float       # -1 (très négatif) à +1 (très positif)
    label: str         # "positif" | "neutre" | "négatif"
    source: str        # "vader" | "lexicon"


def _label_from_score(score: float) -> str:
    if score > 0.05:
        return "positif"
    if score < -0.05:
        return "négatif"
    return "neutre"


def _lexicon_score(text: str) -> float:
    """Score par lexique financier (fallback si VADER absent)."""
    words = text.lower().split()
    scores = [_FINANCIAL_LEXICON.get(w, 0.0) for w in words]
    non_zero = [s for s in scores if s != 0.0]
    if not non_zero:
        return 0.0
    # Moyenne des mots du lexique présents, bornée à [-1, 1].
    return max(-1.0, min(1.0, sum(non_zero) / len(non_zero)))


def analyze_sentiment(text: str) -> SentimentResult:
    """Analyse le sentiment d'un texte (titre de news, commentaire).

    Utilise VADER si disponible, sinon le lexique financier de fallback.
    """
    if not text or not text.strip():
        return SentimentResult(text=text, score=0.0, label="neutre", source="lexicon")

    if _VADER_AVAILABLE:
        scores = _VADER_ANALYZER.polarity_scores(text)
        compound = float(scores["compound"])
        return SentimentResult(
            text=text, score=compound, label=_label_from_score(compound), source="vader"
        )

    score = _lexicon_score(text)
    return SentimentResult(
        text=text, score=score, label=_label_from_score(score), source="lexicon"
    )


@dataclass
class HeadlineSentiment:
    title: str
    score: float
    label: str


def analyze_headlines(titles: list[str]) -> list[HeadlineSentiment]:
    """Analyse une liste de titres de news. Renvoie un sentiment par titre."""
    out = []
    for t in titles:
        r = analyze_sentiment(t)
        out.append(HeadlineSentiment(title=t, score=r.score, label=r.label))
    return out


def aggregate_sentiment(titles: list[str]) -> tuple[float, str, list[HeadlineSentiment]]:
    """Score global agrégé sur plusieurs titres.

    Renvoie (score_moyen, label_global, détails_par_titre).
    """
    if not titles:
        return 0.0, "neutre", []
    details = analyze_headlines(titles)
    avg = sum(d.score for d in details) / len(details)
    return avg, _label_from_score(avg), details


def fetch_headlines(symbol: str) -> list[str]:
    """Récupère les titres d'actualité pour un symbole.

    STUB : renvoie des titres simulés pour la démo. L'intégration d'une vraie
    source (NewsAPI / RSS) nécessite une clé API — voir le commentaire en tête
    de fichier. À remplacer par un vrai fetch quand la clé sera disponible.
    """
    # Titres neutres par défaut pour ne pas biaiser l'agent tant qu'on n'a
    # pas de vraie source de news.
    return []
