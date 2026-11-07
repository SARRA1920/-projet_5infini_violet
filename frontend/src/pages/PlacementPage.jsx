import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { api } from "../services/api.js";
import "./formation.css";

const LEVELS = {
  debutant: {
    label: "Débutant",
    color: "#38bdf8",
    text: "Tu découvres les marchés. Les premières salles de crise te guideront pas à pas, avec des situations accessibles.",
  },
  intermediaire: {
    label: "Intermédiaire",
    color: "#a78bfa",
    text: "Tu connais les bases. Tu peux aborder des salles plus exigeantes, où la gestion du risque compte.",
  },
  pro: {
    label: "Pro",
    color: "#f59e0b",
    text: "Tu maîtrises les notions clés. Tu accèdes d'emblée aux salles les plus difficiles.",
  },
};
const LEVEL_ORDER = ["debutant", "intermediaire", "pro"];
const DIFFICULTY = { 1: "Facile", 2: "Moyen", 3: "Difficile" };
const LETTERS = ["A", "B", "C", "D"];
const CIRC = 2 * Math.PI * 54;

function Gauge({ score, max, color }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setShown(score / max), 80);
    return () => clearTimeout(t);
  }, [score, max]);
  return (
    <div className="pl-gauge">
      <svg viewBox="0 0 120 120">
        <circle cx="60" cy="60" r="54" className="pl-gauge-bg" />
        <circle
          cx="60"
          cy="60"
          r="54"
          className="pl-gauge-fg"
          style={{ stroke: color, strokeDasharray: CIRC, strokeDashoffset: CIRC * (1 - shown) }}
        />
      </svg>
      <div className="pl-gauge-text">
        <strong>{score}</strong>
        <span>/ {max}</span>
      </div>
    </div>
  );
}

