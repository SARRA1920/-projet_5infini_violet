// Graphiques du module Actuariat (recharts), au thème sombre de l'application.
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ASSET_CLASS_COLORS, ASSET_CLASS_LABELS, DATA_SOURCE_LABELS, fmtAmount, fmtPct } from "../../services/actuarial.js";

const AXIS = { fill: "#93a0b5", fontSize: 12 };
const GRID = "rgba(255, 255, 255, 0.06)";
const TOOLTIP = {
  contentStyle: { background: "#121a2b", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 10 },
  labelStyle: { color: "#e8eef8" },
  itemStyle: { color: "#e8eef8" },
};
const GAIN = "#3dd68c";
const LOSS = "#ff5d73";

export function SourceBadge({ source }) {
  return <span className={`act-badge act-badge-${source}`}>{DATA_SOURCE_LABELS[source] || source}</span>;
}

export function ValueCurveChart({ points }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={points} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="act-value" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8eb7ff" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#8eb7ff" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} minTickGap={40} />
        <YAxis tick={AXIS} domain={["auto", "auto"]} width={72} tickFormatter={(v) => fmtAmount(v).split(",")[0]} />
        <Tooltip {...TOOLTIP} formatter={(v) => [fmtAmount(v), "Valeur"]} />
        <Area type="monotone" dataKey="value" stroke="#8eb7ff" strokeWidth={2} fill="url(#act-value)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// Histogramme à partir de classes {from, to, count} ; `colorOf(bin)` choisit la couleur de chaque barre.
