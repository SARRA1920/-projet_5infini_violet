"""Analyse de sentiment des actualités financières, multilingue FR/EN.

Corrige deux limites de la première version :
1. **VADER est anglophone.** Sur un texte français (« Apple annonce des
   bénéfices record »), VADER renvoie 0.0 : aucun mot reconnu. La détection
   de langue route désormais les textes français vers un **lexique financier
   français** (couvrant les termes haussiers/baissiers), avec gestion de la
   **négation** (« ne … pas », « sans », « aucun »), des **intensifiants**
   (« très », « fortement ») et des **atténuants** (« légèrement »). La
   comparaison est **insensible aux accents** (« benefices » ≡ « bénéfices »).
2. **Titres hors sujet.** Le flux RSS Yahoo Finance d'un ticker contient des
   actualités génériques (SpaceX, Walmart…) qui polluaient le score. Les
   titres sont maintenant **filtrés par alias** : ils ne sont conservés que
   s'ils mentionnent le ticker ou un mot significatif du nom de l'entreprise
   (ex. « Apple » pour AAPL). La requête Google News utilise aussi le nom
   de l'entreprise, ce qui améliore la pertinence des résultats.

Choix de moteur par langue :
- **FR** : lexique financier maison (pur Python, hors-ligne, aucune dépendance).
- **EN** : VADER si disponible (lexique généraliste anglais), sinon le lexique
  financier anglais de repli ; si VADER renvoie 0.0 alors que le lexique
  financier reconnaît des mots (« beats », « misses »…), le lexique financier
  prime car il est plus adapté au vocabulaire boursier.

Évolution prévue : remplacer le scoring par **FinBERT** (ProsusAI/finbert),
pré-entraîné sur du texte financier et disponible en version multilingue.
FinBERT pèse ~420 Mo et nécessite `transformers` + `torch` dans le build
Docker ; l'interface publique (`analyze_sentiment`) restera identique.
"""

from __future__ import annotations

import re
import time
import unicodedata
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import unescape

# ---------------------------------------------------------------------------
# Normalisation : minuscules + suppression des accents (« benefices » et
# « bénéfices » doivent matcher le même mot du lexique).
# ---------------------------------------------------------------------------


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFD", text) if not unicodedata.combining(ch)
    )


_TOKEN_RE = re.compile(r"[a-z'’]+")

# Élisions françaises : « n'est » → n + est ; « l'annonce » → annonce.
_ELISION_NEGATORS = {"n"}  # « n' » = négation élidée (« n'est pas bon »)


def _tokenize(text: str) -> list[str]:
    """Tokenise en minuscules, sans accents, en séparant les élisions."""
    lowered = _strip_accents(text.lower())
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(lowered):
        for part in raw.replace("’", "'").split("'"):
            if part:
                tokens.append(part)
    return tokens


# ---------------------------------------------------------------------------
# Lexique financier FR (clés sans accents). Score entre -1 et +1.
# ---------------------------------------------------------------------------

