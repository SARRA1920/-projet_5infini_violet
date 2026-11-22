"""Fil d'actualités en direct pour toute l'application (pop-ups + panneau).

Réutilise les briques de `sentiment.py` (fetch RSS, analyse de sentiment
multilingue, alias d'actifs) pour alimenter un **fil global** :

- **Marché** : flux RSS Yahoo Finance « Top Stories » de l'indice S&P 500
  (`^GSPC`), repli Google News « stock market » — les actualités générales
  du marché, sans filtrage par actif ;
- **Par actif** : les flux RSS de chaque actif suivi en base, récupérés
  **par rotation** (au plus `_ASSETS_PER_REFRESH` flux par appel, ceux dont
  le cache est le plus périmé d'abord). Sur quelques rafraîchissements,
  tous les actifs sont couverts sans marteler les sources RSS.

Chaque titre reçoit :
- un **id** stable (md5 du titre normalisé) — le frontend s'en sert pour ne
  jamais afficher deux fois le même pop-up ;
- les **symboles mentionnés** (0 → news « marché », sinon 1 à 3 tickers) ;
- un **sentiment** calculé par le moteur multilingue existant (FR/EN).

Politesse réseau : un seul appel déclenche au plus 1 + `_ASSETS_PER_REFRESH`
requêtes RSS (timeout 5 s chacune), et le fil agrégé est mis en cache
`_FEED_CACHE_TTL` secondes — cent utilisateurs qui rafraîchissent en même
temps ne déclenchent qu'une seule agrégation. Aucune erreur réseau ne remonte
à l'API : en cas de coupure, le fil renvoie le dernier contenu en cache.
"""

from __future__ import annotations

import hashlib
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import Asset

from .sentiment import _aliases_for, _strip_accents, analyze_sentiment

# ---------------------------------------------------------------------------
# Réglages (mêmes ordres de grandeur que sentiment.py)
# ---------------------------------------------------------------------------

_RSS_TIMEOUT = 5                       # secondes — on ne bloque jamais l'API
_MARKET_TTL = 1200                     # 20 min : cache du flux « marché »
_ASSET_TTL = 1200                      # 20 min : cache des flux par actif
_ASSETS_PER_REFRESH = 3                # flux d'actifs fetchés par appel au plus
_FEED_CACHE_TTL = 90                   # 90 s : fil agrégé partagé
_MAX_FEED_ITEMS = 24                   # taille du fil renvoyé
_MAX_SYMBOLS_PER_ITEM = 3              # tickers tagués par titre au plus

_MARKET_SYMBOL = "^GSPC"               # Top Stories Yahoo Finance (S&P 500)
_MARKET_FALLBACK_QUERY = "stock market"

# ---------------------------------------------------------------------------
# Structures
# ---------------------------------------------------------------------------


@dataclass
class NewsItem:
    """Une actualité du fil en direct."""

    id: str                            # md5 du titre normalisé (stable)
    title: str
    link: str | None = None
    symbols: list[str] = field(default_factory=list)   # [] = news « marché »
    score: float = 0.0                 # -1 (négatif) à +1 (positif)
    label: str = "neutre"
    source: str = "lexicon"            # moteur de sentiment réellement utilisé
    published: datetime | None = None  # date de publication RSS si fournie


# Caches en mémoire (partagés entre tous les utilisateurs du process).
_MARKET_CACHE: tuple[float, list[dict]] | None = None          # (ts, items bruts)
_ASSET_CACHE: dict[str, tuple[float, list[dict]]] = {}         # symbole → (ts, items bruts)
_ASSET_FETCHED_AT: dict[str, float] = {}                       # symbole → dernier fetch
_FEED_CACHE: tuple[float, list[NewsItem]] | None = None        # (ts, fil agrégé)


def clear_feed_cache() -> None:
    """Vide tous les caches du fil (utilisé par les tests)."""
    global _MARKET_CACHE, _FEED_CACHE
    _MARKET_CACHE = None
    _FEED_CACHE = None
    _ASSET_CACHE.clear()
    _ASSET_FETCHED_AT.clear()


# ---------------------------------------------------------------------------
# Récupération RSS : comme sentiment._fetch_rss_titles, mais on garde aussi
# le lien et la date de publication (utiles pour l'affichage « il y a X min »).
# ---------------------------------------------------------------------------


def _fetch_rss_items(url: str, limit: int = 30) -> list[dict]:
    """Télécharge un flux RSS et renvoie {title, link, published} par item."""
    req = urllib.request.Request(
        url, headers={"User-Agent": "TradeLab/1.0 (+projet pédagogique)"}
    )
    with urllib.request.urlopen(req, timeout=_RSS_TIMEOUT) as resp:
        raw = resp.read()
    root = ET.fromstring(raw)
    items: list[dict] = []
    for item in root.iter("item"):
        title = item.findtext("title")
        if not title:
            continue
        published = None
        raw_date = item.findtext("pubDate")
        if raw_date:
            try:
                published = parsedate_to_datetime(raw_date)
            except (TypeError, ValueError):
                published = None
        items.append({
            "title": unescape(title).strip(),
            "link": (item.findtext("link") or "").strip() or None,
            "published": published,
        })
        if len(items) >= limit:
            break
    return items


