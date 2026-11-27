import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createChart } from "lightweight-charts";
import { api } from "../services/api.js";
import "./arcade.css";

const money = (n) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n) => `${n > 0 ? "+" : ""}${Number(n).toFixed(2).replace(".", ",")} %`;
const cls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");

// Couleurs par nature de bougie : réelle (vraies données), choc (généré par Sarra),
// IA (généré par le modèle stochastique calibré par l'IA).
const BAR_COLORS = {
  reel: { up: "#26a69a", down: "#ef5350" },
  choc: { up: "#f5c242", down: "#f5c242" },
  ia: { up: "rgba(38,166,154,0.45)", down: "rgba(239,83,80,0.45)" },
};

function colorFor(bar) {
  const set = BAR_COLORS[bar.kind] || BAR_COLORS.reel;
  return bar.close >= bar.open ? set.up : set.down;
}

function sma(history, period) {
  const closes = history.map((h) => h.close);
  const out = [];
  for (let i = period - 1; i < closes.length; i++) {
    const slice = closes.slice(i - period + 1, i + 1);
    const avg = slice.reduce((a, b) => a + b, 0) / period;
    out.push({ time: history[i].time, value: avg });
  }
  return out;
}

function CandleChart({ history }) {
  const ref = useRef(null);
  const chartRef = useRef(null);
  const candleRef = useRef(null);
  const volumeRef = useRef(null);
  const maRef = useRef({});
  const priceLineRef = useRef(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const chart = createChart(ref.current, {
      autoSize: true,
      height: 460,
      layout: {
        background: { type: "solid", color: "transparent" },
        textColor: "#7c8494",
        fontFamily: '"IBM Plex Mono", ui-monospace, monospace',
        fontSize: 11,
      },
      grid: { vertLines: { color: "rgba(255,255,255,0.04)" }, horzLines: { color: "rgba(255,255,255,0.04)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)", scaleMargins: { top: 0.08, bottom: 0.26 } },
      timeScale: { borderColor: "rgba(255,255,255,0.08)", visible: false },
      crosshair: {
        vertLine: { color: "rgba(255,255,255,0.25)", width: 1, style: 3, labelBackgroundColor: "#1b2230" },
        horzLine: { color: "rgba(255,255,255,0.25)", width: 1, style: 3, labelBackgroundColor: "#1b2230" },
      },
    });
    const candle = chart.addCandlestickSeries({
      upColor: "#26a69a",
      downColor: "#ef5350",
      borderUpColor: "#26a69a",
      borderDownColor: "#ef5350",
      wickUpColor: "#26a69a",
      wickDownColor: "#ef5350",
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    const ma5 = chart.addLineSeries({ color: "#e8eaed", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const ma10 = chart.addLineSeries({ color: "#f5c242", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });
    const ma20 = chart.addLineSeries({ color: "#c084fc", lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false });

    candleRef.current = candle;
    volumeRef.current = volume;
    maRef.current = { ma5, ma10, ma20 };
    chartRef.current = chart;

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData.size) {
        setHover(null);
        return;
      }
      const bar = param.seriesData.get(candle);
      if (bar) setHover(bar);
    });

    return () => chart.remove();
  }, []);

  useEffect(() => {
    candleRef.current.setData(
      history.map((h) => ({
        time: h.time,
        open: h.open,
        high: h.high,
        low: h.low,
        close: h.close,
        color: colorFor(h),
        borderColor: colorFor(h),
        wickColor: colorFor(h),
      }))
    );
    volumeRef.current.setData(
      history.map((h) => ({
        time: h.time,
        value: h.volume || 0,
        color: h.close >= h.open ? "rgba(38,166,154,0.5)" : "rgba(239,83,80,0.5)",
      }))
    );
    maRef.current.ma5.setData(sma(history, 5));
    maRef.current.ma10.setData(sma(history, 10));
    maRef.current.ma20.setData(sma(history, 20));
    chartRef.current.timeScale().fitContent();

    if (priceLineRef.current) {
      candleRef.current.removePriceLine(priceLineRef.current);
      priceLineRef.current = null;
    }
    const last = history[history.length - 1];
    if (last) {
      priceLineRef.current = candleRef.current.createPriceLine({
        price: last.close,
        color: "rgba(255,255,255,0.4)",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "dernier",
      });
    }
  }, [history]);

  const last = history[history.length - 1];
  const shown = hover || last;

  return (
    <div className="ag-chart-wrap">
      {shown && (
        <div className="ag-chart-legend">
          <span>O {money(shown.open)}</span>
          <span>H {money(shown.high)}</span>
          <span>L {money(shown.low)}</span>
          <strong className={shown.close >= shown.open ? "up" : "down"}>C {money(shown.close)}</strong>
          <span className="ag-ma ma5">MA5</span>
          <span className="ag-ma ma10">MA10</span>
          <span className="ag-ma ma20">MA20</span>
        </div>
      )}
      <div ref={ref} className="ag-chart" />
      <div className="ag-ai-legend">
        <span><i className="ag-dot" style={{ background: BAR_COLORS.reel.up }} /> Vraies données</span>
        <span><i className="ag-dot" style={{ background: BAR_COLORS.choc.up }} /> Jour du choc</span>
        <span><i className="ag-dot" style={{ background: BAR_COLORS.ia.up }} /> Suite générée par l'IA</span>
      </div>
    </div>
  );
}

export default function AiRunPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [s, setS] = useState(null);
  const [error, setError] = useState("");
  const [side, setSide] = useState("buy");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);
  const [showCalibration, setShowCalibration] = useState(false);

  const apply = useCallback((state) => setS(state), []);

  useEffect(() => {
    api(`/salles-de-jeu/ai-runs/${runId}`).then(apply).catch((err) => setError(err.message));
  }, [runId, apply]);

  async function act(path, body) {
    setBusy(true);
    setError("");
    try {
      const next = await api(`/salles-de-jeu/ai-runs/${runId}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      apply(next);
      if (path === "trade") setQty("");
    } catch (err) {
      setError(err.message);
      api(`/salles-de-jeu/ai-runs/${runId}`).then(apply).catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  async function closeSession() {
    if (!window.confirm("Fermer cette session sans la finaliser ? Ta progression ne sera pas comptée.")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/salles-de-jeu/ai-runs/${runId}/close`, { method: "POST" });
      navigate("/salles-de-jeu");
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (error && !s) return <p className="status error">{error}</p>;
  if (!s) return <p className="status">Chargement…</p>;

  const quantity = Number(qty.replace(",", "."));
  const valid = quantity > 0 && s.price;
  const cost = valid ? quantity * s.price : 0;
  const ret = (s.equity / s.initial_cash - 1) * 100;
  const active = s.status === "active";
  const calib = s.calibration;

  function fill(fraction) {
    if (!s.price) return;
    const max = side === "buy" ? s.cash / s.price : s.quantity;
    setQty(String(Math.floor(max * fraction * 10000) / 10000));
  }

  return (
    <section className="page ag ag-play">
      <header className="ag-bar">
        <div>
          <p className="ag-day">Salle IA · choc + suite calculée par l'IA</p>
          <h1>{s.symbol} <small>{s.asset_name}</small></h1>
          <p className="ag-day">
            Choc de −{String(Math.round(s.shock_pct * 1000) / 10).replace(".", ",")} % · jour {s.day} / {s.total_steps} après le choc
          </p>
        </div>
        <div className="ag-bar-right">
          <div className="ag-kpis">
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
          {active && (
            <button className="ag-close" disabled={busy} onClick={closeSession}>
              ✕ Fermer la session
            </button>
          )}
        </div>
      </header>

      {s.day === 1 && active && (
        <div className="ag-brief">
          <strong>Contexte.</strong> {s.pre_shock_days} jours de vraies données, puis un choc brutal de −
          {String(Math.round(s.shock_pct * 1000) / 10).replace(".", ",")} % frappe {s.symbol}. À partir d'ici, il
          n'y a plus de vraies données : la suite de la courbe est calculée par un modèle stochastique (GBM)
          calibré par l'IA. Clique sur « Comment l'IA a calculé cette suite ? » pour voir le détail.
        </div>
      )}
      {error && <p className="status error">{error}</p>}

      <div className="ag-layout no-watchlist">
        <div className="ag-center">
          <div className="ag-asset-head">
            <h2>
              {s.symbol} <small>{s.asset_name}</small>
            </h2>
            <strong>{money(s.price)}</strong>
          </div>
          <CandleChart history={s.history} />

          <button className="ag-calib-toggle" onClick={() => setShowCalibration((v) => !v)}>
            {showCalibration ? "▼" : "▶"} Comment l'IA a calculé cette suite ?
          </button>
          {showCalibration && calib && (
            <div className="ag-calib-panel">
              <ul>
                <li>
                  <span>Dérive annualisée retenue (μ)</span>
                  <strong>{(calib.mu_annualise * 100).toFixed(1)} %</strong>
                </li>
                <li>
                  <span>Volatilité annualisée retenue (σ)</span>
                  <strong>{(calib.sigma_annualise * 100).toFixed(1)} %</strong>
                </li>
                <li>
                  <span>Tendance réelle pré-choc seule (μ historique)</span>
                  <strong>{(calib.mu_historique_pre_choc * 100).toFixed(1)} %</strong>
                </li>
                <li>
                  <span>Signal du module de prédiction IA utilisé ?</span>
                  <strong className={calib.prediction_ia_utilisee ? "up" : ""}>
                    {calib.prediction_ia_utilisee ? "Oui" : "Non"}
                  </strong>
                </li>
                {calib.prediction_ia_utilisee && (
                  <>
                    <li>
                      <span>Rendement prédit par le module IA</span>
                      <strong className={cls(calib.rendement_predit_ia)}>{pct(calib.rendement_predit_ia * 100)}</strong>
                    </li>
                    <li>
                      <span>Confiance du module IA</span>
                      <strong>{Math.round(calib.confiance_ia * 100)} %</strong>
                    </li>
                  </>
                )}
              </ul>
              <p className="ag-muted">{calib.note}</p>
            </div>
          )}
        </div>

        <div className="ag-right">
          <div className="ag-ticket">
            <div className="ag-side-tabs">
              <button className={`buy${side === "buy" ? " active" : ""}`} onClick={() => setSide("buy")}>
                Acheter
              </button>
              <button className={`sell${side === "sell" ? " active" : ""}`} onClick={() => setSide("sell")}>
                Vendre
              </button>
            </div>
            <div className="ag-ticket-body">
              <div className="ag-ticket-top">
                <label className="trade-field">
                  Quantité
                  <input value={qty} onChange={(e) => setQty(e.target.value)} inputMode="decimal" placeholder="0" disabled={!active} />
                </label>
                <div className="ag-quick">
                  {[0.25, 0.5, 1].map((f) => (
                    <button key={f} disabled={!active} onClick={() => fill(f)}>
                      {f * 100} %
                    </button>
                  ))}
                </div>
              </div>
              <p className="ag-cost">Montant : {valid ? `${money(cost)} $` : "—"}</p>
              <div className="ag-trade">
                <button className={side} disabled={!active || !valid || busy} onClick={() => act("trade", { side, quantity })}>
                  {side === "buy" ? "Acheter" : "Vendre"}
                </button>
              </div>
              <button className="ag-next" disabled={!active || busy} onClick={() => act("next")}>
                {s.is_last_step ? "Terminer la partie" : "Jour suivant →"}
              </button>
              <p className="ag-muted">Ordres exécutés au cours du jour affiché, sans frais.</p>
            </div>
          </div>
        </div>
      </div>

      {!active && (
        <div className="ag-overlay">
          <div className="ag-result">
            <span className="ag-pill">Partie terminée</span>
            <h2>{s.symbol} · choc IA</h2>
            <div className="ag-score">
              <strong className={cls(s.result.score)}>{s.result.score}</strong>
              <span>points</span>
            </div>
            <ul className="ag-result-list">
              <li>
                <span>Rendement</span>
                <strong className={cls(s.result.return_pct)}>{pct(s.result.return_pct)}</strong>
              </li>
              <li>
                <span>Perte maximale</span>
                <strong className="down">−{String(s.result.max_drawdown_pct).replace(".", ",")} %</strong>
              </li>
            </ul>
            <p className="ag-muted">Score = rendement − (perte maximale ÷ 2)</p>
            <div className="ag-actions">
              <button className="ag-btn" onClick={() => navigate("/salles-de-jeu")}>
                Retour aux salles de jeu
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
