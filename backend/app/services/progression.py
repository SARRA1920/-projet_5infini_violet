"""Progression de la Formation : validation des salles, montée de niveau, classement.

Règles
- Une salle est « validée » par une tentative TERMINÉE (pas de temps écoulé) avec un score >= 3 points.
- Quand toutes les salles du niveau du joueur sont validées, il passe au niveau suivant.
- Le classement ne compte que les tentatives terminées ; les administrateurs n'y figurent pas.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.models import CrisisRun, User
from app.services import crisis as rooms

LEVELS = ["debutant", "intermediaire", "pro"]
LEVEL_LABELS = {"debutant": "Débutant", "intermediaire": "Intermédiaire", "pro": "Pro"}


def keys_by_level() -> dict[str, list[str]]:
    result: dict[str, list[str]] = {level: [] for level in LEVELS}
    for key in rooms.list_keys():
        result[rooms.load_crisis(key)["meta"]["level"]].append(key)
    return result


def is_validating(run) -> bool:
    return run.status == "finished" and run.score is not None and run.score >= rooms.VALIDATION_SCORE


def validated_keys(runs) -> set[str]:
    return {r.crisis_key for r in runs if is_validating(r)}


def progress(level: str | None, runs) -> dict:
    """Avancement vers le niveau suivant (salles validées parmi celles du niveau actuel)."""
    validated = validated_keys(runs)
    base = {"level": level, "validation_score": rooms.VALIDATION_SCORE, "validated": sorted(validated)}
    if level not in LEVELS or level == LEVELS[-1]:
        return {**base, "next_level": None, "next_label": None, "required": 0, "done": 0}
    current = keys_by_level()[level]
    nxt = LEVELS[LEVELS.index(level) + 1]
    return {
        **base,
        "next_level": nxt,
        "next_label": LEVEL_LABELS[nxt],
        "required": len(current),
        "done": len([k for k in current if k in validated]),
    }


def apply_promotion(user, runs) -> dict | None:
    """Fait monter l'utilisateur d'un ou plusieurs niveaux si toutes les salles du niveau sont validées."""
    if user.level not in LEVELS:
        return None
    start = user.level
    validated = validated_keys(runs)
    by_level = keys_by_level()
    while user.level != LEVELS[-1] and all(k in validated for k in by_level[user.level]):
        user.level = LEVELS[LEVELS.index(user.level) + 1]
    if user.level == start:
        return None
    return {"from": start, "to": user.level, "to_label": LEVEL_LABELS[user.level]}


def _ranked(rows: list[dict], key: str) -> list[dict]:
    """Classement à égalité : deux joueurs au même score ont le même rang."""
    rows.sort(key=lambda r: (-r[key], r["username"].lower()))
    previous, rank = None, 0
    for i, row in enumerate(rows):
        if row[key] != previous:
            rank = i + 1
            previous = row[key]
        row["rank"] = rank
    return rows


def leaderboard(db: Session, me_id: int, limit: int = 20) -> dict:
    pairs = db.execute(
        select(CrisisRun, User).join(User, User.id == CrisisRun.user_id).where(CrisisRun.status == "finished")
    ).all()

    best: dict[tuple[str, int], tuple[CrisisRun, User]] = {}
    for run, user in pairs:
        if getattr(user.role, "value", user.role) == "admin" or run.score is None:
            continue
        slot = (run.crisis_key, user.id)
        if slot not in best or run.score > best[slot][0].score:
            best[slot] = (run, user)

    per_room = []
    for key in rooms.list_keys():
        meta = rooms.load_crisis(key)["meta"]
        entries = [
            {
                "username": user.username,
                "score": run.score,
                "return_pct": run.return_pct,
                "max_drawdown_pct": run.max_drawdown_pct,
                "is_me": user.id == me_id,
            }
            for (k, _), (run, user) in best.items()
            if k == key
        ]
        per_room.append({"key": key, "name": meta["name"], "level": meta["level"], "entries": _ranked(entries, "score")[:limit]})

    totals: dict[int, dict] = {}
    for (_, uid), (run, user) in best.items():
        row = totals.setdefault(
            uid, {"username": user.username, "level": user.level, "total": 0.0, "rooms_done": 0, "is_me": uid == me_id}
        )
        row["total"] = round(row["total"] + run.score, 2)
        row["rooms_done"] += 1
    overall = _ranked(list(totals.values()), "total")
    return {"overall": overall[:limit], "rooms": per_room}