_FRENCH_LEXICON: dict[str, float] = {
    # Positif
    "benefice": 0.5, "benefices": 0.5, "profit": 0.5, "profits": 0.5,
    "profitable": 0.4, "hausse": 0.6, "hausser": 0.5, "augmentation": 0.5,
    "augmente": 0.5, "augmentent": 0.5, "croissance": 0.6, "rebond": 0.5,
    "rebondit": 0.5, "reprise": 0.4, "remontee": 0.4, "gagne": 0.5,
    "gagnent": 0.5, "gain": 0.5, "gains": 0.5, "progres": 0.4, "solide": 0.4,
    "solides": 0.4, "robuste": 0.4, "record": 0.5, "records": 0.5,
    "optimiste": 0.5, "optimistes": 0.5, "depasse": 0.5, "depassent": 0.5,
    "surpasse": 0.5, "surprenante": 0.4, "succes": 0.5, "victoire": 0.4,
    "rachat": 0.3, "acquisition": 0.4, "dividende": 0.3, "dividendes": 0.3,
    "expansion": 0.4, "innovation": 0.3, "innovations": 0.3, "partenariat": 0.3,
    "stimule": 0.4, "favorable": 0.4, "favorables": 0.4, "haussier": 0.6,
    "haussiere": 0.6, "excellent": 0.5, "excellente": 0.5, "excellents": 0.5,
    "meilleur": 0.4, "meilleure": 0.4, "meilleurs": 0.4, "amelioration": 0.4,
    "ameliore": 0.4, "ameliorent": 0.4, "accelere": 0.3, "bondit": 0.5,
    "envole": 0.5, "valorisation": 0.2, "soutien": 0.2, "relance": 0.3,
    "relancee": 0.3, "bon": 0.3, "bons": 0.3, "bonne": 0.3, "bonnes": 0.3,
    "remonte": 0.4, "remontent": 0.4, "reussite": 0.4, "favorise": 0.3,
    # Négatif
    "baisse": -0.6, "baissent": -0.5, "baisser": -0.5, "chute": -0.7,
    "chutes": -0.7, "chutent": -0.7, "chuter": -0.6, "recul": -0.5,
    "recule": -0.5, "reculent": -0.5, "plonge": -0.7, "plongent": -0.7,
    "plongeon": -0.7, "effondrement": -0.8, "effondre": -0.8, "krach": -0.8,
    "crash": -0.8, "faillite": -0.8, "banqueroute": -0.8, "defaut": -0.6,
    "defauts": -0.6, "perte": -0.5, "pertes": -0.5, "perd": -0.4,
    "perdent": -0.4, "mevente": -0.5, "avertissement": -0.5, "avertit": -0.5,
    "avertissent": -0.5, "previent": -0.5, "degradation": -0.5, "degrade": -0.5,
    "abaisse": -0.4, "recession": -0.6, "crise": -0.6, "incertitude": -0.4,
    "incertain": -0.4, "volatile": -0.3, "volatilite": -0.2, "pessimiste": -0.5,
    "litige": -0.4, "litiges": -0.4, "amende": -0.4, "amendes": -0.4,
    "enquete": -0.4, "enquetes": -0.4, "scandale": -0.7, "fraude": -0.7,
    "soupcon": -0.4, "poursuite": -0.4, "poursuites": -0.4, "sanction": -0.5,
    "sanctions": -0.5, "licenciements": -0.5, "deficit": -0.5, "deficits": -0.5,
    "dette": -0.3, "dettes": -0.4, "endettement": -0.4, "decevant": -0.5,
    "decevante": -0.5, "deception": -0.5, "manque": -0.3, "rate": -0.4,
    "rater": -0.4, "mediorcre": -0.4, "melange": -0.2, "fragilise": -0.4,
    "affaiblit": -0.5, "affaiblissement": -0.5,
}

# Négation FR : la négation PRÉCÈDE le mot porteur de sens dans un rayon de
# `NEGATION_WINDOW` tokens (« les résultats ne sont pas bons »).
_FR_NEGATORS = {"ne", "pas", "aucun", "aucune", "sans", "jamais", "nul", "nulle"}
_FR_INTENSIFIERS = {
    "tres", "extremement", "fortement", "nettement", "considerablement",
    "largement", "brutalement", "vivement", "serieusement", "fort", "forte",
    "forts", "severe", "severement", "massivement", "vraiment",
}
_FR_DAMPENERS = {"legerement", "legere", "leger", "moderement", "relativement"}

# ---------------------------------------------------------------------------
# Lexique financier EN de repli (utilisé si VADER est absent, ou si VADER
# renvoie 0.0 alors que ces mots sont reconnus — son lexique généraliste ne
# connaît pas « beats », « misses »…).
# ---------------------------------------------------------------------------

