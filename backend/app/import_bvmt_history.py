"""Charge l'historique de cotation BVMT (Bourse de Tunis) dans la base.

Source : fichiers fournis par le professeur (cotations journalieres BVMT,
2018 -> octobre 2026), deja nettoyes en amont (obligations, droits de
souscription/attribution et lignes d'agregat exclus - seules les vraies
actions sont conservees) et consolides dans deux fichiers CSV :

  backend/data_import/bvmt_assets.csv  (symbol,name,asset_type)
  backend/data_import/bvmt_prices.csv  (symbol,date,open,high,low,close,volume)

Lancement :
    docker compose exec backend python -m app.import_bvmt_history

Idempotent : relancer le script ne duplique ni les actifs (symbole deja
present -> ignore) ni les prix (contrainte unique asset_id+date -> ignore).
"""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.database import SessionLocal
from app.models.models import Asset, AssetType, PriceHistory

DATA_DIR = Path(__file__).resolve().parent.parent / "data_import"
ASSETS_CSV = DATA_DIR / "bvmt_assets.csv"
PRICES_CSV = DATA_DIR / "bvmt_prices.csv"


def load_assets(db) -> dict[str, int]:
    if not ASSETS_CSV.exists():
        raise SystemExit(f"Fichier introuvable : {ASSETS_CSV}")

    created, skipped = 0, 0
    with open(ASSETS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            symbol = row["symbol"].strip()
            existing = db.scalar(select(Asset).where(Asset.symbol == symbol))
            if existing:
                skipped += 1
                continue
            db.add(Asset(symbol=symbol, name=row["name"].strip(), asset_type=AssetType.STOCK))
            created += 1
    db.commit()
    print(f"Actifs : {created} crees, {skipped} deja presents")

    return {a.symbol: a.id for a in db.scalars(select(Asset))}


def load_prices(db, asset_id_by_symbol: dict[str, int]) -> None:
    if not PRICES_CSV.exists():
        raise SystemExit(f"Fichier introuvable : {PRICES_CSV}")

    batch = []
    total_inserted = 0
    BATCH_SIZE = 5000

    def flush():
        nonlocal total_inserted
        if not batch:
            return
        stmt = pg_insert(PriceHistory.__table__).values(batch)
        stmt = stmt.on_conflict_do_nothing(constraint="uq_price_asset_date")
        db.execute(stmt)
        db.commit()
        total_inserted += len(batch)
        batch.clear()

    with open(PRICES_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            asset_id = asset_id_by_symbol.get(row["symbol"].strip())
            if asset_id is None:
                continue
            batch.append(
                {
                    "asset_id": asset_id,
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": int(float(row["volume"])) if row["volume"] else None,
                }
            )
            if len(batch) >= BATCH_SIZE:
                flush()
                print(f"  ... {total_inserted} lignes envoyees")
    flush()
    print(f"Prix : {total_inserted} lignes envoyees (les doublons existants sont ignores)")


def main() -> None:
    db = SessionLocal()
    try:
        asset_id_by_symbol = load_assets(db)
        load_prices(db, asset_id_by_symbol)
    finally:
        db.close()


if __name__ == "__main__":
    main()
