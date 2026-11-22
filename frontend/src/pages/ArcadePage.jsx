import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api.js";
import "./arcade.css";

const TYPES = [
  {
    key: "event",
    code: "TYPE_01",
    status: "LIVE",
    title: "Crise surprise",
    text: "Rejoue une vraie crise financière tunisienne ou mondiale. À chaque partie, une crise différente est tirée au hasard dans nos données réelles.",
    cta: "Jouer",
    ready: true,
  },
  {
    key: "strategy",
    code: "TYPE_02",
    status: "LIVE",
    title: "Test de stratégie",
    text: "Choisis une stratégie de trading (day trading, position, swing, trend, scalping) et applique-la sur une vraie action BVMT.",
    cta: "Choisir une stratégie",
    ready: true,
  },
  {
    key: "ai",
    code: "TYPE_03",
    status: "SOON",
    title: "Avec intelligence artificielle",
    text: "Un modèle d'IA interviendra pendant la partie.",
    cta: "À venir",
    ready: false,
  },
  {
    key: "live",
    code: "TYPE_04",
    status: "SOON",
    title: "Même salle en temps réel",
    text: "Plusieurs joueurs dans la même salle, en même temps.",
    cta: "À venir",
    ready: false,
  },
];

export default function ArcadePage() {
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function playEvent() {
    setBusy(true);
    setError("");
    try {
      const state = await api("/salles-de-jeu/events/start", { method: "POST" });
      navigate(`/salles-de-jeu/evenement/${state.run_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  function onPlay(type) {
    if (!type.ready) return;
    if (type.key === "event") playEvent();
    if (type.key === "strategy") navigate("/salles-de-jeu/strategie");
  }

  return (
    <section className="page ag">
      <div className="ag-header">
        <p className="ag-prompt">Entraînement libre</p>
        <h1>Salles de jeu</h1>
        <p className="page-lead">
          Quatre façons de s'entraîner, en dehors du parcours de Formation : crises surprises,
          stratégies de trading, assistance par IA et sessions en temps réel.
        </p>
      </div>
      {error && <p className="status error">{error}</p>}

      <div className="ag-grid">
        {TYPES.map((t) => (
          <article key={t.key} className={`ag-card${t.ready ? "" : " dim"}`}>
            <div className="ag-card-bar">
              <span className="ag-card-code">{t.code}</span>
              <span className="ag-suit">{t.status}</span>
            </div>
            <div className="ag-card-body">
              <h3>{t.title}</h3>
              <p>{t.text}</p>
            </div>
            <div className="ag-card-foot">
              {!t.ready && <span className="ag-soon">en préparation</span>}
              <button className="ag-btn" disabled={!t.ready || busy} onClick={() => onPlay(t)}>
                {t.ready ? "▶" : "—"} {t.cta}
              </button>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
