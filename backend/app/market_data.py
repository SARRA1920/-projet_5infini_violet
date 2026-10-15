"""Client minimal pour l'API Twelve Data (cours journaliers)."""
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://api.twelvedata.com/time_series"

# Plan gratuit : 8 requêtes par minute -> au moins 8 s entre deux appels.
MIN_INTERVAL_SECONDS = 8.0
RATE_LIMIT_WAIT_SECONDS = 60.0
HTTP_TIMEOUT_SECONDS = 30

_last_call = 0.0


class MarketDataError(Exception):
    """Erreur générique lors de la récupération des cours."""


class SymbolUnavailable(MarketDataError):
    """Symbole inconnu de Twelve Data, ou non accessible avec le plan actuel."""


class AuthenticationError(MarketDataError):
    """Clé API absente ou refusée : inutile de continuer."""


def get_api_key() -> str:
    key = os.getenv("TWELVEDATA_API_KEY", "").strip()
    if not key:
        raise AuthenticationError("TWELVEDATA_API_KEY est vide ou absente de l'environnement")
    return key


def _throttle() -> None:
    """Attend si nécessaire pour respecter la limite de requêtes par minute."""
    global _last_call
    wait = MIN_INTERVAL_SECONDS - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _request(params: dict, attempts: int = 2) -> dict:
    url = f"{BASE_URL}?{urllib.parse.urlencode(params)}"
    for attempt in range(1, attempts + 1):
        _throttle()
        try:
            with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_SECONDS) as response:
                body = response.read()
            break
        except urllib.error.HTTPError as exc:
            # Twelve Data renvoie parfois le détail de l'erreur dans le corps d'une réponse HTTP 4xx.
            body = exc.read()
            break
        except (urllib.error.URLError, http.client.HTTPException, OSError) as exc:
            # Coupure en cours de transfert (IncompleteRead), timeout, etc. : on réessaie.
            # On n'affiche pas l'URL : elle contient la clé API.
            if attempt == attempts:
                raise MarketDataError(f"erreur réseau ({type(exc).__name__})") from None

    try:
        return json.loads(body)
    except ValueError:
        raise MarketDataError("réponse non JSON de Twelve Data") from None


def fetch_daily_prices(symbol: str, days: int = 365) -> list[dict]:
    """Retourne les cours journaliers (ordre chronologique) des `days` derniers jours.

    Chaque élément : {date, open, high, low, close, volume} (volume = None si absent,
    par exemple pour les devises).
    """
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": (date.today() - timedelta(days=days)).isoformat(),
        "outputsize": 5000,
        "order": "ASC",
        "apikey": get_api_key(),
    }

    data = _request(params)
    if data.get("code") == 429:
        time.sleep(RATE_LIMIT_WAIT_SECONDS)
        data = _request(params)

    if data.get("status") == "error":
        code = data.get("code")
        message = data.get("message", "erreur inconnue")
        if code in (401,):
            raise AuthenticationError(message)
        if code in (400, 403, 404):
            raise SymbolUnavailable(message)
        raise MarketDataError(f"code {code} : {message}")

    values = data.get("values")
    if not values:
        raise SymbolUnavailable("aucune donnée renvoyée")

    try:
        return [
            {
                "date": date.fromisoformat(v["datetime"][:10]),
                "open": Decimal(v["open"]),
                "high": Decimal(v["high"]),
                "low": Decimal(v["low"]),
                "close": Decimal(v["close"]),
                "volume": int(v["volume"]) if v.get("volume") not in (None, "") else None,
            }
            for v in values
        ]
    except (KeyError, ValueError, ArithmeticError):
        raise MarketDataError("format de données inattendu") from None
