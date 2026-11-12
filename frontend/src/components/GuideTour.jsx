import { useCallback, useEffect, useLayoutEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { api } from "../services/api.js";
import "./guide.css";

const INTRO = {
  debutant: "Tu débutes : pas de panique, ce petit tour te montre où tout se trouve.",
  intermediaire: "Tu connais déjà les bases : voici où retrouver chaque outil de la plateforme.",
  pro: "Tu maîtrises les notions clés : voici un tour rapide des outils à ta disposition.",
};

const STEPS = [
  { target: null, title: "Bienvenue sur TradeLab", text: null },
  { target: "search", place: "bottom", title: "Recherche", text: "Trouve un actif (action, devise, obligation) en tapant son nom ou son symbole." },
  { target: "/marches", place: "right", title: "Marchés", text: "Les cours en direct et l'évolution de chaque actif." },
  { target: "/trading", place: "right", title: "Trading", text: "Passe tes ordres d'achat et de vente. Avant de valider, un aperçu te montre le risque de l'ordre." },
  { target: "/portefeuille", place: "right", title: "Portefeuille", text: "Tes positions, tes gains réalisés et tes seuils stop loss / take profit." },
  { target: "/analyse", place: "right", title: "Analyse", text: "Graphiques en chandeliers, indicateurs (moyenne mobile, RSI) et comparaison de stratégies." },
  { target: "/formation", place: "right", title: "Formation", text: "Les salles de marché : rejoue de vraies crises financières dans un temps limité et progresse de niveau." },
  { target: "/classement", place: "right", title: "Classement", text: "Compare tes performances avec celles des autres traders." },
  { target: "user", place: "bottom-left", title: "Ton niveau", text: "Ton badge indique ton niveau actuel. Il évolue avec tes résultats dans les salles de marché." },
  { target: null, title: "C'est parti !", text: "Tu peux rouvrir la Formation à tout moment. Bon trading !" },
];

const PAD = 6;
const TIP_W = 320;

export default function GuideTour() {
  const { user, refreshUser } = useAuth();
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState(null);
  const step = STEPS[index];

  const measure = useCallback(() => {
    if (!step.target) return setRect(null);
    const el = document.querySelector(`[data-tour="${step.target}"]`);
    if (!el) return setRect(null);
    const r = el.getBoundingClientRect();
    setRect({ top: r.top - PAD, left: r.left - PAD, width: r.width + PAD * 2, height: r.height + PAD * 2 });
  }, [step]);

  useLayoutEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  async function finish() {
    try {
      await api("/formation/guide/seen", { method: "POST" });
    } finally {
      await refreshUser();
    }
  }

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "ArrowRight" && index < STEPS.length - 1) setIndex(index + 1);
      if (e.key === "ArrowLeft" && index > 0) setIndex(index - 1);
      if (e.key === "Escape") finish();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // Position de l'étiquette et de sa flèche
  let tipStyle = {};
  let arrow = "none";
  if (rect) {
    const place = step.place;
    if (place === "right") {
      tipStyle = { top: Math.max(12, rect.top + rect.height / 2 - 60), left: rect.left + rect.width + 16 };
      arrow = "left";
    } else if (place === "bottom-left") {
      tipStyle = { top: rect.top + rect.height + 16, left: Math.max(12, rect.left + rect.width - TIP_W) };
      arrow = "top-right";
    } else {
      tipStyle = { top: rect.top + rect.height + 16, left: Math.max(12, Math.min(rect.left, window.innerWidth - TIP_W - 12)) };
      arrow = "top-left";
    }
  }

  const last = index === STEPS.length - 1;
  const text = index === 0 ? INTRO[user?.level] || INTRO.debutant : step.text;

  return (
    <div className="tour">
      <div className="tour-block" />
      {rect ? (
        <div className="tour-spot" style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }} />
      ) : (
        <div className="tour-dim" />
      )}
      <div className={`tour-tip arrow-${arrow}${rect ? "" : " centered"}`} style={rect ? tipStyle : undefined} role="dialog">
        <p className="tour-count">
          {index + 1} / {STEPS.length}
        </p>
        <h3>{step.title}</h3>
        <p>{text}</p>
        <div className="tour-actions">
          <button className="tour-skip" onClick={finish}>
            Passer
          </button>
          <span>
            {index > 0 && (
              <button className="tour-btn" onClick={() => setIndex(index - 1)}>
                Précédent
              </button>
            )}
            <button className="tour-btn primary" onClick={() => (last ? finish() : setIndex(index + 1))}>
              {last ? "Terminer" : index === 0 ? "Commencer le tour" : "Suivant"}
            </button>
          </span>
        </div>
      </div>
    </div>
  );
}
