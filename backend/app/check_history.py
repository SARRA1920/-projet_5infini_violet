"""Vérifie jusqu'où remonte l'historique Twelve Data (plan gratuit) pour les salles de crise.

Lancement : python -m app.check_history
Affiche, pour chaque test, le nombre de jours reçus et la première / dernière date.
(~1 minute : la limite est de 8 requêtes par minute.)
"""
from app.market_data import MarketDataError, _request, get_api_key

TESTS = [
    # (symbole, début, fin, crise)
    ("SPY", "2008-09-01", "2009-03-31", "Crise 2008"),
    ("JPM", "2008-09-01", "2009-03-31", "Crise 2008"),
    ("TLT", "2008-09-01", "2009-03-31", "Crise 2008"),
    ("XAU/USD", "2008-09-01", "2009-03-31", "Crise 2008"),
    ("SPY", "2020-02-01", "2020-06-30", "Covid 2020"),
    ("EUR/USD", "2020-02-01", "2020-06-30", "Covid 2020"),
    ("EWU", "2016-06-01", "2016-09-30", "Brexit 2016"),
    ("GBP/USD", "2016-06-01", "2016-09-30", "Brexit 2016"),
    ("EZU", "2011-07-01", "2011-12-31", "Dette euro 2011"),
    ("EUR/USD", "2011-07-01", "2011-12-31", "Dette euro 2011"),
]


def main() -> None:
    key = get_api_key()
    for symbol, start, end, label in TESTS:
        params = {
            "symbol": symbol,
            "interval": "1day",
            "start_date": start,
            "end_date": end,
            "outputsize": 5000,
            "order": "ASC",
            "apikey": key,
        }
        try:
            data = _request(params)
        except MarketDataError as exc:
            print(f"{label:16} {symbol:8} ERREUR réseau : {exc}")
            continue
        if data.get("status") == "error":
            print(f"{label:16} {symbol:8} refusé : {data.get('message', '?')[:90]}")
            continue
        values = data.get("values") or []
        if not values:
            print(f"{label:16} {symbol:8} aucune donnée")
        else:
            print(f"{label:16} {symbol:8} {len(values):4} jours  {values[0]['datetime'][:10]} -> {values[-1]['datetime'][:10]}")


if __name__ == "__main__":
    main()
