import { useState, useEffect } from "react";
import { api } from "../../services/api.js";
import {
  ComposedChart,
  LineChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
  Legend,
} from "recharts";
import { iaApi } from "../../services/ia.js";
import { fmtPct, toneOf, HORIZONS } from "../../services/ia.js";

// Options de réglages de réalisme du backtest.
const CAPITAL_OPTIONS = [
  { value: 0.1, label: "10 %" },
  { value: 0.25, label: "25 %" },
  { value: 0.5, label: "50 %" },
  { value: 1.0, label: "100 %" },
];

export default function BacktestPage() {
  const [symbol, setSymbol] = useState("AAPL");
  const [horizon, setHorizon] = useState(5);
  const [capitalFraction, setCapitalFraction] = useState(0.25);
  const [feeBps, setFeeBps] = useState(10);
  const [slippageBps, setSlippageBps] = useState(5);
  const [allowShort, setAllowShort] = useState(false);
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
      const result = await iaApi(`/backtest/${symbol.toUpperCase()}`, {
        horizon,
        capital_fraction: capitalFraction,
        fee_bps: feeBps,
        slippage_bps: slippageBps,
        allow_short: allowShort,
      });
      setData(result);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  // Données pour le graphique : rendement prédit vs réel par décision.
  const chartData = data
    ? data.trades.map((t, i) => ({
        i: i + 1,
        predicted: t.predicted_return,
        actual: t.actual_return,
        action: t.action,
      }))
    : [];

  // Courbes d'équité : stratégie (frais inclus) vs buy & hold.
  const equityData = data
    ? data.equity_curve.map((p) => ({
        day: p.day,
        strategy: p.strategy - 1,
        buyHold: p.buy_hold - 1,
      }))
    : [];

  const winTone = data
    ? data.win_rate >= 0.55
      ? "up"
      : data.win_rate < 0.45
        ? "down"
        : ""
    : "";

  const beatsMarket = data ? data.total_return > data.buy_hold_return : false;

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
        <label>
          Capital par position
          <select
            value={capitalFraction}
            onChange={(e) => setCapitalFraction(Number(e.target.value))}
          >
            {CAPITAL_OPTIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Frais (bps/côté)
          <input
            type="number"
            min="0"
            max="100"
            value={feeBps}
            onChange={(e) => setFeeBps(Number(e.target.value))}
          />
        </label>
        <label>
          Slippage (bps/côté)
          <input
            type="number"
            min="0"
            max="100"
            value={slippageBps}
            onChange={(e) => setSlippageBps(Number(e.target.value))}
          />
        </label>
        <label className="ia-checkbox">
          <input
            type="checkbox"
            checked={allowShort}
            onChange={(e) => setAllowShort(e.target.checked)}
          />
          Vente à découvert
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Backtest…" : "Lancer le backtest"}
        </button>
      </form>

      {error && <p className="banner error">{error}</p>}

      {data && (
        <div className="ia-result">
          <p className="ia-chart-note">
            Backtest <strong>walk-forward</strong> : au jour t, le modèle n'est entraîné que
            sur des échantillons dont le résultat est connu avant t — aucune fuite de données.
            La simulation applique vos frais et votre slippage, bloque le capital {data.horizon}{" "}
            jours par position (max&nbsp;{Math.round(1 / data.capital_fraction)} positions
            simultanées) et interdit la vente à découvert sauf option cochée.
          </p>

          <div className="ia-metrics">
            <div className="metric metric-confidence">
              <span className="metric-label">Taux de réussite (hors échantillon)</span>
              <strong className={`metric-value ${winTone}`}>{fmtPct(data.win_rate)}</strong>
              <div className="conf-gauge">
                <div
                  className="conf-gauge-fill"
                  style={{ width: `${Math.max(2, data.win_rate * 100)}%` }}
                />
              </div>
            </div>
            <div className="metric">
              <span className="metric-label">Stratégie (net de frais)</span>
              <strong className={`metric-value ${toneOf(data.total_return)}`}>
                {fmtPct(data.total_return)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Buy &amp; hold (même période)</span>
              <strong className={`metric-value ${toneOf(data.buy_hold_return)}`}>
                {fmtPct(data.buy_hold_return)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Vs marché</span>
              <strong className={`metric-value ${beatsMarket ? "up" : "down"}`}>
                {beatsMarket ? "surperforme" : "sous-performe"}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Drawdown maximal</span>
              <strong className="metric-value down">−{fmtPct(data.max_drawdown)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">IC (prédit vs réel)</span>
              <strong className={`metric-value ${toneOf(data.information_coefficient)}`}>
                {data.information_coefficient.toFixed(3)}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Frais payés</span>
              <strong className="metric-value">−{fmtPct(data.fees_paid)}</strong>
            </div>
            <div className="metric">
              <span className="metric-label">Positions / ignorées / flat</span>
              <strong className="metric-value">
                {data.n_opened} / {data.n_skipped} / {data.n_flat}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Décisions BUY / SELL / HOLD</span>
              <strong className="metric-value">
                <span className="up">{data.n_buy}</span> /{" "}
                <span className="down">{data.n_sell}</span> / {data.n_hold}
              </strong>
            </div>
            <div className="metric">
              <span className="metric-label">Bloqués par filtre de tendance</span>
              <strong className="metric-value">{data.n_trend_blocked}</strong>
            </div>
          </div>

          <div className="ia-chart">
            <h3>Équité : stratégie vs buy &amp; hold (base 100)</h3>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={equityData} margin={{ top: 10, right: 20, bottom: 5, left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
                <XAxis dataKey="day" stroke="#93a0b5" tick={{ fontSize: 11 }} />
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
                  labelFormatter={(l) => `Jour ${l}`}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <ReferenceLine y={0} stroke="#5a6a82" />
                <Line
                  type="monotone"
                  dataKey="strategy"
                  name="Stratégie (net de frais)"
                  stroke="#f0b429"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="buyHold"
                  name="Buy &amp; hold"
                  stroke="#7c9cf5"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
            <p className="ia-chart-note">
              Comparaison honnête : la stratégie est-elle meilleure que « acheter et ne rien
              faire » sur la même période ? L'IC (corrélation de Spearman entre rendements
              prédits et réels) mesure le pouvoir prédictif hors échantillon — autour de 0, le
              modèle ne prédit rien ; un bon modèle réel dépasse rarement 0,3.
            </p>
          </div>

          <div className="ia-chart">
            <h3>Rendement prédit vs rendement réel ({data.trades.length} dernières décisions)</h3>
            <ResponsiveContainer width="100%" height={260}>
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
                  labelFormatter={(l) => `Décision #${l}`}
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
              En walk-forward, les prédictions ne collent plus aux barres : le modèle ne peut
              pas « deviner » le passé qu'il n'a jamais vu. Les barres montrent le rendement
              réel sur l'horizon ; la ligne jaune, la prédiction faite avec les seules données
              antérieures.
            </p>
          </div>

          <div className="ia-chart">
            <h3>Journal des décisions (échantillon)</h3>
            <div className="ia-table-wrap">
              <table className="ia-table">
                <thead>
                  <tr>
                    <th>Jour</th>
                    <th>Action</th>
                    <th>Prédit</th>
                    <th>Réel</th>
                    <th>Direction ?</th>
                    <th>Entraînement (échantillons)</th>
                    <th>Position</th>
                    <th>P&amp;L net</th>
                  </tr>
                </thead>
                <tbody>
                  {data.trades.map((t) => (
                    <tr key={t.index}>
                      <td>{t.index}</td>
                      <td className={t.action === "BUY" ? "up" : t.action === "SELL" ? "down" : ""}>
                        {t.action}
                      </td>
                      <td>{fmtPct(t.predicted_return)}</td>
                      <td>{fmtPct(t.actual_return)}</td>
                      <td>{t.correct ? "✓" : "✗"}</td>
                      <td title={`dernier indice d'entraînement : ${t.train_last_index}`}>
                        {t.train_size}
                      </td>
                      <td>{t.opened ? "ouverte" : "—"}</td>
                      <td className={t.pnl != null ? toneOf(t.pnl) : ""}>
                        {t.pnl != null ? fmtPct(t.pnl) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="ia-chart-note">
              La colonne « entraînement » donne le nombre d'échantillons dont disposait le
              modèle au jour de la décision — il croît avec le temps et ne contient jamais les
              jours futurs (garantie : dernier indice d'entraînement ≤ jour − horizon).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
