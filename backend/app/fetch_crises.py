"""Télécharge une fois les cours historiques des salles de crise et les fige en fichiers JSON.

Lancement : python -m app.fetch_crises
- Lit app/data/crises_catalog.json
- Écrit app/data/crises/<crise>.json  (ces fichiers sont versionnés dans Git)
- Reprenable : un actif déjà présent dans un fichier n'est pas retéléchargé.
Nécessite TWELVEDATA_API_KEY ; compter ~6 minutes (8 requêtes par minute au maximum).
"""
import json
import time
from pathlib import Path

from app.market_data import (
    RATE_LIMIT_WAIT_SECONDS,
    AuthenticationError,
    MarketDataError,
    _request,
    get_api_key,
)

DATA = Path(__file__).resolve().parent / "data"
CATALOG = DATA / "crises_catalog.json"
OUT = DATA / "crises"


def fetch(symbol: str, start: str, end: str, key: str) -> list[dict]:
    params = {
        "symbol": symbol,
        "interval": "1day",
        "start_date": start,
        "end_date": end,
        "outputsize": 5000,
        "order": "ASC",
        "apikey": key,
    }
    data = _request(params)
    if data.get("code") == 429:
        time.sleep(RATE_LIMIT_WAIT_SECONDS)
        data = _request(params)
    if data.get("status") == "error":
        raise MarketDataError(str(data.get("message", "erreur inconnue"))[:100])
    rows = {}
    for v in data.get("values") or []:
        rows[v["datetime"][:10]] = [
            round(float(v["open"]), 4),
            round(float(v["high"]), 4),
            round(float(v["low"]), 4),
            round(float(v["close"]), 4),
        ]
    return [[d, *rows[d]] for d in sorted(rows)]  # [date, open, high, low, close]


def main() -> int:
    try:
        key = get_api_key()
    except AuthenticationError as exc:
        print(f"Erreur : {exc}")
        return 1
    OUT.mkdir(exist_ok=True)
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["crises"]
    failures = []

    for crisis in catalog:
        path = OUT / f"{crisis['key']}.json"
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"prices": {}}
        doc.update({k: v for k, v in crisis.items() if k != "symbols"})
        for symbol in crisis["symbols"]:
            if doc["prices"].get(symbol):
                print(f"{crisis['key']:15} {symbol:8} déjà présent")
                continue
            try:
                rows = fetch(symbol, crisis["start"], crisis["end"], key)
            except MarketDataError as exc:
                print(f"{crisis['key']:15} {symbol:8} ÉCHEC : {exc}")
                failures.append((crisis["key"], symbol))
                continue
            if not rows:
                print(f"{crisis['key']:15} {symbol:8} ÉCHEC : aucune donnée")
                failures.append((crisis["key"], symbol))
                continue
            doc["prices"][symbol] = rows
            print(f"{crisis['key']:15} {symbol:8} {len(rows):4} jours  {rows[0][0]} -> {rows[-1][0]}")
            path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        path.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print("\nÉchecs :", failures if failures else "aucun")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
