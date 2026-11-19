import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { filters, quotes as maquetteQuotes } from "../data/maquette.js";

function Sparkline({ points, up, id }) {
  const line = points.map((y, index) => `${index ? "L" : "M"}${index * 16},${y}`).join(" ");
  const area = `${line} L${(points.length - 1) * 16},28 L0,28 Z`;
  const color = up ? "#3dd68c" : "#ff5d73";
  const gradientId = `spark-fill-${String(id).replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg className="spark" viewBox="0 0 96 28" width="96" height="28" aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gradientId})`} stroke="none" />
      <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// Ordre d'affichage : actions, puis devises, puis matières premières ; ensuite par symbole.
const GROUP_ORDER = { actions: 0, devises: 1, matieres: 2 };

function compareRows(a, b) {
  return (
    (GROUP_ORDER[a.group] ?? 9) - (GROUP_ORDER[b.group] ?? 9) ||
    a.symbol.localeCompare(b.symbol)
  );
}

export default function MarketsPage() {
  const [params] = useSearchParams();
  const [group, setGroup] = useState("tous");
  const [notice, setNotice] = useState("");
  const [quotes, setQuotes] = useState(maquetteQuotes);
  const [live, setLive] = useState(false);
  const query = (params.get("q") || "").trim().toLowerCase();

  useEffect(() => {
    fetch("/quotes")
      .then((response) => {
        if (!response.ok) throw new Error("cours indisponibles");
        return response.json();
      })
      .then((rows) => {
        const bySymbol = new Map(rows.map((row) => [row.symbol, row]));
        const maquetteSymbols = new Set(maquetteQuotes.map((row) => row.symbol));
        // Les lignes de la maquette gardent leur place (remplacées par le vrai cours
        // quand il existe), puis on ajoute tous les autres actifs de la base.
        const merged = maquetteQuotes.map((row) => bySymbol.get(row.symbol) || row);
        const others = rows.filter((row) => !maquetteSymbols.has(row.symbol));
        setQuotes([...merged, ...others]);
        setLive(rows.length > 0);
      })
      .catch(() => setLive(false));
  }, []);

  const rows = useMemo(
    () =>
      quotes
        .filter((row) => {
          const matchesGroup = group === "tous" || row.group === group;
          const matchesQuery =
            !query ||
            row.symbol.toLowerCase().includes(query) ||
            row.name.toLowerCase().includes(query);
          return matchesGroup && matchesQuery;
        })
        .sort(compareRows),
    [quotes, group, query],
  );

  const cards = quotes.filter((row) => ["SFBT", "BIAT", "AAPL", "TSLA"].includes(row.symbol));

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Marchés</p>
          <h1>Marchés</h1>
          <p className="page-lead">
            {live
              ? "Cours importés par Twelve Data. Les titres absents de cet import restent la maquette."
              : "Cours de la maquette : l'historique Twelve Data n'est pas encore importé."}
          </p>
        </div>
        <button type="button" className="primary-btn" onClick={() => setNotice("Les alertes seront branchées avec les données de marché.")}>
          Créer une alerte
        </button>
      </div>
      {notice && <p className="banner">{notice}</p>}

      <div className="ticker-grid">
        {cards.map((row) => (
          <article key={row.symbol} className="ticker-card">
            <p>{row.symbol}</p>
            <strong>{row.last}</strong>
            <em className={row.up ? "up" : "down"}>{row.change}</em>
          </article>
        ))}
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Cotations en direct</h2>
            <p>{live ? "Dernier cours enregistré dans l'historique Twelve Data." : "Chiffres de la maquette."}</p>
          </div>
          <div className="ranges">
            {filters.map((item) => (
              <button
                key={item.id}
                type="button"
                className={item.id === group ? "range active" : "range"}
                onClick={() => setGroup(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>Instrument</th>
              <th>Dernier</th>
              <th>Variation</th>
              <th>Plus haut</th>
              <th>Plus bas</th>
              <th>Volume</th>
              <th>Tendance</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan="7">Aucun actif ne correspond à cette recherche.</td>
              </tr>
            )}
            {rows.map((row) => (
              <tr key={row.symbol}>
                <td>
                  <strong>{row.name}</strong>
                  <span>{row.symbol}</span>
                </td>
                <td>{row.last}</td>
                <td>
                  <span className={`change-pill ${row.up ? "up" : "down"}`}>{row.change}</span>
                </td>
                <td>{row.high}</td>
                <td>{row.low}</td>
                <td>{row.volume}</td>
                <td>
                  <Sparkline points={row.spark} up={row.up} id={row.symbol} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </section>
  );
}
