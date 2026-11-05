import { useEffect, useRef, useState } from "react";
import { createChart } from "lightweight-charts";
import { formatDecimal } from "../services/format.js";

const UP = "#3dd68c";
const DOWN = "#ff5d73";
const TEXT = "#8a96ad";
const GRID = "rgba(255, 255, 255, 0.06)";

function baseOptions(height) {
  return {
    autoSize: true,
    height,
    layout: { background: { type: "solid", color: "transparent" }, textColor: TEXT },
    grid: { vertLines: { color: GRID }, horzLines: { color: GRID } },
    rightPriceScale: { borderColor: GRID },
    timeScale: { borderColor: GRID },
    crosshair: { mode: 0 },
  };
}

// Points d'une série d'indicateur, sans les jours où il n'est pas encore défini.
function linePoints(dates, values) {
  return dates.flatMap((time, index) =>
    values[index] === null || values[index] === undefined ? [] : [{ time, value: values[index] }],
  );
}

const fmt = (value) => formatDecimal(Number(value).toFixed(2));

/**
 * Chandeliers japonais + volume + moyennes mobiles, et le RSI dans un second graphique
 * dont l'axe du temps suit le premier (zoom et déplacement synchronisés).
 */
export default function CandleChart({ data }) {
  const priceRef = useRef(null);
  const rsiRef = useRef(null);
  const [hover, setHover] = useState(null);

  useEffect(() => {
    const price = createChart(priceRef.current, baseOptions(380));
    const rsiChart = createChart(rsiRef.current, baseOptions(140));

    const candles = price.addCandlestickSeries({
      upColor: UP,
      downColor: DOWN,
      wickUpColor: UP,
      wickDownColor: DOWN,
      borderVisible: false,
    });
    candles.setData(
      data.dates.map((time, i) => ({
        time,
        open: data.open[i],
        high: data.high[i],
        low: data.low[i],
        close: data.close[i],
      })),
    );

    const volume = price.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "" });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    volume.setData(
      data.dates.map((time, i) => ({
        time,
        value: data.volume[i],
        color: data.close[i] >= data.open[i] ? "rgba(61, 214, 140, 0.35)" : "rgba(255, 93, 115, 0.35)",
      })),
    );

    const short = price.addLineSeries({ color: "#fb923c", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    short.setData(linePoints(data.dates, data.sma_short));
    const long = price.addLineSeries({ color: "#a78bfa", lineWidth: 2, priceLineVisible: false, lastValueVisible: false });
    long.setData(linePoints(data.dates, data.sma_long));

    const strength = rsiChart.addLineSeries({ color: "#5aa6ff", lineWidth: 2, priceLineVisible: false });
    strength.setData(linePoints(data.dates, data.rsi));
    strength.createPriceLine({ price: 70, color: "#64748b", lineStyle: 2, axisLabelVisible: true, title: "" });
    strength.createPriceLine({ price: 30, color: "#64748b", lineStyle: 2, axisLabelVisible: true, title: "" });
    rsiChart.priceScale("right").applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });

    // Les deux graphiques gardent la même fenêtre de temps.
    let syncing = false;
    const link = (from, to) =>
      from.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (syncing || !range) return;
        syncing = true;
        to.timeScale().setVisibleLogicalRange(range);
        syncing = false;
      });
    link(price, rsiChart);
    link(rsiChart, price);

    // Prix du jour survolé.
    price.subscribeCrosshairMove((param) => {
      const bar = param.seriesData?.get(candles);
      setHover(bar ? { date: param.time, ...bar } : null);
    });

    price.timeScale().fitContent();
    return () => {
      price.remove();
      rsiChart.remove();
    };
  }, [data]);

  const last = data.dates.length - 1;
  const shown = hover || {
    date: data.dates[last],
    open: data.open[last],
    high: data.high[last],
    low: data.low[last],
    close: data.close[last],
  };
  const change = shown.open ? ((shown.close / shown.open - 1) * 100).toFixed(2) : null;
  const direction = shown.close >= shown.open ? "up" : "down";

  return (
    <div className="candle-chart">
      <p className="ohlc">
        <span>{String(shown.date)}</span>
        <span>O <b>{fmt(shown.open)}</b></span>
        <span>H <b>{fmt(shown.high)}</b></span>
        <span>L <b>{fmt(shown.low)}</b></span>
        <span>C <b className={direction}>{fmt(shown.close)}</b></span>
        {change !== null && <span className={direction}>{change > 0 ? "+" : ""}{change.replace(".", ",")} %</span>}
      </p>
      <div ref={priceRef} className="chart-box" />
      <h3 className="sub">RSI</h3>
      <div ref={rsiRef} className="chart-box" />
    </div>
  );
}
