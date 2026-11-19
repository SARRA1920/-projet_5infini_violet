import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { iaApi } from "../../services/ia.js";

/* Icônes SVG inline (cohérentes avec la sidebar AppShell, pas d'emoji). */
const ICONS = {
  prediction: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 16l5-5 4 3 7-7" />
      <path d="M14 7h6v6" />
    </svg>
  ),
  sentiment: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z" />
    </svg>
  ),
  agent: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="8" width="16" height="12" rx="2" />
      <path d="M12 8V4M9 4h6" />
      <circle cx="9" cy="14" r="1" fill="currentColor" stroke="none" />
      <circle cx="15" cy="14" r="1" fill="currentColor" stroke="none" />
      <path d="M2 14h2M20 14h2" />
    </svg>
  ),
  backtest: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 3v18h18" />
      <rect x="7" y="12" width="3" height="5" fill="currentColor" stroke="none" />
      <rect x="12" y="9" width="3" height="8" fill="currentColor" stroke="none" />
      <rect x="17" y="6" width="3" height="11" fill="currentColor" stroke="none" />
    </svg>
  ),
};

const CARDS = [
  {
    to: "/ia/prediction",
    title: "Prédiction de cours",
    desc: "RandomForest sur 9 features techniques. Rendement prédit à 1-21 jours avec intervalle de confiance issu des quantiles d'arbres.",
    icon: "prediction",
  },
  {
    to: "/ia/sentiment",
    title: "Analyse de sentiment",
    desc: "VADER sur titres d'actualité. Score entre -1 et +1, label positif / neutre / négatif, agrégé par actif.",
    icon: "sentiment",
  },
  {
    to: "/ia/agent",
    title: "Agent de trading",
    desc: "Policy combinant prédiction (50%), technique (30%) et sentiment (20%). Signal BUY / SELL / HOLD avec score de confiance.",
    icon: "agent",
  },
  {
    to: "/ia/backtest",
    title: "Backtest de stratégie",
    desc: "Simule l'agent sur l'historique passé : taux de réussite des signaux, rendement cumulé et rendement prédit vs réel.",
    icon: "backtest",
  },
];

export default function IaDashboard() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    iaApi("/status")
      .then(setStatus)
      .catch((e) => setError(e.message));
  }, []);

  return (
    <div className="ia-dashboard">
      <div className="ia-status">
        <h2>État du module</h2>
        {error && <p className="banner error">Erreur : {error}</p>}
        {status && (
          <ul className="status-list">
            <li>
              <strong>scikit-learn</strong>
              <em className={status.scikit_learn_available ? "ok" : "ko"}>
                {status.scikit_learn_available ? "Disponible" : "Non installé"}
              </em>
            </li>
            <li>
              <strong>VADER (sentiment)</strong>
              <em className={status.vader_available ? "ok" : "ko"}>
                {status.vader_available ? "Disponible" : "Fallback lexique"}
              </em>
            </li>
            <li>
              <strong>Modèles en cache</strong>
              <em>{status.cached_models}</em>
            </li>
            <li>
              <strong>Historique minimum</strong>
              <em>{status.min_history} jours</em>
            </li>
          </ul>
        )}
        {!status && !error && <p className="banner">Chargement de l'état…</p>}
      </div>

      <div className="ia-cards">
        {CARDS.map((card) => (
          <Link key={card.to} to={card.to} className="ia-card">
            <span className="ia-card-icon" aria-hidden="true">
              {ICONS[card.icon]}
            </span>
            <h3>{card.title}</h3>
            <p>{card.desc}</p>
            <span className="ia-card-link">Ouvrir →</span>
          </Link>
        ))}
      </div>

      <div className="ia-note">
        <h3>À propos du module IA</h3>
        <p>
          Ce module répond au cahier des charges : « exploiter l'intelligence
          artificielle pour réaliser des analyses, des prédictions et des
          recommandations ». Les modèles sont entraînés à la demande sur la
          table <code>price_history</code> et mis en cache en mémoire. La page
          Prédiction affiche l'importance des features (quelles variables
          pèsent le plus), et la page Backtest mesure la qualité de la
          stratégie sur l'historique passé. L'explainability avancée (SHAP)
          reste une évolution future.
        </p>
      </div>
    </div>
  );
}
