import { useState, useEffect } from "react";
import { api } from "../../services/api.js";
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
  BarChart,
  Bar,
  Cell,
} from "recharts";
import { iaApi } from "../../services/ia.js";
import { fmtPct, fmtPrice, toneOf, HORIZONS } from "../../services/ia.js";

export default function PredictionPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [horizon, setHorizon] = useState(5);
  const [assets, setAssets] = useState([]);

  // Liste des actifs disponibles (ceux qui ont un cours en base) pour le menu déroulant.
  useEffect(() => {
    api("/quotes")
      .then(setAssets)
      .catch(() => {});
  }, []);
  const [data, setData] = useState(null);
  const [featureImp, setFeatureImp] = useState(null);
  const [diag, setDiag] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runPredict(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    setFeatureImp(null);
    setDiag(null);
    try {
      const result = await iaApi(`/predict/${symbol.toUpperCase()}`, { horizon });
      setData(result);
      // Récupère l'importance des features et le diagnostic en parallèle
      // (indépendants de la prédiction elle-même).
      iaApi(`/feature-importance/${symbol.toUpperCase()}`, { horizon })
        .then(setFeatureImp)
        .catch(() => setFeatureImp(null));
      iaApi(`/diagnostics/${symbol.toUpperCase()}`, { horizon })
        .then(setDiag)
        .catch(() => setDiag(null));
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
            <div className="metric metric-confidence">
              <span className="metric-label">Confiance du modèle</span>
              <strong className="metric-value">{fmtPct(data.confidence)}</strong>
              <div className="conf-gauge" title={`Dispersion des arbres : ${fmtPct(1 - data.confidence)}`}>
                <div
                  className="conf-gauge-fill"
                  style={{ width: `${Math.max(2, data.confidence * 100)}%` }}
                />
              </div>
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
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="label" stroke="#93a0b5" tick={{ fontSize: 12 }} />
                <YAxis domain={["auto", "auto"]} stroke="#93a0b5" tick={{ fontSize: 12 }} />
                <Tooltip
                  formatter={(v) => fmtPrice(v)}
                  contentStyle={{
                    borderRadius: 10,
                    border: "1px solid rgba(255,255,255,0.12)",
                    background: "#121a2b",
                    color: "#e8eef8",
                    fontSize: 13,
                  }}
                  labelStyle={{ color: "#93a0b5" }}
                />
                <ReferenceLine y={data.last_close} stroke="#5a6a82" strokeDasharray="4 4" />
                <Area
                  type="monotone"
                  dataKey="high"
                  stroke="none"
                  fill="rgba(47,124,246,0.15)"
                  name="Borne haute"
                />
                <Area
                  type="monotone"
                  dataKey="low"
                  stroke="none"
                  fill="rgba(255,93,115,0.15)"
                  name="Borne basse"
                />
                <Line
                  type="monotone"
                  dataKey="close"
                  stroke="#2f7cf6"
                  strokeWidth={2.5}
                  dot={{ r: 5, fill: "#2f7cf6" }}
                  name="Cours / Projection"
                />
              </ComposedChart>
            </ResponsiveContainer>
            <p className="ia-chart-note">
              L'aire bleue représente la borne haute (quantile 90% des arbres), l'aire rouge la
              borne basse (quantile 10%). Le modèle est un RandomForestRegressor à 200 arbres.
            </p>
          </div>

          {featureImp && featureImp.features && featureImp.features.length > 0 && (
            <div className="ia-feature-importance">
              <h3>Importance des features</h3>
              <p className="ia-chart-note">
                Quelles variables pèsent le plus dans la prédiction ? Plus la barre est longue,
                plus la feature réduit l'impureté des arbres (somme = 100%).
              </p>
              <ResponsiveContainer width="100%" height={260}>
                <BarChart
                  data={featureImp.features}
                  layout="vertical"
                  margin={{ top: 5, right: 20, bottom: 5, left: 10 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                  <XAxis
                    type="number"
                    stroke="#93a0b5"
                    tick={{ fontSize: 11 }}
                    tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
                  />
                  <YAxis
                    type="category"
                    dataKey="name"
                    stroke="#93a0b5"
                    tick={{ fontSize: 11 }}
                    width={120}
                  />
                  <Tooltip
                    formatter={(v) => `${(v * 100).toFixed(2)}%`}
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid rgba(255,255,255,0.12)",
                      background: "#121a2b",
                      color: "#e8eef8",
                      fontSize: 13,
                    }}
                    labelStyle={{ color: "#93a0b5" }}
                  />
                  <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                    {featureImp.features.map((entry, i) => (
                      <Cell key={i} fill={i === 0 ? "#2f7cf6" : "#3b82f6"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {diag && (
            <div className="ia-diagnostics">
              <h3>Diagnostic du modèle</h3>
              <p className="ia-chart-note">
                Pourquoi le modèle prédit-il (presque) toujours du positif ? Sur un titre
                historiquement montant, la moyenne des rendements futurs est positive et le
                régresseur recentre ses prédictions autour de cette moyenne. Le diagnostic mesure
                ce biais et la qualité du <em>classement</em> (utile même avec un biais de niveau).
              </p>
              <div className="ia-metrics">
                <div className="metric">
                  <span className="metric-label">Prédictions positives</span>
                  <strong className="metric-value">{fmtPct(diag.pct_predicted_positive)}</strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Cibles réelles positives</span>
                  <strong className="metric-value">{fmtPct(diag.pct_actual_positive)}</strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Moyenne prédite</span>
                  <strong className={`metric-value ${toneOf(diag.mean_predicted)}`}>
                    {fmtPct(diag.mean_predicted)}
                  </strong>
                </div>
                <div className="metric">
                  <span className="metric-label">Moyenne réelle</span>
                  <strong className={`metric-value ${toneOf(diag.mean_actual)}`}>
                    {fmtPct(diag.mean_actual)}
                  </strong>
                </div>
              </div>
              <div className="diag-columns">
                <div className="diag-block">
                  <h4>Calibration par quintile de prédiction</h4>
                  <table className="diag-table">
                    <thead>
                      <tr>
                        <th>Quintile</th>
                        <th>Prédit moy.</th>
                        <th>Réel moy.</th>
                        <th>n</th>
                      </tr>
                    </thead>
                    <tbody>
                      {diag.calibration.map((b) => (
                        <tr key={b.bucket}>
                          <td>{b.bucket}</td>
                          <td className={toneOf(b.mean_predicted)}>{fmtPct(b.mean_predicted)}</td>
                          <td className={toneOf(b.mean_actual)}>{fmtPct(b.mean_actual)}</td>
                          <td>{b.n}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="ia-chart-note">
                    Si le rendement réel moyen croît de Q1 à Q5, le modèle classe correctement les
                    jours — même si le niveau des prédictions est décalé.
                  </p>
                </div>
                <div className="diag-block">
                  <h4>IC par feature (Spearman, top 5)</h4>
                  <ul className="diag-ic-list">
                    {diag.feature_ic.slice(0, 5).map((f) => (
                      <li key={f.name}>
                        <span>{f.name}</span>
                        <strong className={toneOf(f.ic)}>
                          {f.ic >= 0 ? "+" : ""}{f.ic.toFixed(3)}
                        </strong>
                      </li>
                    ))}
                  </ul>
                  <p className="ia-chart-note">
                    Une feature dont l'IC est proche de 0 n'apporte aucune information directionnelle
                    — une importance élevée avec un IC nul signale que le modèle mémorise au lieu de
                    généraliser.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
