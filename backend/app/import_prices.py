"""Importe ~1 an de cours journaliers Twelve Data dans price_history (idempotent).

Lancement : python -m app.import_prices
Nécessite TWELVEDATA_API_KEY dans l'environnement (limite : 8 requêtes/minute).
"""
import sys
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.database import SessionLocal
from app.market_data import (
    AuthenticationError,
    MarketDataError,
    SymbolUnavailable,
    fetch_daily_prices,
    get_api_key,
)
from app.models.models import Asset, PriceHistory


def upsert_prices(db, asset_id: int, rows: list[dict]) -> int:
    """Insère les lignes, ou met à jour celles qui existent déjà (asset_id, date).

    L'API peut renvoyer plusieurs fois la même date : on garde la dernière occurrence
    (PostgreSQL refuse qu'un même INSERT ... ON CONFLICT touche deux fois une ligne).
    Retourne le nombre de doublons ignorés.
    """
    unique_rows = list({row["date"]: row for row in rows}.values())
    duplicates = len(rows) - len(unique_rows)

    stmt = insert(PriceHistory).values([{"asset_id": asset_id, **row} for row in unique_rows])
    stmt = stmt.on_conflict_do_update(
        constraint="uq_price_asset_date",
        set_={col: stmt.excluded[col] for col in ("open", "high", "low", "close", "volume")},
    )
    db.execute(stmt)
    return duplicates


def main() -> int:
    try:
        get_api_key()
    except AuthenticationError as exc:
        print(f"Erreur : {exc}")
        return 1

    imported: list[str] = []
    failed: list[str] = []
    today_utc = datetime.now(timezone.utc).date()

    with SessionLocal() as db:
        assets = db.scalars(select(Asset).order_by(Asset.symbol)).all()
        if not assets:
            print("Aucun actif en base : lancez d'abord python -m app.seed")
            return 1

        for asset in assets:
            try:
                rows = fetch_daily_prices(asset.symbol)
            except AuthenticationError as exc:
                print(f"Erreur d'authentification Twelve Data : {exc}. Arrêt de l'import.")
                db.rollback()
                return 1
            except SymbolUnavailable as exc:
                failed.append(f"{asset.symbol} : symbole non disponible chez Twelve Data ({exc})")
                print(f"  ! {failed[-1]}")
                continue
            except MarketDataError as exc:
                failed.append(f"{asset.symbol} : {exc}")
                print(f"  ! {failed[-1]}")
                continue

            # Bougie du jour suivant (fuseaux horaires) : incomplète, on l'ignore.
            kept = [row for row in rows if row["date"] <= today_utc]
            future = len(rows) - len(kept)
            if not kept:
                failed.append(f"{asset.symbol} : aucune ligne datée au plus tard du {today_utc}")
                print(f"  ! {failed[-1]}")
                continue

            duplicates = upsert_prices(db, asset.id, kept)
            db.commit()
            imported.append(
                f"{asset.symbol} : {len(kept) - duplicates} jours "
                f"({kept[0]['date']} -> {kept[-1]['date']}), "
                f"{duplicates} doublon(s) ignoré(s), {future} ligne(s) future(s) ignorée(s)"
            )
            print(f"  + {imported[-1]}")

    print(f"\nImportés ({len(imported)}) :")
    for line in imported:
        print(f"  + {line}")
    print(f"Échecs / non disponibles ({len(failed)}) :")
    for line in failed:
        print(f"  ! {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