_EN_LEXICON: dict[str, float] = {
    "bullish": 0.7, "bearish": -0.7, "rally": 0.6, "rallies": 0.6, "surge": 0.6,
    "surges": 0.6, "surging": 0.6, "soar": 0.6, "soars": 0.6, "soaring": 0.6,
    "jump": 0.5, "jumps": 0.5, "jumped": 0.5, "climb": 0.4, "climbs": 0.4,
    "beat": 0.5, "beats": 0.5, "beating": 0.5, "gain": 0.5, "gains": 0.5,
    "gained": 0.5, "record": 0.5, "growth": 0.6, "grow": 0.4, "grows": 0.4,
    "upbeat": 0.4, "optimistic": 0.5, "optimism": 0.4, "dividend": 0.3,
    "dividends": 0.3, "acquisition": 0.4, "breakthrough": 0.6, "rebound": 0.4,
    "rebounds": 0.4, "recovery": 0.4, "upgrade": 0.5, "upgrades": 0.5,
    "raised": 0.3, "raises": 0.3, "profit": 0.5, "profits": 0.5, "strong": 0.4,
    "stronger": 0.4, "strength": 0.4, "outperform": 0.5, "outperforms": 0.5,
    "fall": -0.5, "falls": -0.5, "fell": -0.5, "falling": -0.5, "drop": -0.5,
    "drops": -0.5, "dropped": -0.5, "plunge": -0.7, "plunges": -0.7,
    "slump": -0.6, "slumps": -0.6, "tumble": -0.6, "tumbles": -0.6,
    "sink": -0.5, "sinks": -0.5, "crash": -0.8, "miss": -0.4, "misses": -0.4,
    "missed": -0.4, "loss": -0.5, "losses": -0.5, "warn": -0.5, "warns": -0.5,
    "warned": -0.5, "warning": -0.5, "downgrade": -0.5, "downgrades": -0.5,
    "cut": -0.3, "cuts": -0.3, "recession": -0.6, "bankruptcy": -0.8,
    "default": -0.6, "decline": -0.5, "declines": -0.5, "weak": -0.4,
    "weaker": -0.4, "weakness": -0.4, "fear": -0.4, "fears": -0.4,
    "concern": -0.3, "concerns": -0.3, "lawsuit": -0.4, "probe": -0.4,
    "fraud": -0.7, "scandal": -0.7, "layoffs": -0.5, "shortfall": -0.4,
    "pessimistic": -0.5, "uncertainty": -0.3, "volatile": -0.3,
    "volatility": -0.2, "underperform": -0.5,
}

_EN_NEGATORS = {"not", "no", "never", "without", "hardly", "barely"}
_EN_INTENSIFIERS = {
    "very", "extremely", "sharply", "significantly", "strongly", "severely",
    "massively", "hugely",
}
_EN_DAMPENERS = {"slightly", "modestly", "somewhat", "marginally", "mildly"}

# ---------------------------------------------------------------------------
# Détection de langue : mots-outils fréquents + couverture lexicale.
# ---------------------------------------------------------------------------

_FRENCH_MARKERS = {
    "le", "la", "les", "des", "du", "de", "un", "une", "au", "aux", "et",
    "est", "sont", "dans", "pour", "avec", "sur", "sous", "qui", "que",
    "quoi", "dont", "ce", "cet", "cette", "ces", "son", "sa", "ses", "leur",
    "leurs", "plus", "moins", "tres", "bien", "apres", "avant", "chez",
    "donc", "ainsi", "alors", "aussi", "mais", "entre", "vers", "depuis",
    "pendant", "selon", "sera", "seront", "ete", "etait", "ont", "annonce",
    "annonces", "publie", "publient", "resultats", "resultat", "trimestre",
    "semestre", "chiffre", "chiffres", "action", "actions", "bourse",
    "titre", "titres", "valeurs", "valeur", "cours", "marche", "marches",
    "banque", "banques", "entreprise", "entreprises", "gouvernement",
    "francais", "paris", "cac",
}

