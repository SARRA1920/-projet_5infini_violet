import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import "./ia.css";

const TABS = [
  { to: "/ia", label: "Tableau de bord", end: true },
  { to: "/ia/prediction", label: "Prédiction de cours" },
  { to: "/ia/sentiment", label: "Analyse de sentiment" },
  { to: "/ia/agent", label: "Agent de trading" },
];

export default function IaLayout() {
  return (
    <section className="page ia-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Intelligence</p>
          <h1>IA &amp; Prédictions</h1>
          <p className="page-lead">
            Prédiction de cours par RandomForest, analyse de sentiment des actualités et agent de
            trading automatisé — entraînés sur l'historique local du simulateur.
          </p>
        </div>
      </div>
      <nav className="ia-tabs" aria-label="Sections du module IA">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => (isActive ? "active" : "")}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>
      <Suspense fallback={<p className="banner">Chargement…</p>}>
        <Outlet />
      </Suspense>
    </section>
  );
}
