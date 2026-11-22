// Fil d'actualités en direct : pop-ups discrets en bas à droite + panneau
// repliable. Récupère /api/ia/news/live toutes les 60 s — le backend met le
// fil agrégé en cache 90 s, donc les rafraîchissements de tous les
// utilisateurs partagent la même agrégation RSS (aucune requête en trop).
// Chaque titre porte un id stable calculé côté backend : les pop-ups déjà
// vus sont mémorisés localement (localStorage) et jamais réaffichés.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { iaApi, SENTIMENT_LABELS, SENTIMENT_TONES } from "../services/ia.js";
import "./newsfeed.css";

const POLL_MS = 60_000;            // intervalle entre deux rafraîchissements
const FIRST_POPUP_DELAY_MS = 8_000; // délai avant le premier pop-up (laisser respirer)
const POPUP_DURATION_MS = 12_000;   // durée d'affichage d'un pop-up
const COOLDOWN_MS = 4_000;          // pause entre deux pop-ups consécutifs
const SEEN_KEY = "tradelab_news_seen_v1";
const SEEN_MAX = 300;               // on ne garde que les 300 derniers ids vus

function loadSeen() {
  try {
    const raw = JSON.parse(localStorage.getItem(SEEN_KEY) || "[]");
    return new Set(Array.isArray(raw) ? raw.filter((v) => typeof v === "string") : []);
  } catch {
    return new Set();
  }
}

function saveSeen(next) {
  const arr = [...next];
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(arr.slice(-SEEN_MAX)));
  } catch {
    /* stockage indisponible (navigation privée) : on ignore, les pop-ups
       réapparaîtront simplement à la prochaine session */
  }
  return next;
}

function ageLabel(iso) {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const mins = Math.round((Date.now() - then) / 60_000);
  if (mins < 2) return "à l'instant";
  if (mins < 60) return `il y a ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `il y a ${days} j`;
  return new Date(iso).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
}

function scoreLabel(item) {
  const label = SENTIMENT_LABELS[item.label] || item.label;
  const sign = item.score >= 0 ? "+" : "";
  return `${label} ${sign}${item.score.toFixed(2)}`;
}

export default function NewsFeed() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [seen, setSeen] = useState(loadSeen);
  const [panelOpen, setPanelOpen] = useState(false);
  const [popup, setPopup] = useState(null);
  const cooldownUntil = useRef(0);

  // Première apparition : on laisse le temps à la page de se poser.
  useEffect(() => {
    cooldownUntil.current = Date.now() + FIRST_POPUP_DELAY_MS;
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await iaApi("/news/live", { limit: 20 });
      setItems(Array.isArray(data.items) ? data.items : []);
    } catch {
      // Fil indisponible (backend coupé, hors connexion) : on garde l'affiché.
    }
  }, []);

  useEffect(() => {
    if (!user) return undefined;
    refresh();
    const interval = setInterval(() => {
      // Onglet en arrière-plan : pas de requête, la prochaine suffit.
      if (!document.hidden) refresh();
    }, POLL_MS);
    return () => clearInterval(interval);
  }, [user, refresh]);

  const unseen = useMemo(
    () => items.filter((item) => !seen.has(item.id)),
    [items, seen],
  );

  const markSeen = useCallback((id) => {
    setSeen((prev) => saveSeen(new Set(prev).add(id)));
  }, []);

  const markAllSeen = useCallback(() => {
    setSeen((prev) => saveSeen(new Set([...prev, ...items.map((i) => i.id)])));
  }, [items]);

  const dismissPopup = useCallback(
    (id) => {
      markSeen(id);
      setPopup(null);
      cooldownUntil.current = Date.now() + COOLDOWN_MS;
    },
    [markSeen],
  );

  // Planification : quand aucun pop-up n'est affiché et que le cooldown est
  // écoulé, la dernière actus non vue glisse dans le coin bas-droit.
  // Panneau ouvert → pas de pop-up (l'utilisateur lit déjà les actus).
  useEffect(() => {
    if (!user || popup || unseen.length === 0) return undefined;
    const show = () => {
      if (panelOpen) {
        cooldownUntil.current = Date.now() + COOLDOWN_MS;
        return;
      }
      setPopup(unseen[0]);
    };
    const timer = setTimeout(show, Math.max(0, cooldownUntil.current - Date.now()));
    return () => clearTimeout(timer);
  }, [user, popup, unseen, panelOpen]);

  // Disparition automatique du pop-up courant.
  useEffect(() => {
    if (!popup) return undefined;
    const timer = setTimeout(() => dismissPopup(popup.id), POPUP_DURATION_MS);
    return () => clearTimeout(timer);
  }, [popup, dismissPopup]);

  const renderItemTitle = (item) =>
    item.link ? (
      <a href={item.link} target="_blank" rel="noreferrer">
        {item.title}
      </a>
    ) : (
      <p>{item.title}</p>
    );

  return (
    <div className="newsfeed">
      {popup && (
        <article
          className={`nf-popup ${SENTIMENT_TONES[popup.label] || ""}`}
          role="status"
        >
          <header className="nf-popup-head">
            <span className="nf-symbols">
              {popup.symbols.length ? popup.symbols.join(" · ") : "Marché"}
            </span>
            <span className="nf-age">{ageLabel(popup.published)}</span>
            <button
              type="button"
              className="nf-close"
              aria-label="Fermer l'actualité"
              onClick={() => dismissPopup(popup.id)}
            >
              ×
            </button>
          </header>
          <div className="nf-popup-title">{renderItemTitle(popup)}</div>
          <footer className="nf-popup-foot">
            <span className={`nf-badge ${SENTIMENT_TONES[popup.label] || ""}`}>
              IA : {scoreLabel(popup)}
            </span>
          </footer>
        </article>
      )}

      {panelOpen && (
        <aside className="nf-panel" aria-label="Actualités en direct">
          <header className="nf-panel-head">
            <strong>Actus en direct</strong>
            <div className="nf-panel-actions">
              {unseen.length > 0 && (
                <button type="button" onClick={markAllSeen}>
                  Tout marquer comme lu
                </button>
              )}
              <button
                type="button"
                className="nf-close"
                aria-label="Fermer le panneau"
                onClick={() => setPanelOpen(false)}
              >
                ×
              </button>
            </div>
          </header>
          <ul className="nf-list">
            {items.length === 0 && (
              <li className="nf-empty">
                Aucune actualité pour l'instant — les sources RSS (Yahoo Finance,
                Google News) seront relancées à la prochaine vérification.
              </li>
            )}
            {items.map((item) => (
              <li key={item.id} className={seen.has(item.id) ? "" : "nf-unseen"}>
                <div className="nf-meta">
                  <span className="nf-symbols">
                    {item.symbols.length ? item.symbols.join(" · ") : "Marché"}
                  </span>
                  <span className="nf-age">{ageLabel(item.published)}</span>
                </div>
                <div className="nf-title">{renderItemTitle(item)}</div>
                <span className={`nf-badge ${SENTIMENT_TONES[item.label] || ""}`}>
                  {scoreLabel(item)}
                </span>
              </li>
            ))}
          </ul>
        </aside>
      )}

      <button
        type="button"
        className="nf-toggle"
        onClick={() => setPanelOpen((open) => !open)}
        aria-expanded={panelOpen}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
          <path
            d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
          />
          <path d="M8 8h8M8 12h8M8 16h5" stroke="currentColor" strokeWidth="1.8" />
        </svg>
        <span>Actus</span>
        {unseen.length > 0 && <em>{unseen.length > 9 ? "9+" : unseen.length}</em>}
      </button>
    </div>
  );
}
