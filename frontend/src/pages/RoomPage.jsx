import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createChart } from "lightweight-charts";
import { useAuth } from "../context/AuthContext.jsx";
import { api } from "../services/api.js";
import "./rooms.css";

const money = (n) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n) => `${n > 0 ? "+" : ""}${Number(n).toFixed(2).replace(".", ",")} %`;
const clock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
const cls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");

function PriceChart({ history }) {
  const ref = useRef(null);
  const seriesRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 300,
      layout: { background: { type: "solid", color: "transparent" }, textColor: "#8a96ad" },
      grid: { vertLines: { color: "rgba(255,255,255,0.05)" }, horzLines: { color: "rgba(255,255,255,0.05)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
    });
    seriesRef.current = chart.addAreaSeries({
      lineColor: "#5aa6ff",
      topColor: "rgba(90,166,255,0.35)",
      bottomColor: "rgba(90,166,255,0.02)",
      lineWidth: 2,
    });
    chartRef.current = chart;
    return () => chart.remove();
  }, []);

  useEffect(() => {
    seriesRef.current.setData(history.map(([time, value]) => ({ time, value })));
    chartRef.current.timeScale().fitContent();
  }, [history]);

  return <div ref={ref} className="rm-chart" />;
}

export default function RoomPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const { refreshUser } = useAuth();
  const [s, setS] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [qty, setQty] = useState("");
  const [left, setLeft] = useState(0);
  const [brief, setBrief] = useState(true);
  const [busy, setBusy] = useState(false);
  const deadline = useRef(0);

  const apply = useCallback((state) => {
    setS(state);
    deadline.current = Date.now() + state.seconds_left * 1000;
    setLeft(state.seconds_left);
    setSelected((cur) => cur || state.assets[0]?.symbol);
  }, []);

  useEffect(() => {
    api(`/formation/runs/${runId}`).then(apply).catch((err) => setError(err.message));
  }, [runId, apply]);

  // Montée de niveau : met à jour le badge de l'en-tête
  useEffect(() => {
    if (s?.promotion) refreshUser().catch(() => {});
  }, [s?.promotion, refreshUser]);

  // Chronomètre : décompte local, resynchronisé à l'arrivée du temps écoulé
  useEffect(() => {
    if (!s || s.status !== "active") return undefined;
    const timer = setInterval(() => {
      const remaining = Math.max(0, Math.round((deadline.current - Date.now()) / 1000));
      setLeft(remaining);
      if (remaining === 0) {
        clearInterval(timer);
        api(`/formation/runs/${runId}`).then(apply).catch(() => {});
      }
    }, 500);
    return () => clearInterval(timer);
  }, [s?.status, s?.run_id, runId, apply]);

  async function act(path, body) {
    setBusy(true);
    setError("");
    try {
      const next = await api(`/formation/runs/${runId}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      apply(next);
      if (path === "trade") setQty("");
    } catch (err) {
      setError(err.message);
      api(`/formation/runs/${runId}`).then(apply).catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  if (error && !s) return <p className="status error">{error}</p>;
  if (!s) return <p className="status">Chargement…</p>;

  const asset = s.assets.find((a) => a.symbol === selected) || s.assets[0];
  const quantity = Number(qty.replace(",", "."));
  const valid = quantity > 0 && asset.price;
  const cost = valid ? quantity * asset.price : 0;
  const ret = (s.equity / s.initial_cash - 1) * 100;
  const active = s.status === "active";
  const danger = left <= 60;

  function fill(fraction, side) {
    if (!asset.price) return;
    const max = side === "buy" ? s.cash / asset.price : asset.quantity;
    setQty(String(Math.floor(max * fraction * 10000) / 10000));
  }

  return (
    <section className="page rm rm-play">
      <header className="rm-bar">
        <div>
          <p className="page-kicker">Salle de marché · {s.crisis.name}</p>
          <h1>
            {new Date(s.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}
          </h1>
          <p className="rm-day">
            Jour {s.day} / {s.total_days}
          </p>
        </div>
        <div className={`rm-timer${danger && active ? " danger" : ""}`}>
          <span>Temps restant</span>
          <strong>{clock(left)}</strong>
        </div>
        <div className="rm-kpis">
          <div>
            <span>Valeur</span>
            <strong>{money(s.equity)} $</strong>
          </div>
          <div>
            <span>Rendement</span>
            <strong className={cls(ret)}>{pct(ret)}</strong>
          </div>
          <div>
            <span>Liquidités</span>
            <strong>{money(s.cash)} $</strong>
          </div>
        </div>
      </header>

      {brief && s.day === 1 && active && (
        <div className="rm-brief">
          <p>
            <strong>Contexte.</strong> {s.crisis.story}
          </p>
          <button onClick={() => setBrief(false)}>Compris</button>
        </div>
      )}
      {error && <p className="status error">{error}</p>}

      <div className="rm-layout">
        <div className="rm-left">
          <div className="panel">
            <div className="rm-asset-head">
              <h2>
                {asset.symbol} <small>{asset.name}</small>
              </h2>
              <div>
                <strong>{asset.price ? money(asset.price) : "—"}</strong>{" "}
                {asset.change_pct !== null && <span className={cls(asset.change_pct)}>{pct(asset.change_pct)}</span>}
              </div>
            </div>
            <PriceChart history={asset.history} />
          </div>

          <div className="panel">
            <h2>Mes positions</h2>
            {s.assets.some((a) => a.quantity > 0) ? (
              <table className="rm-table">
                <thead>
                  <tr>
                    <th>Actif</th>
                    <th>Quantité</th>
                    <th>Cours</th>
                    <th>Valeur</th>
                  </tr>
                </thead>
                <tbody>
                  {s.assets
                    .filter((a) => a.quantity > 0)
                    .map((a) => (
                      <tr key={a.symbol} onClick={() => setSelected(a.symbol)}>
                        <td>{a.symbol}</td>
                        <td>{a.quantity}</td>
                        <td>{money(a.price)}</td>
                        <td>{money(a.quantity * a.price)} $</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            ) : (
              <p className="rm-muted">Aucune position : tout ton capital est en liquidités.</p>
            )}
          </div>
        </div>

        <aside className="rm-right">
          <div className="panel">
            <h2>Actifs</h2>
            <ul className="rm-assets">
              {s.assets.map((a) => (
                <li
                  key={a.symbol}
                  className={a.symbol === asset.symbol ? "active" : ""}
                  onClick={() => setSelected(a.symbol)}
                >
                  <span>
                    <strong>{a.symbol}</strong>
                    <small>{a.name}</small>
                  </span>
                  <span className="rm-assets-price">
                    {a.price ? money(a.price) : "—"}
                    {a.change_pct !== null && <em className={cls(a.change_pct)}>{pct(a.change_pct)}</em>}
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="panel">
            <h2>Passer un ordre · {asset.symbol}</h2>
            <label className="trade-field">
              Quantité
              <input
                value={qty}
                onChange={(e) => setQty(e.target.value)}
                inputMode="decimal"
                placeholder="0"
                disabled={!active}
              />
            </label>
            <div className="rm-quick">
              {[0.25, 0.5, 1].map((f) => (
                <button key={f} disabled={!active} onClick={() => fill(f, "buy")}>
                  {f === 1 ? "Max achat" : `${f * 100} % cash`}
                </button>
              ))}
              <button disabled={!active || !asset.quantity} onClick={() => fill(1, "sell")}>
                Tout vendre
              </button>
            </div>
            <p className="rm-cost">Montant : {valid ? `${money(cost)} $` : "—"}</p>
            <div className="rm-trade">
              <button
                className="buy"
                disabled={!active || !valid || busy}
                onClick={() => act("trade", { symbol: asset.symbol, side: "buy", quantity })}
              >
                Acheter
              </button>
              <button
                className="sell"
                disabled={!active || !valid || busy}
                onClick={() => act("trade", { symbol: asset.symbol, side: "sell", quantity })}
              >
                Vendre
              </button>
            </div>
            <button className="rm-next" disabled={!active || busy} onClick={() => act("next")}>
              {s.is_last_day ? "Terminer la partie" : "Jour suivant →"}
            </button>
            <p className="rm-muted">Les ordres sont exécutés au cours de clôture du jour, sans frais.</p>
          </div>
        </aside>
      </div>

      {!active && (
        <div className="rm-overlay">
          <div className="rm-result">
            <span className={`rm-pill ${s.result.completed ? "ok" : "late"}`}>
              {s.result.completed ? "Salle terminée" : "Temps écoulé"}
            </span>
            <h2>{s.crisis.name}</h2>
            {!s.result.completed && (
              <p className="rm-muted">
                Le temps imparti est écoulé : la salle est fermée. Ton score est calculé sur ta situation au jour{" "}
                {s.result.days_played} sur {s.total_days}. Tu peux la refaire quand tu veux.
              </p>
            )}
            <div className="rm-score">
              <strong className={cls(s.result.score)}>{s.result.score}</strong>
              <span>points</span>
            </div>
            <ul className="rm-result-list">
              <li>
                <span>Rendement</span>
                <strong className={cls(s.result.return_pct)}>{pct(s.result.return_pct)}</strong>
              </li>
              <li>
                <span>Perte maximale</span>
                <strong className="down">−{String(s.result.max_drawdown_pct).replace(".", ",")} %</strong>
              </li>
            </ul>
            <p className="rm-muted">Score = rendement − (perte maximale ÷ 2)</p>
            {s.result.validated && <p className="rm-validated">✓ Salle validée</p>}
            {s.result.completed && !s.result.validated && (
              <p className="rm-muted">Il fallait au moins 3 points pour valider cette salle. Tu peux réessayer.</p>
            )}
            {s.promotion && (
              <div className="rm-promo">
                🎉 Niveau supérieur ! Tu passes <strong>{s.promotion.to_label}</strong>. De nouvelles salles sont
                débloquées.
              </div>
            )}
            <div className="rm-actions">
              <button className="rm-btn" onClick={() => navigate("/formation")}>
                Retour aux salles
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
