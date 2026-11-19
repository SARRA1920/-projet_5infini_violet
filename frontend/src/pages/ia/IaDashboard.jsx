import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { iaApi } from "../../services/ia.js";

export default function IaDashboard() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    iaApi("/status")
      .then(setStatus)
      .catch((e) => setError(e.message));
  }, []);

  const cards = [
    {
      to: "/ia/prediction",
      title: "Prédiction de cours",
      desc: "RandomForest sur features techniques : rendement prédit à 1-21 jours avec intervalle de confiance.",
      icon: "📈",
    },
    {
      to: "/ia/sentiment",
      title: "Analyse de sentiment",
      desc: "VADER sur titres d'actualité : score -1 à +1, label positif/neutre/négatif par actif.",
      icon: "📰",
    },
    {
      to: "/ia/agent",
      title: "Agent de trading",
      desc: "Policy rule-based combinant prédiction, technique et sentiment : signal BUY/SELL/HOLD + confiance.",
      icon: "🤖",
    },
  ];

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
              <strong>Historique minimum requis</strong>
              <em>{status.min_history} jours</em>
            </li>
          </ul>
        )}
        {!status && !error && <p className="banner">Chargement de l'état…</p>}
      </div>

      <div className="ia-cards">
        {cards.map((card) => (
          <Link key={card.to} to={card.to} className="ia-card">
            <span className="ia-card-icon" aria-hidden="true">
              {card.icon}
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
          Ce module répond au cahier des charges : « exploiter l'intelligence artificielle pour
          réaliser des analyses, des prédictions et des recommandations ». Les modèles sont
          entraînés à la demande sur la table <code>price_history</code> et mis en cache en
          mémoire. L'explainability (XAI/SHAP) est prévue comme évolution pour rendre les
          prédictions interprétables.
        </p>
      </div>
    </div>
  );
}
