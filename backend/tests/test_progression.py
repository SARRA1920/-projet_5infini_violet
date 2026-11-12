from datetime import datetime

from app.models.models import CrisisRun, User, UserRole
from app.services import progression

NOW = datetime(2026, 11, 12, 12, 0, 0)


def run(db, user, key, score, status="finished"):
    r = CrisisRun(
        user_id=user.id, crisis_key=key, status=status, started_at=NOW, finished_at=NOW,
        day_index=10, cash=100000.0, positions={}, equity_curve=[], score=score,
        return_pct=score, max_drawdown_pct=1.0,
    )
    db.add(r)
    db.flush()
    return r


def player(db, name, level="debutant", role=UserRole.USER):
    u = User(email=f"{name}@x.com", username=name, hashed_password="x", role=role, level=level)
    db.add(u)
    db.flush()
    return u


def test_salle_validee_seulement_si_terminee_et_score_au_moins_3(db, seed_data):
    u = seed_data["user"]
    runs = [
        run(db, u, "covid_2020", 3.0),                      # juste au seuil : validée
        run(db, u, "brexit_2016", 2.9),                     # trop bas
        run(db, u, "euro_debt_2011", 50.0, status="timeout"),  # temps écoulé : ne valide pas
    ]
    assert progression.validated_keys(runs) == {"covid_2020"}


def test_progression_un_sur_deux(db, seed_data):
    u = seed_data["user"]
    u.level = "debutant"
    p = progression.progress(u.level, [run(db, u, "covid_2020", 8.0)])
    assert (p["done"], p["required"], p["next_level"]) == (1, 2, "intermediaire")


def test_montee_de_niveau_quand_les_deux_salles_sont_validees(db, seed_data):
    u = seed_data["user"]
    u.level = "debutant"
    runs = [run(db, u, "covid_2020", 5.0)]
    assert progression.apply_promotion(u, runs) is None
    assert u.level == "debutant"
    runs.append(run(db, u, "brexit_2016", 4.0))
    promo = progression.apply_promotion(u, runs)
    assert promo["from"] == "debutant" and promo["to"] == "intermediaire"
    assert u.level == "intermediaire"


def test_le_niveau_pro_est_le_maximum(db, seed_data):
    u = seed_data["user"]
    u.level = "pro"
    runs = [run(db, u, k, 10.0) for k in ("crisis_2008", "rates_2022")]
    assert progression.apply_promotion(u, runs) is None
    assert progression.progress("pro", runs)["next_level"] is None


def test_classement_meilleur_score_par_joueur_et_admin_exclu(db, seed_data):
    a = seed_data["user"]          # testuser
    b = player(db, "bob")
    admin = player(db, "boss", level=None, role=UserRole.ADMIN)
    run(db, a, "covid_2020", 5.0)
    run(db, a, "covid_2020", 9.0)             # meilleur essai de testuser
    run(db, b, "covid_2020", 7.0)
    run(db, admin, "covid_2020", 99.0)        # admin : exclu
    run(db, b, "brexit_2016", 20.0, status="timeout")  # incomplet : ne compte pas
    board = progression.leaderboard(db, me_id=a.id)

    covid = next(r for r in board["rooms"] if r["key"] == "covid_2020")["entries"]
    assert [(e["username"], e["score"], e["rank"]) for e in covid] == [("testuser", 9.0, 1), ("bob", 7.0, 2)]
    assert covid[0]["is_me"] and not covid[1]["is_me"]

    brexit = next(r for r in board["rooms"] if r["key"] == "brexit_2016")["entries"]
    assert brexit == []

    assert [(e["username"], e["total"]) for e in board["overall"]] == [("testuser", 9.0), ("bob", 7.0)]


def test_egalite_meme_rang(db, seed_data):
    a = seed_data["user"]
    b = player(db, "bob")
    run(db, a, "covid_2020", 6.0)
    run(db, b, "covid_2020", 6.0)
    entries = next(r for r in progression.leaderboard(db, a.id)["rooms"] if r["key"] == "covid_2020")["entries"]
    assert [e["rank"] for e in entries] == [1, 1]
