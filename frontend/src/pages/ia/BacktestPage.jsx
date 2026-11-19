import { useState, useEffect } from "react";
import { api } from "../../services/api.js";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
} from "recharts";
import { iaApi } from "../../services/ia.js";
import { fmtPct, toneOf, HORIZONS } from "../../services/ia.js";

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [horizon, setHorizon] = useState(5);
  const [assets, setAssets] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/quotes")
      .then(setAssets)
      .catch(() => {});
  }, []);

  async function runBacktest(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    try {
      const result = await iaApi(`/backtest/${symbol.toUpperCase()}`, { horizon });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Données pour le graphique : rendement prédit vs réel par trade.
  const chartData = data
    ? data.trades.map((t, i) => ({
        i: i + 1,
        predicted: t.predicted_return,
        actual: t.actual_return,
        action: t.action,
      }))
    : [];

  const winTone = data
    ? data.win_rate >= 0.55
      ? "up"
      : data.win_rate < 0.45
        ? "down"
        : ""
    : "";

  return (
    <div className="ia-section">
      <form className="ia-form" onSubmit={runBacktest}>
        <label>
          Symbole
          <select value={symbol} onChange={(e) => setSymbol(e.target.value)} required>
            {assets.length === 0 && <option value="">Chargement des actifs…</option>}
            {assets.map((a) => (
              <option key={a.symbol} value={a.symbol}>
                {a.symbol} — {a.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Horizon
          <select value={horizon} onChange={(e) => setHorizon(Number(e.target.value))}>
            {HORIZONS.map((h) => (
              <option key={h.value} value={h.value}>
                {h.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Backtest…" : "Lancer le backtest"}
        </button>
      </form>

      {error && <p className="banner error">{error}</p>}

      {data && (
        <div className="ia-result">
          <div className="ia-metrics">
            <div className="metric metric-confidence">
              <span className="metric-label">Taux de réussite</span>
              <strong className={`metric-value ${winTone}`}>{fmtPct(data.win_rate)}</strong>
              <div className="conf-gauge">
                <div
                  className="conf-gauge-fill"
                  style={{ width: `${Math.max(2, data.win_rate * 100)}%` }}
                />
              </div>
            </div>
            <div className="metric">
              <span className="metric-label">Rendement cumulé</span>
              <strong className={`metric-value ${toneOf(data.total_return)}`}>
                {fmtPct(data.total_return)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Jours évalués</span>
              <strong className="metric-value">{data.n_points}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Signaux BUY</span>
              <strong className="metric-value up">{data.n_buy}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Signaux SELL</span>
              <strong className="metric-value down">{data.n_sell}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Signaux HOLD</span>
              <strong className="metric-value">{data.n_hold}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Rendement prédit moyen</span>
              <strong className={`metric-value ${toneOf(data.avg_predicted)}`}>
                {fmtPct(data.avg_predicted)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Rendement réel moyen</span>
              <strong className={`metric-value ${toneOf(data.avg_actual)}`}>
                {fmtPct(data.avg_actual)}
              </strong>
            </div>
          </div>

          <div className="ia-chart">
            <h3>Rendement prédit vs rendement réel ({data.trades.length} derniers trades)</h3>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="i" stroke="#93a0b5" tick={{ fontSize: 11 }} />
                <YAxis
                  stroke="#93a0b5"
                  tick={{ fontSize: 11 }}
                  tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                />
                <Tooltip
                  formatter={(v) => fmtPct(v)}
                  contentStyle={{
                    borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.12)",
                    background: "#121a2b",
                    color: "#e8eef8",
                    fontSize: 13,
                  }}
                  labelStyle={{ color: "#93a0b5" }}
                  labelFormatter={(l) => `Trade #${l}`}
                />
                <ReferenceLine y={0} stroke="#5a6a82" />
                <Bar dataKey="actual" name="Rendement réel" radius={[3, 3, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={i}
                      fill={entry.actual >= 0 ? "rgba(11,143,77,0.7)" : "rgba(192,57,43,0.7)"}
                    />
                  ))}
                </Bar>
                <Line
                  type="monotone"
                  dataKey="predicted"
                  stroke="#f0b429"
                  strokeWidth={2}
                  dot={false}
                  name="Rendement prédit"
                />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="ia-chart-note">
              Les barres vertes/rouges montrent le rendement réel sur l'horizon ; la ligne jaune
              est le rendement prédit par le modèle. Un bon modèle suit la même direction que les
              barres. Le taux de réussite mesure la proportion de signaux directionnels (BUY/SELL)
              qui ont eu raison de la direction du marché.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
