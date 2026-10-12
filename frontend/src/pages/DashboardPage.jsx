import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { allocation, performance, positions } from "../data/maquette.js";

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

export default function DashboardPage() {
  const { user } = useAuth();
  const [range, setRange] = useState("1M");
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
          <strong>124 850,40 TND</strong>
          <em className="up">+2,38 % aujourd'hui</em>
        </article>
        <article className="stat-card">
          <p>PNL du jour</p>
          <strong className="up">+1 842,60 TND</strong>
          <em className="up">+1,49 % aujourd'hui</em>
        </article>
        <article className="stat-card">
          <p>Risque (VaR 95 %)</p>
          <strong>3 245,20 TND</strong>
          <em className="down">-0,18 % aujourd'hui</em>
        </article>
        <article className="stat-card">
          <p>Score de performance</p>
          <strong>82 / 100</strong>
          <em className="up">+4 pts aujourd'hui</em>
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
                <strong>124,8K</strong>
                <span>TND</span>
              </div>
            </div>
            <ul>
              {allocation.map((slice) => (
                <li key={slice.label}>
                  <i style={{ background: slice.color }} />
                  {slice.label}
                  <b>{slice.value} %</b>
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
            <p>Aperçu de la maquette</p>
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
            {positions.map((row) => (
              <tr key={row.symbol}>
                <td>
                  <strong>{row.symbol}</strong>
                  <span>{row.name}</span>
                </td>
                <td>{row.qty}</td>
                <td>{row.price}</td>
                <td className={row.up ? "up" : "down"}>{row.pnl}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
