from datetime import datetime, timedelta

import pytest

from app.services import crisis as rooms

T0 = datetime(2026, 11, 8, 10, 0, 0)


def new_run(db, user, key="covid_2020"):
    run = rooms.start_run(user.id, key, T0)
    db.add(run)
    db.flush()
    return run


# ---------- score ----------
def test_score_exemple_gain_et_perte_moderee():
    # +10 % final, sommet 120 000 puis 110 000 : perte max 8,33 % -> 10 - 4,17 = 5,83
    r = rooms.score_curve([100_000, 120_000, 110_000])
    assert r["return_pct"] == 10.0
    assert r["max_drawdown_pct"] == pytest.approx(8.33, abs=0.01)
    assert r["score"] == pytest.approx(5.83, abs=0.01)


def test_score_gain_avec_grosse_perte_est_negatif():
    # +14 % final mais passé par -30 % depuis le sommet : 14 - 15 = -1
    r = rooms.score_curve([100_000, 150_000, 105_000, 114_000])
    assert r["return_pct"] == 14.0
    assert r["max_drawdown_pct"] == 30.0
    assert r["score"] == -1.0


def test_score_sans_rien_faire_est_zero():
    assert rooms.score_curve([100_000, 100_000, 100_000])["score"] == 0.0


# ---------- temps ----------
def test_formule_du_temps():
    for key, minutes in [("covid_2020", 21), ("brexit_2016", 22), ("euro_debt_2011", 22),
                         ("oil_2014", 27), ("crisis_2008", 30), ("rates_2022", 28)]:
        c = rooms.load_crisis(key)
        level = c["meta"]["level"]
        expected = 60 + len(c["calendar"]) * rooms.SECONDS_PER_DAY[level]
        assert rooms.time_limit_seconds(c) == expected
        assert round(expected / 60) == minutes


def test_les_six_salles_se_chargent():
    assert len(rooms.list_keys()) == 6
    for key in rooms.list_keys():
        c = rooms.load_crisis(key)
        assert len(c["calendar"]) > 50
        first = c["calendar"][0]
        assert any(rooms.price_at(c, s, 0) for s in c["series"]), first


# ---------- acces par niveau ----------
def test_acces_par_niveau():
    covid = rooms.load_crisis("covid_2020")
    y2008 = rooms.load_crisis("crisis_2008")
    assert rooms.can_enter("debutant", False, covid)
    assert not rooms.can_enter("debutant", False, y2008)
    assert rooms.can_enter("pro", False, covid)
    assert rooms.can_enter(None, True, y2008)  # admin
    assert not rooms.can_enter(None, False, covid)


# ---------- ordres ----------
def test_achat_puis_vente_au_meme_prix_ne_change_rien(db, seed_data):
    run = new_run(db, seed_data["user"])
    c = rooms.load_crisis("covid_2020")
    price = rooms.price_at(c, "SPY", 0)
    rooms.trade(run, "SPY", "buy", 100, T0)
    assert run.cash == pytest.approx(100_000 - 100 * price)
    assert run.positions == {"SPY": 100.0}
    rooms.trade(run, "SPY", "sell", 100, T0)
    assert run.cash == pytest.approx(100_000)
    assert run.positions == {}


def test_achat_trop_cher_refuse(db, seed_data):
    run = new_run(db, seed_data["user"])
    with pytest.raises(rooms.RoomError):
        rooms.trade(run, "SPY", "buy", 1_000_000, T0)


def test_vente_a_decouvert_refusee(db, seed_data):
    run = new_run(db, seed_data["user"])
    with pytest.raises(rooms.RoomError):
        rooms.trade(run, "SPY", "sell", 1, T0)


def test_actif_inconnu_refuse(db, seed_data):
    run = new_run(db, seed_data["user"])
    with pytest.raises(rooms.RoomError):
        rooms.trade(run, "NVDA", "buy", 1, T0)


# ---------- jours et prix futurs ----------
def test_pas_de_prix_futurs_dans_la_vue(db, seed_data):
    run = new_run(db, seed_data["user"])
    state = rooms.build_state(run, T0, {})
    assert state["day"] == 1
    for a in state["assets"]:
        assert len(a["history"]) == 1
        assert a["history"][0][0] == state["date"]
    rooms.advance(run, T0)
    state = rooms.build_state(run, T0, {})
    assert state["day"] == 2
    assert all(a["history"][-1][0] <= state["date"] for a in state["assets"])


def test_partie_complete_jusqu_au_dernier_jour(db, seed_data):
    run = new_run(db, seed_data["user"])
    n = len(rooms.load_crisis("covid_2020")["calendar"])
    for _ in range(n - 1):
        rooms.advance(run, T0)
    assert run.status == "active"
    assert rooms.build_state(run, T0, {})["is_last_day"]
    rooms.advance(run, T0)
    assert run.status == "finished"
    assert run.score == 0.0  # jamais investi
    with pytest.raises(rooms.RoomError):
        rooms.advance(run, T0)


def test_gain_reel_sur_covid(db, seed_data):
    """Tout investi dans SPY dès le 3 février 2020 : le score reflète le vrai krach."""
    run = new_run(db, seed_data["user"])
    c = rooms.load_crisis("covid_2020")
    qty = run.cash / rooms.price_at(c, "SPY", 0)
    rooms.trade(run, "SPY", "buy", qty * 0.999999, T0)
    n = len(c["calendar"])
    for _ in range(n):
        rooms.advance(run, T0)
    assert run.status == "finished"
    assert run.max_drawdown_pct > 25   # le S&P 500 a perdu plus de 30 % au plus bas
    assert run.score < run.return_pct  # la perte maximale pénalise le score


# ---------- temps écoulé ----------
def test_temps_ecoule_ferme_la_salle_et_calcule_le_score(db, seed_data):
    run = new_run(db, seed_data["user"])
    c = rooms.load_crisis("covid_2020")
    rooms.trade(run, "SPY", "buy", 100, T0)
    for _ in range(10):
        rooms.advance(run, T0)
    later = T0 + timedelta(seconds=rooms.time_limit_seconds(c) + 1)
    assert rooms.expire_if_needed(run, later)
    assert run.status == "timeout"
    assert run.score is not None
    state = rooms.build_state(run, later, {})
    assert state["result"]["completed"] is False
    assert state["seconds_left"] == 0
    with pytest.raises(rooms.RoomError):
        rooms.trade(run, "SPY", "sell", 1, later)


def test_avant_la_limite_la_salle_reste_ouverte(db, seed_data):
    run = new_run(db, seed_data["user"])
    c = rooms.load_crisis("covid_2020")
    ok = T0 + timedelta(seconds=rooms.time_limit_seconds(c) - 5)
    assert not rooms.expire_if_needed(run, ok)
    assert run.status == "active"
    assert rooms.build_state(run, ok, {})["seconds_left"] == 5
