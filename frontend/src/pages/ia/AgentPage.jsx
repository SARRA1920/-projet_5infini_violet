import { useState, useEffect } from "react";
import { api } from "../../services/api.js";
import { iaApi } from "../../services/ia.js";
import {
  fmtPct,
  toneOf,
  HORIZONS,
  ACTION_LABELS,
  ACTION_TONES,
} from "../../services/ia.js";

export default function AgentPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [horizon, setHorizon] = useState(5);
  const [assets, setAssets] = useState([]);

  // Liste des actifs disponibles (ceux qui ont un cours en base) pour le menu déroulant.
  useEffect(() => {
    api("/quotes")
      .then(setAssets)
      .catch(() => {});
  }, []);
  const [decision, setDecision] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runAgent(e) {
    e.preventDefault();
    setLoading(true);
    setError("");
    setDecision(null);
    try {
      const data = await iaApi(`/agent/${symbol.toUpperCase()}`, { horizon });
      setDecision(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ia-section">
      <form className="ia-form" onSubmit={runAgent}>
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
          {loading ? "Analyse…" : "Obtenir la décision"}
        </button>
      </form>

      {error && <p className="banner error">{error}</p>}

      {decision && (
        <div className="agent-result">
          <div className={`agent-action ${ACTION_TONES[decision.action] || ""}`}>
            <span className="action-label">{ACTION_LABELS[decision.action] || decision.action}</span>
            <span className="action-symbol">{decision.symbol}</span>
          </div>

          <div className="ia-metrics">
            <div className="metric">
              <span className="metric-label">Confiance</span>
              <strong className="metric-value">{fmtPct(decision.confidence)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Score composite</span>
              <strong className={`metric-value ${toneOf(decision.composite_score)}`}>
                {decision.composite_score.toFixed(3)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Rendement prédit</span>
              <strong className={`metric-value ${toneOf(decision.predicted_return)}`}>
                {fmtPct(decision.predicted_return)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Horizon</span>
              <strong className="metric-value">{decision.horizon} jours</strong>
            </div>
          </div>

          <div className="agent-reasons">
            <h3>Signaux combinés</h3>
            <p className="ia-help">
              Le score composite agrège trois signaux pondérés : prédiction IA (50%), technique
              (30%), sentiment (20%). Chaque ligne indique la contribution au score final. La ligne
              « filtre » (contribution nulle) signale un achat/une vente bloqués par le filtre de
              tendance SMA20/SMA50.
            </p>
            <ul className="reason-list">
              {decision.reasons.map((r, i) => (
                <li key={i} className={`reason ${toneOf(r.contribution)}`}>
                  <span className="reason-signal">{r.signal}</span>
                  <span className="reason-detail">{r.detail}</span>
                  <span className={`reason-contrib ${toneOf(r.contribution)}`}>
                    {r.contribution >= 0 ? "+" : ""}
                    {r.contribution.toFixed(3)}
                  </span>
                </li>
              ))}
            </ul>
            <div className="reason-total">
              Total : <strong className={toneOf(decision.composite_score)}>
                {decision.composite_score.toFixed(3)}
              </strong>
              <span className="reason-threshold">
                (seuil de décision : ±{decision.threshold.toFixed(2)} — au-delà
                BUY/SELL, sinon HOLD ; un achat reste bloqué si la SMA20 est
                sous la SMA50)
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
