import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

const NAV = [
  {
    items: [
      { to: "/accueil", label: "Tableau de bord", icon: "grid", end: true },
      { to: "/marches", label: "Marchés", icon: "bars" },
      { to: "/trading", label: "Trading", icon: "swap" },
      { to: "/portefeuille", label: "Portefeuille", icon: "wallet" },
      { to: "/analyse", label: "Analyse", icon: "trend" },
    ],
  },
  {
    section: "Intelligence",
    items: [
      { to: "/ia", label: "IA & Prédictions", icon: "spark", badge: "IA" },
      { to: "/stress-testing", label: "Stress Testing", icon: "pulse" },
      { to: "/actuariat", label: "Actuariat", icon: "calc" },
    ],
  },
  {
    section: "Communauté",
    items: [
      { to: "/formation", label: "Formation", icon: "book" },
      { to: "/classement", label: "Classement", icon: "trophy" },
      { to: "/administration", label: "Administration", icon: "shield" },
    ],
  },
];

function Icon({ name }) {
  const common = {
    viewBox: "0 0 24 24",
    width: 18,
    height: 18,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  if (name === "grid") {
    return (
      <svg {...common}>
        <rect x="3" y="3" width="7" height="7" rx="1.5" />
        <rect x="14" y="3" width="7" height="7" rx="1.5" />
        <rect x="3" y="14" width="7" height="7" rx="1.5" />
        <rect x="14" y="14" width="7" height="7" rx="1.5" />
      </svg>
    );
  }
  if (name === "bars") {
    return (
      <svg {...common}>
        <path d="M4 19V10M10 19V5M16 19v-7M22 19H2" />
      </svg>
    );
  }
  if (name === "swap") {
    return (
      <svg {...common}>
        <path d="M7 7h11l-3-3M17 17H6l3 3" />
      </svg>
    );
  }
  if (name === "wallet") {
    return (
      <svg {...common}>
        <rect x="3" y="6" width="18" height="13" rx="2" />
        <path d="M3 10h18M16 14h2" />
      </svg>
    );
  }
  if (name === "trend") {
    return (
      <svg {...common}>
        <path d="M4 16l5-5 4 3 7-7" />
        <path d="M14 7h6v6" />
      </svg>
    );
  }
  if (name === "spark") {
    return (
      <svg {...common}>
        <path d="M12 3l1.6 4.8L18 9.4l-4.4 1.6L12 16l-1.6-5L6 9.4l4.4-1.6L12 3zM18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14z" />
      </svg>
    );
  }
  if (name === "pulse") {
    return (
      <svg {...common}>
        <path d="M3 12h4l2-5 4 10 2-5h6" />
      </svg>
    );
  }
  if (name === "calc") {
    return (
      <svg {...common}>
        <rect x="5" y="3" width="14" height="18" rx="2" />
        <path d="M8 7h8M8 12h2M12 12h2M16 12h0M8 16h2M12 16h2" />
      </svg>
    );
  }
  if (name === "book") {
    return (
      <svg {...common}>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" />
        <path d="M4 5.5V19" />
      </svg>
    );
  }
  if (name === "trophy") {
    return (
      <svg {...common}>
        <path d="M8 4h8v5a4 4 0 0 1-8 0V4zM8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v3M9 20h6M10 16h4" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z" />
    </svg>
  );
}

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [query, setQuery] = useState(params.get("q") || "");
  const [menu, setMenu] = useState(null);

  useEffect(() => {
    setQuery(params.get("q") || "");
  }, [params]);

  function onSearch(event) {
    const value = event.target.value;
    setQuery(value);
    const next = value.trim() ? `/marches?q=${encodeURIComponent(value.trim())}` : "/marches";
    navigate(next);
  }

  function onLogout() {
    logout();
    navigate("/login");
  }

  const initials = (user?.username || "?").slice(0, 2).toUpperCase();
  const roleLabel = user?.role === "admin" ? "Admin" : "Trader Pro";

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand shell-brand">
          <span className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18">
              <rect x="3" y="10" width="3" height="8" rx="1" fill="currentColor" />
              <rect x="10.5" y="6" width="3" height="12" rx="1" fill="currentColor" />
              <rect x="18" y="3" width="3" height="15" rx="1" fill="currentColor" />
            </svg>
          </span>
          <span className="brand-name">TradeLab</span>
        </div>

        <nav className="side-nav">
          {NAV.map((group) => (
            <div key={group.section || "main"}>
              {group.section && <p className="nav-section">{group.section}</p>}
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  <Icon name={item.icon} />
                  <span>{item.label}</span>
                  {item.badge && <em className="nav-badge">{item.badge}</em>}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="market-status">
          <span className="dot" />
          <div>
            <strong>Marché ouvert</strong>
            <p>Fermeture 17h15</p>
          </div>
        </div>
      </aside>

      <div className="shell-main">
        <header className="topbar">
          <label className="search">
            <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
              <circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="1.8" />
              <path d="M16 16l5 5" stroke="currentColor" strokeWidth="1.8" />
            </svg>
            <input
              value={query}
              onChange={onSearch}
              placeholder="Rechercher un actif, une actualité..."
            />
            {query && (
              <button type="button" className="search-clear" onClick={() => onSearch({ target: { value: "" } })}>
                ×
              </button>
            )}
          </label>

          <div className="top-actions">
            <span className="index-pill">TUNINDEX +0,82 %</span>
            <button
              type="button"
              className="icon-btn"
              aria-label="Notifications"
              onClick={() => setMenu(menu === "bell" ? null : "bell")}
            >
              <svg viewBox="0 0 24 24" width="18" height="18">
                <path d="M6 9a6 6 0 1 1 12 0c0 5 2 6 2 6H4s2-1 2-6z" fill="none" stroke="currentColor" strokeWidth="1.8" />
                <path d="M10 18a2 2 0 0 0 4 0" fill="none" stroke="currentColor" strokeWidth="1.8" />
              </svg>
            </button>
            <button
              type="button"
              className="user-chip"
              onClick={() => setMenu(menu === "user" ? null : "user")}
            >
              <span className="avatar">{initials}</span>
              <span>
                <strong>{user.username}</strong>
                <em>{roleLabel}</em>
              </span>
            </button>
            {menu === "bell" && <p className="pop pop-bell">Aucune notification pour le moment.</p>}
            {menu === "user" && (
              <div className="pop pop-user">
                <p>{user.email}</p>
                <button type="button" onClick={onLogout}>
                  Se déconnecter
                </button>
              </div>
            )}
          </div>
        </header>
        <div className="shell-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}