_ENGLISH_MARKERS = {
    "the", "of", "and", "to", "in", "is", "are", "was", "were", "be", "been",
    "being", "has", "have", "had", "will", "would", "could", "should", "for",
    "with", "on", "at", "from", "by", "that", "this", "these", "those", "it",
    "its", "as", "after", "before", "amid", "vs", "more", "most", "than",
    "then", "when", "while", "about", "into", "over", "under", "new", "says",
    "said", "report", "reports", "shares", "stock", "stocks", "market",
    "markets", "price", "prices", "earnings", "revenue", "quarterly", "ceo",
    "inc", "corp", "ltd", "plc", "which", "their", "they", "up", "down",
    "out", "off", "but", "or", "if", "so", "not", "no", "now", "how", "why",
    "what", "who", "year", "years", "million", "billion", "percent", "us",
    "uk", "biggest", "largest", "world",
}

_NEGATION_WINDOW = 3  # tokens de distance max entre la négation et le mot


def _detect_language(text: str) -> str:
    """Détecte 'fr' ou 'en' : mots-outils d'abord, couverture lexicale ensuite."""
    tokens = _tokenize(text)
    fr_markers = sum(1 for t in tokens if t in _FRENCH_MARKERS)
    en_markers = sum(1 for t in tokens if t in _ENGLISH_MARKERS)
    if fr_markers > en_markers:
        return "fr"
    if en_markers > fr_markers:
        return "en"
    # Égalité (texte télégraphique) : on regarde quel lexique reconnaît le plus.
    fr_cov = sum(1 for t in tokens if t in _FRENCH_LEXICON)
    en_cov = sum(1 for t in tokens if t in _EN_LEXICON)
    if _VADER_AVAILABLE:
        en_cov += sum(1 for t in tokens if t in _VADER_ANALYZER.lexicon)
    if fr_cov > en_cov:
        return "fr"
    return "en"


def _lexicon_score(
    text: str,
    lexicon: dict[str, float],
    negators: set[str],
    intensifiers: set[str],
    dampeners: set[str],
) -> tuple[float, int]:
    """Score par lexique avec négation, intensifiants et atténuants.

    Renvoie (score borné [-1, 1], nombre de mots reconnus). La négation
    inverse la valence du mot (amortie à 80 %) si elle apparaît dans les
    `_NEGATION_WINDOW` tokens précédents — « ne … pas bons » → négatif.
    """
    tokens = _tokenize(text)
    scores: list[float] = []
    for i, tok in enumerate(tokens):
        val = lexicon.get(tok)
        if val is None:
            continue
        negated = any(
            tokens[j] in negators or tokens[j] in _ELISION_NEGATORS
            for j in range(max(0, i - _NEGATION_WINDOW), i)
        )
        # Modificateurs : en français, l'adverbe suit le verbe (« chute
        # fortement ») et l'adjectif précède le nom (« forte baisse ») — on
        # regarde donc le token précédent ET le token suivant.
        prev = tokens[i - 1] if i > 0 else None
        nxt = tokens[i + 1] if i + 1 < len(tokens) else None
        adj = 1.0
        if prev in intensifiers or nxt in intensifiers:
            adj = 1.5
        elif prev in dampeners or nxt in dampeners:
            adj = 0.5
        if negated:
            val = -val * 0.8
        scores.append(val * adj)
    if not scores:
        return 0.0, 0
    return max(-1.0, min(1.0, sum(scores) / len(scores))), len(scores)


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
    source: str        # "vader" | "lexicon" | "lexicon-fr"


def _label_from_score(score: float) -> str:
    if score > 0.05:
        return "positif"
    if score < -0.05:
        return "négatif"
    return "neutre"


