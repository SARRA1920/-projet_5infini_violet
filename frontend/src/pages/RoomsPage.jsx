import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api.js";
import "./rooms.css";

const LEVEL = {
  debutant: { label: "Débutant", color: "#38bdf8" },
  intermediaire: { label: "Intermédiaire", color: "#a78bfa" },
  pro: { label: "Pro", color: "#f59e0b" },
};
const ORDER = ["debutant", "intermediaire", "pro"];

const minutes = (s) => `${Math.round(s / 60)} min`;
const frDate = (iso) => new Date(iso).toLocaleDateString("fr-FR", { month: "short", year: "numeric" });

export default function RoomsPage() {
  const navigate = useNavigate();
  const [rooms, setRooms] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    api("/formation/rooms")
      .then(setRooms)
      .catch((err) => setError(err.message));
  }, []);

  async function enter(room) {
    setBusy(room.key);
    setError("");
    try {
      const state = await api(`/formation/rooms/${room.key}/start`, { method: "POST" });
      navigate(`/formation/salle/${state.run_id}`);
    } catch (err) {
      setError(err.message);
      setBusy("");
    }
  }

  if (error && !rooms) return <p className="status error">{error}</p>;
  if (!rooms) return <p className="status">Chargement…</p>;

  return (
    <section className="page rm">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Communauté</p>
          <h1>Formation : salles de marché</h1>
          <p className="page-lead">
            Rejoue de vraies crises financières, jour après jour, avec un portefeuille virtuel de 100 000 $
            et un temps limité. Les salles plus difficiles se débloquent avec ton niveau.
          </p>
        </div>
      </div>
      {error && <p className="status error">{error}</p>}

      {ORDER.map((level) => {
        const group = rooms.filter((r) => r.level === level);
        if (!group.length) return null;
        return (
          <div key={level} className="rm-group">
            <h2>
              <span className="rm-dot" style={{ background: LEVEL[level].color }} />
              Niveau {LEVEL[level].label}
            </h2>
            <div className="rm-grid">
              {group.map((room) => (
                <article key={room.key} className={`rm-card${room.locked ? " locked" : ""}`}>
                  <div className="rm-card-top">
                    <h3>{room.name}</h3>
                    {room.locked && <span className="rm-lock">🔒 Verrouillée</span>}
                  </div>
                  <p className="rm-story">{room.story}</p>
                  <ul className="rm-meta">
                    <li>
                      <strong>{frDate(room.start)} → {frDate(room.end)}</strong>
                      <span>période rejouée</span>
                    </li>
                    <li>
                      <strong>{room.total_days} jours</strong>
                      <span>de bourse</span>
                    </li>
                    <li>
                      <strong>{minutes(room.time_limit_seconds)}</strong>
                      <span>chronomètre</span>
                    </li>
                  </ul>
                  <div className="rm-card-foot">
                    <span className="rm-best">
                      {room.best_score === null
                        ? "Jamais jouée"
                        : `Meilleur score : ${room.best_score} pts · ${room.attempts} essai${room.attempts > 1 ? "s" : ""}`}
                    </span>
                    <button
                      className="rm-btn"
                      disabled={room.locked || busy === room.key}
                      onClick={() => enter(room)}
                    >
                      {room.active_run_id ? "Reprendre" : "Entrer"}
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </div>
        );
      })}
    </section>
  );
}
