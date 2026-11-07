import pytest

from app.services import placement


def all_correct():
    return {q["id"]: q["answer"] for q in placement.load_quiz()["questions"]}


def test_structure_du_qcm():
    quiz = placement.load_quiz()
    assert len(quiz["questions"]) == 20
    assert sum(q["points"] for q in quiz["questions"]) == 36
    assert len(quiz["glossary"]) == 10


def test_le_client_ne_recoit_pas_les_reponses():
    pub = placement.public_quiz()
    assert pub["max_score"] == 36
    for q in pub["questions"]:
        assert "answer" not in q and "explanation" not in q


def test_tout_juste_donne_36_et_pro():
    r = placement.grade(all_correct())
    assert r["score"] == 36 and r["level"] == "pro"


def test_aucune_reponse_donne_0_et_debutant():
    r = placement.grade({})
    assert r["score"] == 0 and r["level"] == "debutant"


@pytest.mark.parametrize(
    "score,level",
    [(0, "debutant"), (12, "debutant"), (13, "intermediaire"), (25, "intermediaire"), (26, "pro"), (36, "pro")],
)
def test_seuils(score, level):
    assert placement.level_for_score(score) == level


def test_notation_partielle():
    # seules les 8 questions faciles (1 pt) justes -> 8 points
    quiz = placement.load_quiz()
    answers = {q["id"]: q["answer"] for q in quiz["questions"] if q["points"] == 1}
    r = placement.grade(answers)
    assert r["score"] == 8 and r["correct"] == 8 and r["level"] == "debutant"