def analyze_sentiment(text: str) -> SentimentResult:
    """Analyse le sentiment d'un texte financier, en français ou en anglais.

    - texte français → lexique financier FR (VADER ne comprend pas le
      français : il renverrait 0.0) ;
    - texte anglais → VADER si disponible, sinon lexique EN ; si VADER
      renvoie 0.0 mais que le lexique financier reconnaît des mots, le
      lexique financier prime (vocabulaire boursier plus précis).
    """
    if not text or not text.strip():
        return SentimentResult(text=text, score=0.0, label="neutre", source="lexicon")

    if _detect_language(text) == "fr":
        score, _ = _lexicon_score(
            text, _FRENCH_LEXICON, _FR_NEGATORS, _FR_INTENSIFIERS, _FR_DAMPENERS
        )
        return SentimentResult(
            text=text, score=score, label=_label_from_score(score), source="lexicon-fr"
        )

    if _VADER_AVAILABLE:
        compound = float(_VADER_ANALYZER.polarity_scores(text)["compound"])
        score, coverage = _lexicon_score(
            text, _EN_LEXICON, _EN_NEGATORS, _EN_INTENSIFIERS, _EN_DAMPENERS
        )
        # VADER neutre alors que le lexique financier reconnaît des mots :
        # le lexique financier est plus pertinent pour le vocabulaire boursier.
        if coverage > 0 and abs(compound) < abs(score):
            return SentimentResult(
                text=text, score=score, label=_label_from_score(score), source="lexicon"
            )
        if compound != 0.0 or coverage == 0:
            return SentimentResult(
                text=text,
                score=compound,
                label=_label_from_score(compound),
                source="vader",
            )
        return SentimentResult(
            text=text, score=score, label=_label_from_score(score), source="lexicon"
        )

    score, _ = _lexicon_score(
        text, _EN_LEXICON, _EN_NEGATORS, _EN_INTENSIFIERS, _EN_DAMPENERS
    )
    return SentimentResult(
        text=text, score=score, label=_label_from_score(score), source="lexicon"
    )


@dataclass
class HeadlineSentiment:
    title: str
    score: float
    label: str
    source: str = "lexicon"   # "vader" | "lexicon" | "lexicon-fr"


def analyze_headlines(titles: list[str]) -> list[HeadlineSentiment]:
    """Analyse une liste de titres de news. Renvoie un sentiment par titre."""
    out = []
    for t in titles:
        r = analyze_sentiment(t)
        out.append(HeadlineSentiment(
            title=t, score=r.score, label=r.label, source=r.source,
        ))
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


# ---------------------------------------------------------------------------
# Récupération des titres + **filtrage par alias** : on ne garde qu'un titre
# mentionnant le ticker ou un mot significatif du nom de l'entreprise.
# ---------------------------------------------------------------------------

# Cache en mémoire des titres par symbole (TTL 15 min).
_HEADLINE_CACHE: dict[str, tuple[float, list[str]]] = {}
_HEADLINE_CACHE_TTL = 900          # 15 minutes
_RSS_TIMEOUT = 5                   # secondes — on ne bloque jamais l'API
_MAX_HEADLINES = 10
_RAW_HEADLINES = 30                # titres bruts analysés avant filtrage

# Mots génériques du nom d'entreprise (jamais utilisés comme alias) : ils
# apparaissent dans trop de titres hors sujet (« year », « group », « Inc »…).
_GENERIC_NAME_WORDS = {
    "inc", "corp", "corporation", "company", "companies", "co", "sa", "sas",
    "nv", "ltd", "limited", "plc", "group", "holding", "holdings", "ag",
    "spa", "oyj", "ab", "asa", "trust", "etf", "fund", "the", "and", "of",
    "for", "new", "year", "years", "best", "top", "big", "biggest", "large",
    "largest", "world", "first", "global", "international", "market",
    "markets", "stock", "stocks", "share", "shares", "price", "prices",
    "high", "low", "index", "treasury", "bond", "bonds", "his", "her",
    "their", "its", "our", "your", "all", "one", "two", "three", "next",
    "last", "week", "month", "day", "today", "amid", "after", "before",
    "will", "says", "said", "report", "reports", "why", "how", "what",
    "when", "who", "are", "was", "were", "has", "have", "had", "not", "but",
    "can", "may", "now", "us", "uk",
}


