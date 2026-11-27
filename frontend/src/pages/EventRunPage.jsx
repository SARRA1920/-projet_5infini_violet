import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { createChart } from "lightweight-charts";
import { api } from "../services/api.js";
import "./arcade.css";

const money = (n) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pct = (n) => `${n > 0 ? "+" : ""}${Number(n).toFixed(2).replace(".", ",")} %`;
const cls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");

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
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
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
      if (bar) setHover({ time: param.time, ...bar });
    });

    return () => chart.remove();
  }, []);

  useEffect(() => {
    candleRef.current.setData(history);
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
      <div className="ag-chart-legend">
        {shown && (
          <>
            <span>O {money(shown.open)}</span>
            <span>H {money(shown.high)}</span>
            <span>L {money(shown.low)}</span>
            <strong className={shown.close >= shown.open ? "up" : "down"}>C {money(shown.close)}</strong>
          </>
        )}
        <span className="ag-ma ma5">MA5</span>
        <span className="ag-ma ma10">MA10</span>
        <span className="ag-ma ma20">MA20</span>
      </div>
      <div ref={ref} className="ag-chart" />
    </div>
  );
}

export default function EventRunPage() {
  const { runId } = useParams();
  const navigate = useNavigate();
  const [s, setS] = useState(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState(null);
  const [side, setSide] = useState("buy");
  const [qty, setQty] = useState("");
  const [busy, setBusy] = useState(false);

  const apply = useCallback((state) => {
    setS(state);
    setSelected((cur) => cur || state.assets[0]?.symbol);
  }, []);

  useEffect(() => {
    api(`/salles-de-jeu/event-runs/${runId}`).then(apply).catch((err) => setError(err.message));
  }, [runId, apply]);

  async function act(path, body) {
    setBusy(true);
    setError("");
    try {
      const next = await api(`/salles-de-jeu/event-runs/${runId}/${path}`, {
        method: "POST",
        body: body ? JSON.stringify(body) : undefined,
      });
      apply(next);
      if (path === "trade") setQty("");
    } catch (err) {
      setError(err.message);
      api(`/salles-de-jeu/event-runs/${runId}`).then(apply).catch(() => {});
    } finally {
      setBusy(false);
    }
  }

  async function closeSession() {
    if (!window.confirm("Fermer cette session sans la finaliser ? Ta progression ne sera pas comptée.")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/salles-de-jeu/event-runs/${runId}/close`, { method: "POST" });
      navigate("/salles-de-jeu");
    } catch (err) {
      setError(err.message);
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

  function fill(fraction) {
    if (!asset.price) return;
    const max = side === "buy" ? s.cash / asset.price : asset.quantity;
    setQty(String(Math.floor(max * fraction * 10000) / 10000));
  }

  return (
    <section className="page ag ag-play">
      <header className="ag-bar">
        <div>
          <p className="ag-day">Salle de jeu · {s.event.name}</p>
          <h1>{new Date(s.date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}</h1>
          <p className="ag-day">Jour {s.day} / {s.total_days}</p>
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
          <strong>Contexte.</strong> {s.event.story}
        </div>
      )}
      {error && <p className="status error">{error}</p>}

      <div className="ag-layout">
        <div className="ag-left">
          <div className="ag-watchlist">
            <h2>Actifs</h2>
            <ul className="ag-assets">
              {s.assets.map((a) => (
                <li key={a.symbol} className={a.symbol === asset.symbol ? "active" : ""} onClick={() => setSelected(a.symbol)}>
                  <span>
                    <strong>{a.name}</strong>
                    <small>{a.symbol}</small>
                  </span>
                  <span className="ag-assets-price">
                    {a.price ? money(a.price) : "—"}
                    {a.change_pct !== null && <em className={cls(a.change_pct)}>{pct(a.change_pct)}</em>}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="ag-center">
          <div className="ag-asset-head">
            <h2>
              {asset.name} <small>{asset.symbol}</small>
            </h2>
            <div>
              <strong>{asset.price ? money(asset.price) : "—"}</strong>{" "}
              {asset.change_pct !== null && <span className={cls(asset.change_pct)}>{pct(asset.change_pct)}</span>}
            </div>
          </div>
          <CandleChart history={asset.history} />
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
                <button
                  className={side}
                  disabled={!active || !valid || busy}
                  onClick={() => act("trade", { symbol: asset.symbol, side, quantity })}
                >
                  {side === "buy" ? "Acheter" : "Vendre"}
                </button>
              </div>
              <button className="ag-next" disabled={!active || busy} onClick={() => act("next")}>
                {s.is_last_day ? "Terminer la partie" : "Jour suivant →"}
              </button>
              <p className="ag-muted">Ordres exécutés au cours de clôture du jour, sans frais.</p>
            </div>
          </div>
        </div>
      </div>

      {!active && (
        <div className="ag-overlay">
          <div className="ag-result">
            <span className="ag-pill">Partie terminée</span>
            <h2>{s.event.name}</h2>
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
