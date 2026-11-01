import { useEffect, useRef, useState } from "react";
import { createChart } from "lightweight-charts";
import { api } from "../services/api.js";
import { formatDecimal, formatSigned, signClass } from "../services/format.js";

const GRID = "rgba(255, 255, 255, 0.06)";
const COLORS = { hold: "#8a96ad", crossover: "#3dd68c", trend: "#fb923c", rsi: "#a78bfa" };

function Curves({ result }) {
  const ref = useRef(null);
  useEffect(() => {
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 320,
      layout: { background: { type: "solid", color: "transparent" }, textColor: "#8a96ad" },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: GRID },
      timeScale: { borderColor: GRID },
    });
    result.strategies.forEach((strategy) => {
      chart
        .addLineSeries({
          color: COLORS[strategy.key],
          lineWidth: strategy.key === "hold" ? 2 : 3,
          priceLineVisible: false,
          lastValueVisible: false,
        })
        .setData(result.dates.map((time, i) => ({ time, value: strategy.curve[i] })));
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [result]);
  return <div ref={ref} />;
}

const pct = (value) => `${formatSigned(value.toFixed(2))} %`;

export default function BacktestPanel({ symbol }) {
  const [shortWindow, setShortWindow] = useState("20");
  const [longWindow, setLongWindow] = useState("50");
  const [params, setParams] = useState({ short: 20, long: 50 });
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!symbol) return;
    setError("");
    api(`/analysis/${encodeURIComponent(symbol)}/compare?short=${params.short}&long=${params.long}`)
      .then((data) => {
        if (!Array.isArray(data?.strategies)) throw new Error("Réponse inattendue du serveur");
        setResult(data);
      })
      .catch((err) => {
        setResult(null);
        setError(err.message);
      });
  }, [symbol, params]);

  function onSubmit(event) {
    event.preventDefault();
    setParams({ short: Number(shortWindow), long: Number(longWindow) });
  }

  const best = result
    ? result.strategies.reduce((a, b) => (b.return_pct > a.return_pct ? b : a))
    : null;
  const safest = result
    ? result.strategies.reduce((a, b) => (b.max_drawdown_pct < a.max_drawdown_pct ? b : a))
    : null;

  return (
    <article className="panel">
      <div className="panel-head">
        <div>
          <h2>Comparaison de stratégies (backtesting)</h2>
          <p>
            Quatre règles rejouées sur le passé de l'actif, même jour de départ, 10 000 de capital,
            achats et ventes au cours de clôture, sans frais de transaction.
          </p>
        </div>
      </div>

      <form className="backtest-form" onSubmit={onSubmit}>
        <label className="trade-field">
          <span>Croisement : moyenne courte (jours)</span>
          <input inputMode="numeric" value={shortWindow} onChange={(e) => setShortWindow(e.target.value)} />
        </label>
        <label className="trade-field">
          <span>Croisement : moyenne longue (jours)</span>
          <input inputMode="numeric" value={longWindow} onChange={(e) => setLongWindow(e.target.value)} />
        </label>
        <button className="primary-btn" type="submit">
          Comparer
        </button>
      </form>

      {error && <p className="trade-error">{error}</p>}

      {result && (
        <>
          <ul className="legend">
            {result.strategies.map((strategy) => (
              <li key={strategy.key}>
                <i style={{ background: COLORS[strategy.key] }} />
                {strategy.label}
              </li>
            ))}
            <li>
              Du {result.dates[0]} au {result.dates[result.dates.length - 1]}
            </li>
          </ul>
          <Curves result={result} />

          <div className="table-scroll">
            <table className="data-table backtest-table">
              <thead>
                <tr>
                  <th>Stratégie</th>
                  <th>Rendement</th>
                  <th>Perte maximale</th>
                  <th>Rendement / risque</th>
                  <th>Achats</th>
                  <th>Temps investi</th>
                </tr>
              </thead>
              <tbody>
                {result.strategies.map((strategy) => (
                  <tr key={strategy.key}>
                    <td>
                      <i className="dot" style={{ background: COLORS[strategy.key] }} />
                      {strategy.label}
                    </td>
                    <td className={signClass(strategy.return_pct)}>{pct(strategy.return_pct)}</td>
                    <td>-{formatDecimal(strategy.max_drawdown_pct.toFixed(2))} %</td>
                    <td>
                      {strategy.return_to_risk === null
                        ? "—"
                        : formatDecimal(strategy.return_to_risk.toFixed(2))}
                    </td>
                    <td>{strategy.entries}</td>
                    <td>{formatDecimal(strategy.time_in_market_pct.toFixed(1), 1)} %</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="backtest-note">
            Meilleur rendement : <b>{best.label}</b>. Perte maximale la plus faible :{" "}
            <b>{safest.label}</b>. « Rendement / risque » = rendement divisé par la perte maximale :
            plus il est élevé, mieux le gain compense le risque pris. Un résultat passé ne garantit
            rien pour l'avenir.
          </p>
        </>
      )}
    </article>
  );
}
