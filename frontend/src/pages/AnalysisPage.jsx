import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import { formatDecimal } from "../services/format.js";
import "./trading.css";
import "./analysis.css";

const PERIODS = { "3M": 63, "6M": 126, "1A": 260 };
const W = 760;
const H = 260;
const RSI_H = 110;
const PAD = 8;

// Trace une série en sautant les valeurs absentes (début des moyennes mobiles).
function path(values, toY) {
  let d = "";
  let pen = false;
  values.forEach((value, index) => {
    if (value === null || value === undefined) {
      pen = false;
      return;
    }
    const x = (index / Math.max(values.length - 1, 1)) * W;
    d += `${pen ? "L" : "M"}${x.toFixed(1)},${toY(value).toFixed(1)} `;
    pen = true;
  });
  return d;
}

const last = (values) => values[values.length - 1];

export default function AnalysisPage() {
  const [quotes, setQuotes] = useState([]);
  const [symbol, setSymbol] = useState("");
  const [period, setPeriod] = useState("6M");
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/quotes")
      .then((rows) => {
        setQuotes(rows);
        if (rows.length) setSymbol((rows.find((r) => r.symbol === "AAPL") || rows[0]).symbol);
      })
      .catch((err) => setError(`Cours indisponibles : ${err.message}`));
  }, []);

  useEffect(() => {
    if (!symbol) return;
    setError("");
    api(`/analysis/${encodeURIComponent(symbol)}?days=${PERIODS[period]}`)
      .then((result) => {
        if (!Array.isArray(result?.close)) throw new Error("Réponse inattendue du serveur");
        setData(result);
      })
      .catch((err) => {
        setData(null);
        setError(err.message);
      });
  }, [symbol, period]);

  let content = null;
  if (data) {
    const all = [...data.close, ...data.sma_short, ...data.sma_long].filter((v) => v !== null);
    const min = Math.min(...all);
    const max = Math.max(...all);
    const toY = (v) => PAD + (1 - (v - min) / (max - min || 1)) * (H - 2 * PAD);
    const toRsiY = (v) => PAD + (1 - v / 100) * (RSI_H - 2 * PAD);
    const lastRsi = last(data.rsi);
    const lastClose = last(data.close);
    const short = last(data.sma_short);
    const long = last(data.sma_long);
    const trend =
      short === null || long === null ? "—" : short > long ? "Haussière" : "Baissière";
    const rsiState =
      lastRsi === null ? "—" : lastRsi >= 70 ? "Suracheté" : lastRsi <= 30 ? "Survendu" : "Neutre";

    content = (
      <>
        <div className="stat-grid">
          <article className="stat-card">
            <p>Dernier cours</p>
            <strong>{formatDecimal(lastClose.toFixed(2))}</strong>
          </article>
          <article className="stat-card">
            <p>Tendance (MM{data.short_window} / MM{data.long_window})</p>
            <strong className={trend === "Haussière" ? "up" : trend === "Baissière" ? "down" : ""}>
              {trend}
            </strong>
          </article>
          <article className="stat-card">
            <p>RSI ({data.rsi_period} jours)</p>
            <strong>{lastRsi === null ? "—" : formatDecimal(lastRsi.toFixed(1), 1)}</strong>
          </article>
          <article className="stat-card">
            <p>Signal RSI</p>
            <strong>{rsiState}</strong>
          </article>
        </div>

        <article className="panel">
          <div className="panel-head">
            <div>
              <h2>
                {data.symbol} — {data.name}
              </h2>
              <p>
                Du {data.dates[0]} au {last(data.dates)}
              </p>
            </div>
          </div>
          <ul className="legend">
            <li><i style={{ background: "#5aa6ff" }} />Cours</li>
            <li><i style={{ background: "#fb923c" }} />Moyenne mobile {data.short_window} j</li>
            <li><i style={{ background: "#a78bfa" }} />Moyenne mobile {data.long_window} j</li>
          </ul>
          <svg className="analysis-chart" viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Cours et moyennes mobiles">
            <text x="4" y="14" className="axis">{formatDecimal(max.toFixed(2))}</text>
            <text x="4" y={H - 4} className="axis">{formatDecimal(min.toFixed(2))}</text>
            <path d={path(data.sma_long, toY)} fill="none" stroke="#a78bfa" strokeWidth="2" />
            <path d={path(data.sma_short, toY)} fill="none" stroke="#fb923c" strokeWidth="2" />
            <path d={path(data.close, toY)} fill="none" stroke="#5aa6ff" strokeWidth="2.5" />
          </svg>
          <h3 className="sub">RSI</h3>
          <svg className="analysis-chart" viewBox={`0 0 ${W} ${RSI_H}`} role="img" aria-label="RSI">
            <rect x="0" y={toRsiY(70)} width={W} height={toRsiY(30) - toRsiY(70)} className="rsi-zone" />
            <line x1="0" x2={W} y1={toRsiY(70)} y2={toRsiY(70)} className="rsi-line" />
            <line x1="0" x2={W} y1={toRsiY(30)} y2={toRsiY(30)} className="rsi-line" />
            <text x="4" y={toRsiY(70) - 3} className="axis">70</text>
            <text x="4" y={toRsiY(30) - 3} className="axis">30</text>
            <path d={path(data.rsi, toRsiY)} fill="none" stroke="#3dd68c" strokeWidth="2" />
          </svg>
        </article>
      </>
    );
  }

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Analyse</p>
          <h1>Analyse technique</h1>
          <p className="page-lead">
            Cours, moyennes mobiles et RSI calculés sur l'historique de l'actif choisi.
          </p>
        </div>
      </div>
      {error && <p className="banner">{error}</p>}

      <article className="panel">
        <div className="analysis-controls">
          <label className="trade-field">
            <span>Actif</span>
            <select value={symbol} onChange={(event) => setSymbol(event.target.value)}>
              {quotes.map((row) => (
                <option key={row.symbol} value={row.symbol}>
                  {row.symbol} — {row.name}
                </option>
              ))}
            </select>
          </label>
          <div className="ranges">
            {Object.keys(PERIODS).map((key) => (
              <button
                key={key}
                type="button"
                className={key === period ? "range active" : "range"}
                onClick={() => setPeriod(key)}
              >
                {key}
              </button>
            ))}
          </div>
        </div>
      </article>
      {content}
    </section>
  );
}
