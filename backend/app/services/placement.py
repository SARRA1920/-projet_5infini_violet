"""QCM d'entrée de la Formation : questions, notation et niveau.

Les bonnes réponses restent sur le serveur : le client ne reçoit jamais
le champ « answer ». La notation se fait uniquement ici.
"""
import json
from pathlib import Path

QUIZ_PATH = Path(__file__).resolve().parent.parent / "data" / "placement_quiz.json"

# Seuils sur 36 points : 0-12 débutant, 13-25 intermédiaire, 26-36 pro.
MAX_BEGINNER = 12
MAX_INTERMEDIATE = 25


def load_quiz() -> dict:
    with open(QUIZ_PATH, encoding="utf-8") as f:
        return json.load(f)


def public_quiz() -> dict:
    """Glossaire + questions, sans les réponses ni les explications."""
    quiz = load_quiz()
    questions = [
        {"id": q["id"], "points": q["points"], "prompt": q["prompt"], "options": q["options"]}
        for q in quiz["questions"]
    ]
    return {
        "glossary": quiz["glossary"],
        "questions": questions,
        "max_score": sum(q["points"] for q in quiz["questions"]),
    }


def level_for_score(score: int) -> str:
    if score <= MAX_BEGINNER:
        return "debutant"
    if score <= MAX_INTERMEDIATE:
        return "intermediaire"
    return "pro"


def grade(answers: dict[int, int]) -> dict:
    """Note les réponses {id_question: index_choisi}. Question sans réponse = 0 point."""
    quiz = load_quiz()
    score = 0
    correct = 0
    details = []
    for q in quiz["questions"]:
        chosen = answers.get(q["id"])
        ok = chosen == q["answer"]
        if ok:
            score += q["points"]
            correct += 1
        details.append(
            {
                "id": q["id"],
                "correct": ok,
                "chosen": chosen,
                "answer": q["answer"],
                "explanation": q["explanation"],
            }
        )
    return {
        "score": score,
        "max_score": sum(q["points"] for q in quiz["questions"]),
        "correct": correct,
        "total": len(quiz["questions"]),
        "level": level_for_score(score),
        "details": details,
    }