// `axisFormat` : libellés courts sur l'axe (montants élevés) ; `format` reste utilisé dans l'infobulle.
export function BinsHistogram({ bins, format = fmtPct, axisFormat, unit = "Observations", colorOf, height = 240 }) {
  const data = bins.map((bin) => ({ ...bin, label: (axisFormat || format)((bin.from + bin.to) / 2) }));
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap={1}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={AXIS} interval={Math.max(0, Math.ceil(bins.length / 6) - 1)} />
        <YAxis tick={AXIS} allowDecimals={false} width={44} />
        <Tooltip
          {...TOOLTIP}
          formatter={(v) => [v, unit]}
          labelFormatter={(_, payload) => {
            const bin = payload?.[0]?.payload;
            return bin ? `${format(bin.from)} à ${format(bin.to)}` : "";
          }}
        />
        <Bar dataKey="count">
          {data.map((bin) => (
            <Cell key={bin.from} fill={colorOf ? colorOf(bin) : "#8eb7ff"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// Histogramme des rendements quotidiens ; les classes au-delà de la VaR à 1 jour sont en rouge.
export function ReturnHistogram({ returns, var1d, bins = 30 }) {
  const values = returns.map((r) => r.value);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const width = (max - min) / bins || 1;
  const counts = Array.from({ length: bins }, (_, i) => ({ from: min + i * width, to: min + (i + 1) * width, count: 0 }));
  values.forEach((v) => {
    counts[Math.min(bins - 1, Math.floor((v - min) / width))].count += 1;
  });
  return <BinsHistogram bins={counts} unit="Jours" colorOf={(bin) => lossColor(bin, var1d)} />;
}

// Rouge au-delà de la VaR (pertes), vert pour les gains, bleu entre les deux.
export function lossColor(bin, varLevel) {
  if (varLevel != null && bin.to <= -varLevel) return LOSS;
  return bin.from >= 0 ? GAIN : "#8eb7ff";
}

// Carte de chaleur des corrélations : bleu = corrélation positive, rouge = négative.
export function CorrelationHeatmap({ symbols, matrix }) {
  const color = (value) => {
    const alpha = Math.min(1, Math.abs(value)) * 0.85 + 0.05;
    return value >= 0 ? `rgba(142, 183, 255, ${alpha})` : `rgba(255, 93, 115, ${alpha})`;
  };
  return (
    <div className="table-scroll">
      <table className="act-heatmap">
        <thead>
          <tr>
            <th />
            {symbols.map((s) => (
              <th key={s}>{s}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={symbols[i]}>
              <th>{symbols[i]}</th>
              {row.map((value, j) => (
                <td key={symbols[j]} style={{ background: color(value) }} title={`${symbols[i]} / ${symbols[j]}`}>
                  {value.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// Éventail des trajectoires : bandes 5-95 % et 25-75 %, moyenne, quelques trajectoires individuelles.
export function FanChart({ fan, paths = [], format = fmtAmount, xLabel = "années" }) {
  const data = fan.map((point, k) => ({
    t: point.t,
    outer: [point.p05, point.p95],
    inner: [point.p25, point.p75],
    median: point.p50,
    mean: point.mean,
    ...Object.fromEntries(paths.map((path, i) => [`path${i}`, path[k]])),
  }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="t" type="number" domain={["dataMin", "dataMax"]} tick={AXIS}
               tickFormatter={(v) => `${v.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}`}
               label={{ value: xLabel, position: "insideBottomRight", offset: -2, fill: "#6f7d92", fontSize: 11 }} />
        <YAxis tick={AXIS} width={72} domain={["auto", "auto"]} tickFormatter={format} />
        <Tooltip
          {...TOOLTIP}
          labelFormatter={(v) => `t = ${Number(v).toLocaleString("fr-FR", { maximumFractionDigits: 3 })} ${xLabel}`}
          formatter={(value, name) => {
            if (Array.isArray(value)) return [`${format(value[0])} – ${format(value[1])}`, name];
            return [format(value), name];
          }}
        />
        <Area dataKey="outer" name="5 % – 95 %" stroke="none" fill="#8eb7ff" fillOpacity={0.15} isAnimationActive={false} />
        <Area dataKey="inner" name="25 % – 75 %" stroke="none" fill="#8eb7ff" fillOpacity={0.3} isAnimationActive={false} />
        {paths.map((_, i) => (
          <Line key={i} dataKey={`path${i}`} stroke="rgba(232, 238, 248, 0.25)" dot={false} strokeWidth={1}
                isAnimationActive={false} legendType="none" name={`Trajectoire ${i + 1}`} tooltipType="none" />
        ))}
        <Line dataKey="median" name="Médiane" stroke="#f5b94a" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Line dataKey="mean" name="Moyenne" stroke="#3dd68c" dot={false} strokeWidth={2} strokeDasharray="5 4"
              isAnimationActive={false} />
        <Legend wrapperStyle={{ color: "#93a0b5", fontSize: 12 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

// Frontière efficiente (volatilité, rendement) et portefeuilles remarquables.
export function FrontierChart({ frontier, points }) {
  const line = frontier.map((p) => ({ x: p.volatility, y: p.expected_return }));
  return (
    <ResponsiveContainer width="100%" height={300}>
      <ScatterChart margin={{ top: 8, right: 16, left: 8, bottom: 8 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis type="number" dataKey="x" name="Volatilité" tick={AXIS} tickFormatter={fmtPct} domain={["auto", "auto"]}
               label={{ value: "Volatilité annualisée", position: "insideBottom", offset: -4, fill: "#6f7d92", fontSize: 11 }} />
        <YAxis type="number" dataKey="y" name="Rendement" tick={AXIS} tickFormatter={fmtPct} width={64} domain={["auto", "auto"]} />
        <Tooltip {...TOOLTIP} formatter={(value, name) => [fmtPct(value), name]} />
        <Scatter name="Frontière efficiente" data={line} line={{ stroke: "#8eb7ff", strokeWidth: 2 }} fill="#8eb7ff"
                 shape={() => null} isAnimationActive={false} />
        {points.map((p) => (
          <Scatter key={p.name} name={p.name} data={[{ x: p.volatility, y: p.expected_return }]} fill={p.color}
                   isAnimationActive={false} />
        ))}
        <Legend wrapperStyle={{ color: "#93a0b5", fontSize: 12, paddingTop: 8 }} />
      </ScatterChart>
    </ResponsiveContainer>
  );
}

// Backtesting : pertes quotidiennes (barres) et VaR prévue la veille (ligne) ; exceptions en rouge.
export function BacktestChart({ series }) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} minTickGap={40} />
        <YAxis tick={AXIS} width={60} tickFormatter={fmtPct} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [fmtPct(v), name]} />
        <Bar dataKey="loss" name="Perte du jour" isAnimationActive={false}>
          {series.map((p) => (
            <Cell key={p.date} fill={p.hit ? LOSS : p.loss > 0 ? "#3b4a66" : "#24324a"} />
          ))}
        </Bar>
        <Line dataKey="var" name="VaR prévue" stroke="#f5b94a" dot={false} strokeWidth={2} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function SimpleLineChart({ data, x, y, xFormat, yFormat, name, marker }) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={x} type="number" domain={["dataMin", "dataMax"]} tick={AXIS} tickFormatter={xFormat} />
        <YAxis tick={AXIS} width={64} domain={["auto", "auto"]} tickFormatter={yFormat} />
        <Tooltip {...TOOLTIP} labelFormatter={xFormat} formatter={(v) => [yFormat(v), name]} />
        {marker != null && <ReferenceLine x={marker} stroke="#f5b94a" strokeDasharray="4 4" />}
        <Line dataKey={y} name={name} stroke="#8eb7ff" dot={false} strokeWidth={2} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function CashFlowChart({ flows }) {
  const data = flows.map((f) => ({ date: f.date, coupon: f.coupon, principal: f.principal, pv: f.present_value }));
  return (
    <ResponsiveContainer width="100%" height={240}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey="date" tick={AXIS} minTickGap={30} />
        <YAxis tick={AXIS} width={64} tickFormatter={(v) => fmtAmount(v).split(",")[0]} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [fmtAmount(v), name]} />
        <Bar dataKey="coupon" stackId="cf" name="Coupon" fill="#8eb7ff" isAnimationActive={false} />
        <Bar dataKey="principal" stackId="cf" name="Remboursement" fill="#3dd68c" isAnimationActive={false} />
        <Line dataKey="pv" name="Valeur actuelle" stroke="#f5b94a" dot={false} strokeWidth={2} isAnimationActive={false} />
        <Legend wrapperStyle={{ color: "#93a0b5", fontSize: 12 }} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

export function ExposureBars({ rows }) {
  return (
    <ul className="act-bars">
      {rows.map((row) => (
        <li key={row.asset_class}>
          <div className="act-bar-label">
            <span>{ASSET_CLASS_LABELS[row.asset_class] || row.asset_class}</span>
            <strong>{fmtPct(row.weight)}</strong>
          </div>
          <div className="act-bar-track">
            <div
              className="act-bar-fill"
              style={{ width: `${Math.max(0, row.weight) * 100}%`, background: ASSET_CLASS_COLORS[row.asset_class] || "#8eb7ff" }}
            />
          </div>
          <em>{fmtAmount(row.value)}</em>
        </li>
      ))}
    </ul>
  );
}

export function RiskShareChart({ rows }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(120, rows.length * 38)}>
      <BarChart data={rows} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid stroke={GRID} horizontal={false} />
        <XAxis type="number" tick={AXIS} tickFormatter={fmtPct} />
        <YAxis type="category" dataKey="symbol" tick={AXIS} width={72} />
        <Tooltip {...TOOLTIP} formatter={(v, name) => [fmtPct(v), name === "risk_share" ? "Part du risque" : "Poids"]} />
        <Bar dataKey="weight" fill="#3b4a66" name="weight" />
        <Bar dataKey="risk_share" fill="#8eb7ff" name="risk_share" />
      </BarChart>
    </ResponsiveContainer>
  );
}
