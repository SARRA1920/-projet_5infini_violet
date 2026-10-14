import { useEffect, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { getToken } from "../../services/api.js";

const LINKS = [
  { to: "/administration", label: "Vue globale", end: true },
  { to: "/administration/utilisateurs", label: "Utilisateurs" },
  { to: "/administration/marches", label: "Marchés" },
  { to: "/administration/formation", label: "Formation" },
  { to: "/administration/scenarios", label: "Scénarios" },
  { to: "/administration/parametres", label: "Paramètres" },
  { to: "/administration/modeles", label: "Modèles d'IA" },
  { to: "/administration/resultats", label: "Résultats" },
  { to: "/administration/audit", label: "Journal" },
];

export default function AdminLayout() {
  const { user } = useAuth();
  const [allowed, setAllowed] = useState(user?.role === "admin" ? null : false);

  useEffect(() => {
    if (user?.role !== "admin") {
      setAllowed(false);
      return;
    }
    const token = getToken();
    fetch("/admin/session", { headers: token ? { Authorization: `Bearer ${token}` } : {} })
      .then((response) => setAllowed(response.ok))
      .catch(() => setAllowed(false));
  }, [user]);

  if (allowed === null) return <p className="status">Vérification de l'accès…</p>;
  if (!allowed) {
    return (
      <section className="page">
        <article className="panel empty-panel">
          <h1>Administration</h1>
          <p>Cette partie est réservée aux comptes administrateur.</p>
        </article>
      </section>
    );
  }

  return (
    <div className="admin">
      <nav className="admin-nav">
        {LINKS.map((link) => (
          <NavLink key={link.to} to={link.to} end={link.end} className={({ isActive }) => (isActive ? "active" : "")}>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="admin-body">
        <p className="admin-note">Aperçu statique : les boutons modifient l'écran, rien n'est enregistré en base.</p>
        <Outlet />
      </div>
    </div>
  );
}