def _aliases_for(symbol: str, company_name: str | None) -> set[str] | None:
    """Construit les alias de filtrage (ticker + mots du nom d'entreprise).

    Renvoie None si aucun alias exploitable : dans ce cas on ne filtre pas
    (mieux vaut un score bruité qu'un score vide).
    """
    aliases: set[str] = set()
    for part in re.split(r"[/\-\s]+", (symbol or "").strip().upper()):
        part = _strip_accents(part.lower())
        if len(part) >= 3 and part.isalpha():
            aliases.add(part)
    if company_name:
        for tok in re.findall(r"[A-Za-zÀ-ÿ]+", company_name):
            tok = _strip_accents(tok.lower())
            if len(tok) >= 3 and tok not in _GENERIC_NAME_WORDS:
                aliases.add(tok)
    return aliases or None


def _filter_relevant(titles: list[str], aliases: set[str] | None) -> list[str]:
    """Ne garde que les titres mentionnant un alias (ticker ou entreprise).

    Le match est insensible à la casse/aux accents et accepte le pluriel
    (« apple » matche « Apple's » et « apples »). Les doublons sont retirés.
    """
    if aliases is None:
        return titles[:_MAX_HEADLINES]
    patterns = [re.compile(rf"\b{re.escape(a)}s?\b") for a in aliases]
    out: list[str] = []
    seen: set[str] = set()
    for title in titles:
        norm = _strip_accents(title.lower())
        if norm in seen:
            continue
        if any(p.search(norm) for p in patterns):
            seen.add(norm)
            out.append(title)
    return out[:_MAX_HEADLINES]


def _fetch_rss_titles(url: str, limit: int = _RAW_HEADLINES) -> list[str]:
    """Télécharge un flux RSS et renvoie la liste des titres d'items."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "TradeLab/1.0 (+projet pédagogique)"}
    )
    with urllib.request.urlopen(req, timeout=_RSS_TIMEOUT) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    titles = []
    for item in root.iter("item"):
        t = item.findtext("title")
        if t:
            titles.append(unescape(t).strip())
        if len(titles) >= limit:
            break
    return titles


def _yahoo_headlines(symbol: str) -> list[str]:
    """Flux RSS Yahoo Finance — titres spécifiques au ticker, sans clé API."""
    sym = urllib.parse.quote(symbol)
    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline"
        f"?s={sym}&region=US&lang=en-US"
    )
    return _fetch_rss_titles(url)


def _google_headlines(symbol: str, company_name: str | None) -> list[str]:
    """Repli : flux RSS Google News ; la requête privilégie le nom d'entreprise."""
    if company_name:
        query = f'"{company_name}" OR {symbol} stock'
    else:
        query = f"{symbol} stock"
    url = (
        "https://news.google.com/rss/search"
        f"?q={urllib.parse.quote(query)}&hl=en&gl=US&ceid=US:en"
    )
    return _fetch_rss_titles(url)


def fetch_headlines(symbol: str, company_name: str | None = None) -> list[str]:
    """Récupère les titres d'actualité **pertinents** pour un actif.

    Sources : Yahoo Finance RSS (spécifique au ticker), repli Google News.
    Les titres sont ensuite **filtrés par alias** : seul un titre mentionnant
    le ticker ou un mot significatif du nom de l'entreprise est conservé
    (un flux AAPL ne contient donc plus de titres SpaceX ou Walmart). Les
    titres sont mis en cache 15 minutes ; toute erreur réseau est absorbée
    (liste vide plutôt qu'une exception — le sentiment ne contribue alors
    simplement pas au score de l'agent).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return []

    now = time.time()
    cached = _HEADLINE_CACHE.get(sym)
    if cached and (now - cached[0]) < _HEADLINE_CACHE_TTL:
        return cached[1]

    raw_titles: list[str] = []
    for source in (
        lambda: _yahoo_headlines(sym),
        lambda: _google_headlines(sym, company_name),
    ):
        try:
            raw_titles.extend(source())
            if len(raw_titles) >= _RAW_HEADLINES:
                break
        except Exception:
            continue

    aliases = _aliases_for(sym, company_name)
    titles = _filter_relevant(raw_titles, aliases)
    _HEADLINE_CACHE[sym] = (now, titles)
    return titles


def clear_headline_cache() -> None:
    """Vide le cache des titres (utilisé par les tests)."""
    _HEADLINE_CACHE.clear()
