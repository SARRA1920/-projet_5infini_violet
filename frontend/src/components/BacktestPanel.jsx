import { useEffect, useRef, useState } from "react";
import { createChart } from "lightweight-charts";
import { api } from "../services/api.js";
import { formatDecimal, formatSigned, signClass } from "../services/format.js";

const GRID = "rgba(255, 255, 255, 0.06)";

function Curve({ result }) {
  const ref = useRef(null);
  useEffect(() => {
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 300,
      layout: { background: { type: "solid", color: "transparent" }, textColor: "#8a96ad" },
      grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
      rightPriceScale: { borderColor: GRID },
      timeScale: { borderColor: GRID },
    });
    const toPoints = (values) => result.dates.map((time, i) => ({ time, value: values[i] }));
    chart
      .addLineSeries({ color: "#8a96ad", lineWidth: 2, priceLineVisible: false })
      .setData(toPoints(result.buy_hold));
    chart
      .addLineSeries({ color: "#3dd68c", lineWidth: 3, priceLineVisible: false })
      .setData(toPoints(result.strategy));
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
    api(`/analysis/${encodeURIComponent(symbol)}/backtest?short=${params.short}&long=${params.long}`)
      .then((data) => {
        if (!Array.isArray(data?.strategy)) throw new Error("Réponse inattendue du serveur");
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

  const better = result && result.strategy_return_pct > result.buy_hold_return_pct;

  return (
    <article className="panel">
      <div className="panel-head">
        <div>
          <h2>Backtesting : croisement de moyennes mobiles</h2>
          <p>
            On est investi quand la moyenne courte dépasse la moyenne longue, sinon en liquidités.
            Départ 10 000, sans frais de transaction.
          </p>
        </div>
      </div>

      <form className="backtest-form" onSubmit={onSubmit}>
        <label className="trade-field">
          <span>Moyenne courte (jours)</span>
          <input inputMode="numeric" value={shortWindow} onChange={(e) => setShortWindow(e.target.value)} />
        </label>
        <label className="trade-field">
          <span>Moyenne longue (jours)</span>
          <input inputMode="numeric" value={longWindow} onChange={(e) => setLongWindow(e.target.value)} />
        </label>
        <button className="primary-btn" type="submit">
          Lancer le backtest
        </button>
      </form>

      {error && <p className="trade-error">{error}</p>}

      {result && (
        <>
          <ul className="legend">
            <li><i style={{ background: "#3dd68c" }} />Stratégie</li>
            <li><i style={{ background: "#8a96ad" }} />Acheter et garder</li>
            <li>Du {result.dates[0]} au {result.dates[result.dates.length - 1]}</li>
          </ul>
          <Curve result={result} />

          <table className="data-table backtest-table">
            <thead>
              <tr>
                <th>Indicateur</th>
                <th>Stratégie</th>
                <th>Acheter et garder</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Rendement total</td>
                <td className={signClass(result.strategy_return_pct)}>{pct(result.strategy_return_pct)}</td>
                <td className={signClass(result.buy_hold_return_pct)}>{pct(result.buy_hold_return_pct)}</td>
              </tr>
              <tr>
                <td>Perte maximale (drawdown)</td>
                <td>-{formatDecimal(result.strategy_max_drawdown_pct.toFixed(2))} %</td>
                <td>-{formatDecimal(result.buy_hold_max_drawdown_pct.toFixed(2))} %</td>
              </tr>
              <tr>
                <td>Capital final</td>
                <td>{formatDecimal(result.strategy[result.strategy.length - 1].toFixed(2))}</td>
                <td>{formatDecimal(result.buy_hold[result.buy_hold.length - 1].toFixed(2))}</td>
              </tr>
              <tr>
                <td>Achats effectués</td>
                <td>{result.entries}</td>
                <td>1</td>
              </tr>
              <tr>
                <td>Temps passé investi</td>
                <td>{formatDecimal(result.time_in_market_pct.toFixed(1), 1)} %</td>
                <td>100 %</td>
              </tr>
            </tbody>
          </table>
          <p className="backtest-note">
            {better
              ? "Sur cette période, la stratégie a fait mieux que simplement acheter et garder."
              : "Sur cette période, acheter et garder a fait mieux ou autant que la stratégie."}{" "}
            Un résultat passé ne garantit rien pour l'avenir.
          </p>
        </>
      )}
    </article>
  );
}
