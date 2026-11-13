import { Suspense } from "react";
import { NavLink, Outlet } from "react-router-dom";
import "./actuariat.css";

const TABS = [
  { to: "/actuariat", label: "Tableau de bord", end: true },
  { to: "/actuariat/risque", label: "Risk Analytics" },
  { to: "/actuariat/stochastique", label: "Modèles stochastiques" },
  { to: "/actuariat/obligations", label: "Fixed Income" },
  { to: "/actuariat/optimisation", label: "Optimisation" },
  { to: "/actuariat/pertes", label: "Modèles de pertes" },
  { to: "/actuariat/laboratoire", label: "Laboratoire" },
];

export default function ActuarialLayout() {
  return (
    <section className="page act-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Intelligence / Actuariat</p>
          <h1>Actuarial &amp; Quantitative Risk Analytics</h1>
          <p className="page-lead">
            Mesures de risque, modèles stochastiques, obligations, optimisation et modèles de pertes,
            calculés sur les cours et les portefeuilles du simulateur.
          </p>
        </div>
      </div>
      <nav className="act-tabs" aria-label="Sections du module Actuariat">
        {TABS.map((tab) => (
          <NavLink key={tab.to} to={tab.to} end={tab.end} className={({ isActive }) => (isActive ? "active" : "")}>
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