def _market_items() -> list[dict]:
    """Actualités générales du marché (Yahoo ^GSPC, repli Google News)."""
    global _MARKET_CACHE
    now = time.time()
    if _MARKET_CACHE and (now - _MARKET_CACHE[0]) < _MARKET_TTL:
        return _MARKET_CACHE[1]

    sym = urllib.parse.quote(_MARKET_SYMBOL)
    query = urllib.parse.quote(_MARKET_FALLBACK_QUERY)
    items: list[dict] = []
    for url in (
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US",
        f"https://news.google.com/rss/search?q={query}&hl=en&gl=US&ceid=US:en",
    ):
        try:
            items = _fetch_rss_items(url)
            break
        except Exception:
            continue
    _MARKET_CACHE = (now, items)
    return items


def _asset_items(symbol: str, company_name: str | None) -> list[dict]:
    """Titres d'un actif (flux Yahoo du ticker, repli Google News), en cache."""
    now = time.time()
    cached = _ASSET_CACHE.get(symbol)
    if cached and (now - cached[0]) < _ASSET_TTL:
        return cached[1]

    sym = urllib.parse.quote(symbol)
    if company_name:
        query = f'"{company_name}" OR {symbol} stock'
    else:
        query = f"{symbol} stock"
    items: list[dict] = []
    for url in (
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={sym}&region=US&lang=en-US",
        "https://news.google.com/rss/search?q="
        f"{urllib.parse.quote(query)}&hl=en&gl=US&ceid=US:en",
    ):
        try:
            items = _fetch_rss_items(url)
            break
        except Exception:
            continue
    _ASSET_CACHE[symbol] = (now, items)
    _ASSET_FETCHED_AT[symbol] = now
    return items


def _stale_assets(symbols: list[str]) -> list[str]:
    """Les actifs dont le cache de titres est périmé, le plus périmé d'abord.

    La rotation garantit qu'avec `_ASSETS_PER_REFRESH` fetch par appel, tous
    les actifs finissent par être rafraîchis même s'ils sont nombreux.
    """
    now = time.time()
    stale = [s for s in symbols if not _ASSET_CACHE.get(s)
             or (now - _ASSET_CACHE[s][0]) >= _ASSET_TTL]
    stale.sort(key=lambda s: (_ASSET_FETCHED_AT.get(s, 0.0), s))
    return stale[:_ASSETS_PER_REFRESH]


# ---------------------------------------------------------------------------
# Association titre → symboles : chaque titre est comparé aux alias de tous
# les actifs suivis (même logique que le filtre anti-hors-sujet de sentiment).
# ---------------------------------------------------------------------------


def _match_symbols(
    title: str, alias_patterns: list[tuple[str, list[re.Pattern]]]
) -> list[str]:
    """Renvoie les symboles mentionnés dans le titre (au plus 3, ordre stable)."""
    norm = _strip_accents(title.lower())
    matched: list[str] = []
    for symbol, patterns in alias_patterns:
        if any(p.search(norm) for p in patterns):
            matched.append(symbol)
        if len(matched) >= _MAX_SYMBOLS_PER_ITEM:
            break
    return matched


def _build_alias_patterns(
    assets: list[tuple[str, str | None]],
) -> list[tuple[str, list[re.Pattern]]]:
    """Compile les regex d'alias (ticker + mots du nom) pour chaque actif."""
    patterns: list[tuple[str, list[re.Pattern]]] = []
    for symbol, name in assets:
        aliases = _aliases_for(symbol, name)
        if not aliases:
            continue
        patterns.append(
            (symbol, [re.compile(rf"\b{re.escape(a)}s?\b") for a in sorted(aliases)])
        )
    return patterns


def _item_id(title: str) -> str:
    """Id stable d'un titre : deux polls qui voient le même titre → même id."""
    return hashlib.md5(_strip_accents(title.lower()).encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Agrégation du fil
# ---------------------------------------------------------------------------


def live_news(db: Session, limit: int = 20) -> list[NewsItem]:
    """Construit le fil d'actualités global (marché + actifs suivis).

    - lit les actifs en base pour connaître les alias de filtrage ;
    - récupère (avec caches + rotation) les flux RSS marché et par actif ;
    - score chaque titre avec le moteur de sentiment multilingue ;
    - déduplique, trie du plus récent au plus ancien et tronque à `limit`.

    Aucune exception réseau ne remonte : en cas de coupure totale, le fil
    renvoie ce qui reste en cache (éventuellement vide).
    """
    now = time.time()
    global _FEED_CACHE
    if _FEED_CACHE and (now - _FEED_CACHE[0]) < _FEED_CACHE_TTL:
        return _FEED_CACHE[1][:limit]

    assets = [
        (a.symbol, a.name) for a in db.scalars(select(Asset)).all()
    ]

    # Flux marché (cache 20 min) + rotation sur les flux par actif.
    raw: list[dict] = list(_market_items())
    for symbol in _stale_assets([s for s, _ in assets]):
        asset = next((a for a in assets if a[0] == symbol), None)
        try:
            raw.extend(_asset_items(symbol, asset[1] if asset else None))
        except Exception:
            continue

    alias_patterns = _build_alias_patterns(assets)

    items: list[NewsItem] = []
    seen_ids: set[str] = set()
    for entry in raw:
        title = (entry.get("title") or "").strip()
        if not title:
            continue
        item_id = _item_id(title)
        if item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        result = analyze_sentiment(title)
        items.append(NewsItem(
            id=item_id,
            title=title,
            link=entry.get("link"),
            symbols=_match_symbols(title, alias_patterns),
            score=result.score,
            label=result.label,
            source=result.source,
            published=entry.get("published"),
        ))

    # Du plus récent au plus ancien ; les titres sans date passent en dernier.
    items.sort(key=lambda i: (i.published is None, -(i.published.timestamp() if i.published else 0)))
    items = items[:_MAX_FEED_ITEMS]

    _FEED_CACHE = (now, items)
    return items[:limit]
