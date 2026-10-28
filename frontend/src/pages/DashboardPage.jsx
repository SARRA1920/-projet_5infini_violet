import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { api } from "../services/api.js";
import { formatDecimal, formatSigned, signClass } from "../services/format.js";
import { performance } from "../data/maquette.js";

function linePath(values) {
  const width = 640;
  const height = 180;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const points = values.map((value, index) => {
    const x = (index / (values.length - 1)) * width;
    const y = height - 16 - ((value - min) / (max - min || 1)) * (height - 36);
    return [x, y];
  });
  const line = points.map(([x, y], index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
  const area = `${line} L${width},${height} L0,${height} Z`;
  return { line, area };
}

const GROUPS = [
  { id: "actions", label: "Actions", color: "#3dd68c" },
  { id: "obligations", label: "Obligations", color: "#3b82f6" },
  { id: "devises", label: "Devises", color: "#a78bfa" },
  { id: "matieres", label: "Matières premières", color: "#fb923c" },
  { id: "cash", label: "Liquidités", color: "#64748b" },
];

// Valeur totale lisible dans le beignet : 100139.78 -> "100,1K".
function compact(value) {
  const n = Number(value);
  return n >= 1000 ? `${(n / 1000).toFixed(1).replace(".", ",")}K` : n.toFixed(0);
}

// Répartition réelle : valeur de chaque catégorie / valeur totale, en %.
function buildAllocation(portfolio, quotes) {
  if (!portfolio || Number(portfolio.total_value) <= 0) return [];
  const total = Number(portfolio.total_value);
  const groupOf = Object.fromEntries(quotes.map((row) => [row.symbol, row.group]));
  const sums = { cash: Number(portfolio.cash) };
  for (const position of portfolio.positions) {
    const group = groupOf[position.symbol] || "actions";
    sums[group] = (sums[group] || 0) + Number(position.market_value || 0);
  }
  return GROUPS.map((group) => ({
    label: group.label,
    color: group.color,
    value: ((sums[group.id] || 0) / total) * 100,
  })).filter((slice) => slice.value > 0);
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [range, setRange] = useState("1M");
  const [risk, setRisk] = useState(null);
  const [portfolio, setPortfolio] = useState(null);
  const [quotes, setQuotes] = useState([]);

  // Chiffres réels du portefeuille ; en cas d'échec, les cartes affichent « — ».
  useEffect(() => {
    api("/trading/risk")
      .then(setRisk)
      .catch(() => setRisk(null));
    api("/trading/portfolio")
      .then(setPortfolio)
      .catch(() => setPortfolio(null));
    api("/quotes")
      .then(setQuotes)
      .catch(() => setQuotes([]));
  }, []);

  const allocation = buildAllocation(portfolio, quotes);
  // Les 5 plus grosses positions (par valeur de marché).
  const topPositions = [...(portfolio?.positions || [])]
    .sort((a, b) => Number(b.market_value || 0) - Number(a.market_value || 0))
    .slice(0, 5);
  const series = performance[range];
  const chart = linePath(series.values);
  const dateLabel = new Intl.DateTimeFormat("fr-FR", {
    weekday: "long",
    day: "numeric",
    month: "long",
  })
    .format(new Date())
    .toUpperCase();

  const gradient = allocation
    .reduce(
      (acc, slice) => {
        const end = acc.cursor + slice.value;
        acc.parts.push(`${slice.color} ${acc.cursor}% ${end}%`);
        acc.cursor = end;
        return acc;
      },
      { cursor: 0, parts: [] },
    )
    .parts.join(", ");

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">{dateLabel}</p>
          <h1>Bonjour {user.username}, prêt à trader ?</h1>
          <p className="page-lead">Voici un aperçu de vos performances et des marchés aujourd'hui.</p>
        </div>
        <Link className="primary-btn" to="/trading">
          Passer un ordre
        </Link>
      </div>

      <div className="stat-grid">
        <article className="stat-card">
          <p>Valeur du portefeuille</p>
          <strong>{risk ? formatDecimal(risk.total_value) : "—"}</strong>
          <em>Capital de départ : {risk ? formatDecimal(risk.initial_capital) : "—"}</em>
        </article>
        <article className="stat-card">
          <p>Rendement total</p>
          <strong className={risk ? signClass(risk.total_return_pct) : ""}>
            {risk ? `${formatSigned(risk.total_return_pct)} %` : "—"}
          </strong>
          <em>Depuis le début</em>
        </article>
        <article className="stat-card">
          <p>Gain réalisé</p>
          <strong className={risk ? signClass(risk.realized_pnl_total) : ""}>
            {risk ? formatSigned(risk.realized_pnl_total) : "—"}
          </strong>
          <em>Sur les ventes déjà effectuées</em>
        </article>
        <article className="stat-card">
          <p>Risque (VaR 95 %, 1 jour)</p>
          <strong>{risk?.var_95_amount ? formatDecimal(risk.var_95_amount) : "—"}</strong>
          <em>{risk?.var_95_pct ? `${formatDecimal(risk.var_95_pct)} % du portefeuille` : "Historique insuffisant"}</em>
        </article>
      </div>

      <div className="dash-grid">
        <article className="panel">
          <div className="panel-head">
            <div>
              <h2>Performance du portefeuille</h2>
              <p>Évolution de la valeur totale</p>
            </div>
            <div className="ranges">
              {Object.keys(performance).map((key) => (
                <button
                  key={key}
                  type="button"
                  className={key === range ? "range active" : "range"}
                  onClick={() => setRange(key)}
                >
                  {key}
                </button>
              ))}
            </div>
          </div>
          <p className="perf-line">
            <span className="up">{series.label}</span>
            <span>vs +3,15 % Tunindex</span>
          </p>
          <svg className="perf-chart" viewBox="0 0 640 180" role="img" aria-label="Courbe de performance">
            <defs>
              <linearGradient id="perfFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.35" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0" />
              </linearGradient>
            </defs>
            <path d={chart.area} fill="url(#perfFill)" />
            <path d={chart.line} fill="none" stroke="#5aa6ff" strokeWidth="3" />
          </svg>
        </article>

        <article className="panel">
          <div className="panel-head">
            <div>
              <h2>Allocation des actifs</h2>
              <p>Répartition actuelle</p>
            </div>
          </div>
          <div className="alloc">
            <div className="donut" style={{ background: `conic-gradient(${gradient})` }}>
              <div>
                <strong>{portfolio ? compact(portfolio.total_value) : "—"}</strong>
                <span>Total</span>
              </div>
            </div>
            {allocation.length === 0 && <p>Répartition indisponible.</p>}
            <ul>
              {allocation.map((slice) => (
                <li key={slice.label}>
                  <i style={{ background: slice.color }} />
                  {slice.label}
                  <b>{formatDecimal(slice.value.toFixed(1), 1)} %</b>
                </li>
              ))}
            </ul>
          </div>
        </article>
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Positions principales</h2>
            <p>Vos plus grosses positions ouvertes</p>
          </div>
          <Link to="/portefeuille">Voir tout</Link>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Quantité</th>
              <th>Dernier</th>
              <th>Variation</th>
            </tr>
          </thead>
          <tbody>
            {topPositions.length === 0 && (
              <tr>
                <td colSpan="4">Aucune position ouverte.</td>
              </tr>
            )}
            {topPositions.map((row) => (
              <tr key={row.symbol}>
                <td>
                  <strong>{row.symbol}</strong>
                  <span>{row.name}</span>
                </td>
                <td>{formatDecimal(row.quantity, 0)}</td>
                <td>{formatDecimal(row.current_price)}</td>
                <td className={signClass(row.unrealized_pnl_pct)}>
                  {row.unrealized_pnl_pct === null || row.unrealized_pnl_pct === undefined
                    ? "—"
                    : `${formatSigned(row.unrealized_pnl_pct)} %`}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
