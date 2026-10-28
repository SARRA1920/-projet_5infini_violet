import { useEffect, useState } from "react";
import CandleChart from "../components/CandleChart.jsx";
import { api } from "../services/api.js";
import { formatDecimal } from "../services/format.js";
import "./trading.css";
import "./analysis.css";

const PERIODS = { "3M": 63, "6M": 126, "1A": 260 };
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
            <li><i style={{ background: "#3dd68c" }} /><i style={{ background: "#ff5d73" }} />Chandeliers (hausse / baisse)</li>
            <li><i style={{ background: "#fb923c" }} />Moyenne mobile {data.short_window} j</li>
            <li><i style={{ background: "#a78bfa" }} />Moyenne mobile {data.long_window} j</li>
          </ul>
          <CandleChart data={data} />
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