export default function PlacementPage() {
  const { refreshUser, logout } = useAuth();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState(null);
  const [step, setStep] = useState("intro"); // intro -> glossary -> quiz -> result
  const [index, setIndex] = useState(0);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/formation/placement")
      .then((data) => {
        if (data.already_done) navigate("/formation", { replace: true });
        else setQuiz(data);
      })
      .catch((err) => setError(err.message));
  }, [navigate]);

  // Raccourcis clavier : 1-4 pour répondre, flèches pour naviguer
  useEffect(() => {
    if (step !== "quiz" || !quiz) return undefined;
    const q = quiz.questions[index];
    const onKey = (e) => {
      const n = Number(e.key);
      if (n >= 1 && n <= q.options.length) setAnswers((a) => ({ ...a, [q.id]: n - 1 }));
      if (e.key === "ArrowRight" && index < quiz.questions.length - 1) setIndex(index + 1);
      if (e.key === "ArrowLeft" && index > 0) setIndex(index - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, index, quiz]);

  async function submit() {
    setBusy(true);
    setError("");
    try {
      const res = await api("/formation/placement", {
        method: "POST",
        body: JSON.stringify({ answers }),
      });
      setResult(res);
      setStep("result");
      await refreshUser();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !quiz) return <p className="status error">{error}</p>;
  if (!quiz) return <p className="status">Chargement…</p>;

  const questions = quiz.questions;
  const q = questions[index];
  const isLast = index === questions.length - 1;
  const answered = Object.keys(answers).length;

  return (
    <div className="pl-screen">
    <div className="pl">
      <header className="pl-header">
        <span className="pl-brand">TradeLab</span>
        <span className="pl-crumb">Formation · Test de niveau</span>
        <button className="pl-logout" onClick={() => { logout(); navigate("/login", { replace: true }); }}>
          Se déconnecter
        </button>
      </header>

      {step === "intro" && (
        <section className="pl-hero">
          <span className="pl-pill">Étape 1 sur 1 · obligatoire</span>
          <h1>Découvrons ton niveau</h1>
          <p>
            Avant d'entrer dans les salles de marché, un court test permet de te placer dans la bonne
            difficulté. Pas de stress : il sert à adapter ta formation, pas à te noter.
          </p>
          <ul className="pl-facts">
            <li>
              <strong>{questions.length}</strong>
              <span>questions</span>
            </li>
            <li>
              <strong>≈ 5</strong>
              <span>minutes</span>
            </li>
            <li>
              <strong>1</strong>
              <span>seule tentative</span>
            </li>
          </ul>
          <p className="pl-note">
            Ton niveau évoluera ensuite avec tes résultats dans les salles de marché.
          </p>
          <button className="pl-btn primary big" onClick={() => setStep("glossary")}>
            C'est parti
          </button>
        </section>
      )}

      {step === "glossary" && (
        <section className="pl-panel">
          <h1>Les mots à connaître</h1>
          <p className="pl-sub">
            Parcours ces {quiz.glossary.length} définitions : elles reviennent dans le test.
          </p>
          <div className="pl-glossary">
            {quiz.glossary.map((g, i) => (
              <article key={g.term} className="pl-term">
                <span className="pl-term-num">{String(i + 1).padStart(2, "0")}</span>
                <h3>{g.term}</h3>
                <p>{g.definition}</p>
              </article>
            ))}
          </div>
          <div className="pl-actions end">
            <button className="pl-btn primary big" onClick={() => setStep("quiz")}>
              Commencer le test
            </button>
          </div>
        </section>
      )}

      {step === "quiz" && (
        <section className="pl-panel">
          <div className="pl-top">
            <span>
              Question <strong>{index + 1}</strong> / {questions.length}
            </span>
            <span className={`pl-diff d${q.points}`}>
              {DIFFICULTY[q.points]} · {q.points} pt{q.points > 1 ? "s" : ""}
            </span>
          </div>
          <div className="pl-steps">
            {questions.map((x, i) => (
              <button
                key={x.id}
                aria-label={`Question ${i + 1}`}
                className={`pl-dot${i === index ? " current" : ""}${answers[x.id] !== undefined ? " done" : ""}`}
                onClick={() => setIndex(i)}
              />
            ))}
          </div>

          <div key={q.id} className="pl-question">
            <h2>{q.prompt}</h2>
            <div className="pl-options">
              {q.options.map((opt, i) => (
                <button
                  key={i}
                  className={`pl-option${answers[q.id] === i ? " selected" : ""}`}
                  onClick={() => setAnswers({ ...answers, [q.id]: i })}
                >
                  <span className="pl-letter">{LETTERS[i]}</span>
                  <span>{opt}</span>
                </button>
              ))}
            </div>
          </div>

          {error && <p className="status error">{error}</p>}
          <div className="pl-actions">
            <button className="pl-btn" onClick={() => setIndex(index - 1)} disabled={index === 0}>
              ← Précédent
            </button>
            <span className="pl-hint">Astuce : touches 1 à 4 et flèches</span>
            {isLast ? (
              <button className="pl-btn primary" onClick={submit} disabled={busy}>
                {busy ? "Calcul…" : `Terminer (${answered}/${questions.length})`}
              </button>
            ) : (
              <button className="pl-btn primary" onClick={() => setIndex(index + 1)}>
                Suivant →
              </button>
            )}
          </div>
        </section>
      )}

      {step === "result" && result && (
        <section className="pl-panel">
          <div className="pl-result">
            <Gauge score={result.score} max={result.max_score} color={LEVELS[result.level].color} />
            <div>
              <span className="pl-pill" style={{ background: LEVELS[result.level].color, color: "#0b1220" }}>
                Niveau {LEVELS[result.level].label}
              </span>
              <h1>
                {result.correct} bonnes réponses sur {result.total}
              </h1>
              <p className="pl-sub">{LEVELS[result.level].text}</p>
            </div>
          </div>

          <div className="pl-scale">
            {LEVEL_ORDER.map((key) => (
              <div
                key={key}
                className={`pl-scale-item${key === result.level ? " active" : ""}`}
                style={key === result.level ? { borderColor: LEVELS[key].color } : undefined}
              >
                <strong>{LEVELS[key].label}</strong>
                <span>{key === "debutant" ? "0 – 12" : key === "intermediaire" ? "13 – 25" : "26 – 36"}</span>
              </div>
            ))}
          </div>

          <details className="pl-review">
            <summary>Voir la correction détaillée</summary>
            <ol>
              {questions.map((qq, i) => {
                const d = result.details[i];
                return (
                  <li key={qq.id} className={d.correct ? "ok" : "ko"}>
                    <strong>{qq.prompt}</strong>
                    <p>
                      {d.correct ? "✓ Correct" : "✗ Bonne réponse"} : {qq.options[d.answer]}
                    </p>
                    <p className="pl-expl">{d.explanation}</p>
                  </li>
                );
              })}
            </ol>
          </details>

          <div className="pl-actions end">
            <button className="pl-btn primary big" onClick={() => navigate("/formation", { replace: true })}>
              Entrer dans la formation
            </button>
          </div>
        </section>
      )}
    </div>
    </div>
  );
}
