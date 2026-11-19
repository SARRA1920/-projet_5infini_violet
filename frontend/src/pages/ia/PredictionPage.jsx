import { useState } from "react";
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { iaApi } from "../../services/ia.js";
import { fmtPct, fmtPrice, toneOf, HORIZONS } from "../../services/ia.js";

export default function PredictionPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [horizon, setHorizon] = useState(5);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runPredict(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    try {
      const result = await iaApi(`/predict/${symbol.toUpperCase()}`, { horizon });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Données pour le graphique : dernier point réel + point prédit + intervalle.
  const chartData = data
    ? [
        {
          label: "Dernier cours",
          close: data.last_close,
          low: data.last_close,
          high: data.last_close,
        },
        {
          label: `J+${data.horizon}`,
          close: data.predicted_close,
          low: data.interval_low_close,
          high: data.interval_high_close,
        },
      ]
    : [];

  return (
    <div className="ia-section">
      <form className="ia-form" onSubmit={runPredict}>
        <label>
          Symbole
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="AAPL"
            required
          />
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
          {loading ? "Prédiction…" : "Prédire"}
        </button>
      </form>

      {error && <p className="banner error">{error}</p>}

      {data && (
        <div className="ia-result">
          <div className="ia-metrics">
            <div className="metric">
              <span className="metric-label">Dernier cours</span>
              <strong className="metric-value">{fmtPrice(data.last_close)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Rendement prédit ({data.horizon}j)</span>
              <strong className={`metric-value ${toneOf(data.predicted_return)}`}>
                {fmtPct(data.predicted_return)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Prix projeté</span>
              <strong className="metric-value">{fmtPrice(data.predicted_close)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Intervalle (10-90%)</span>
              <strong className="metric-value">
                {fmtPct(data.interval_low)} → {fmtPct(data.interval_high)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Confiance</span>
              <strong className="metric-value">{fmtPct(data.confidence)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Échantillon d'entraînement</span>
              <strong className="metric-value">{data.n_samples} lignes</strong>
            </div>
          </div>

          <div className="ia-chart">
            <h3>Cours actuel et projection à J+{data.horizon}</h3>
            <ResponsiveContainer width="100%" height={300}>
              <ComposedChart data={chartData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e0e0e0" />
                <XAxis dataKey="label" />
                <YAxis domain={["auto", "auto"]} />
                <Tooltip
                  formatter={(v) => fmtPrice(v)}
                  contentStyle={{ borderRadius: 8, border: "1px solid #ddd" }}
                />
                <ReferenceLine y={data.last_close} stroke="#aaa" strokeDasharray="4 4" />
                <Area
                  type="monotone"
                  dataKey="high"
                  stroke="none"
                  fill="#2980b922"
                  name="Borne haute"
                />
                <Area
                  type="monotone"
                  dataKey="low"
                  stroke="none"
                  fill="#e74c3c22"
                  name="Borne basse"
                />
                <Line
                  type="monotone"
                  dataKey="close"
                  stroke="#2980b9"
                  strokeWidth={2}
                  dot={{ r: 5 }}
                  name="Cours / Projection"
                />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="ia-chart-note">
              L'aire bleue représente la borne haute (quantile 90% des arbres), l'aire rouge la
              borne basse (quantile 10%). Le modèle est un RandomForestRegressor à 200 arbres.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
