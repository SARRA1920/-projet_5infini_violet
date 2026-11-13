import { useEffect, useState } from "react";
import { CorrelationHeatmap, FrontierChart, SourceBadge } from "../../components/actuarial/ActuarialCharts.jsx";
import { Conventions, Field, Kpi, Panel, Status } from "../../components/actuarial/Controls.jsx";
import useActuarialRefs from "../../hooks/useActuarialRefs.js";
import { PERIODS, fmtAmount, fmtNum, fmtPct, fmtRatio, percentToFraction, postActuarial } from "../../services/actuarial.js";

const ALLOCATIONS = [
  { key: "current", label: "Actuelle", color: "#f5b94a" },
  { key: "min_variance", label: "Variance minimale", color: "#3dd68c" },
  { key: "max_sharpe", label: "Sharpe maximal", color: "#ff5d73" },
  { key: "target_return", label: "Rendement cible", color: "#c084fc" },
];

const CONVENTIONS = [
  "Rendements espérés μ = moyenne des rendements quotidiens × 252 ; covariance Σ = covariance quotidienne × 252 (historique de la période choisie).",
  "Variance minimale : min wᵀΣw. Sharpe maximal : max (wᵀμ − rf)/√(wᵀΣw). Rendement cible : min wᵀΣw sous wᵀμ = cible.",
  "Contraintes : somme des poids = 100 %, poids entre 0 et le maximum (positions longues) ; vente à découvert possible en simulation théorique (poids ≥ −maximum).",
  "Frontière efficiente : portefeuilles de variance minimale pour des rendements cibles allant du portefeuille de variance minimale au rendement maximal atteignable.",
  "Poids calculés sur la partie investie, hors liquidités. L'allocation actuelle est celle des positions valorisées.",
  "μ et Σ historiques servent d'estimation du futur : les poids optimaux y sont très sensibles. Exercice pédagogique, pas une recommandation.",
  "Les quantités cibles sont indicatives : ce module ne passe jamais d'ordre.",
];

export default function OptimizationPage() {
  const { portfolios, assetsWithHistory } = useActuarialRefs();
  const [form, setForm] = useState({
    portfolio_id: "",
    lookback: 252,
    risk_free: "0",
    max_weight: "40",
    allow_short: false,
    target: "",
    points: 25,
  });
  const [extras, setExtras] = useState(["SPY", "EWJ", "HYG"]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!form.portfolio_id && portfolios.length) setForm((f) => ({ ...f, portfolio_id: portfolios[0].id }));
  }, [portfolios, form.portfolio_id]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));
  const toggle = (symbol) => setExtras((list) => (list.includes(symbol) ? list.filter((s) => s !== symbol) : [...list, symbol]));

  const run = () => {
    setLoading(true);
    setError("");
    postActuarial("/optimization/markowitz", {
      portfolio_id: form.portfolio_id || null,
      extra_symbols: extras,
      lookback: Number(form.lookback),
      risk_free_rate: percentToFraction(form.risk_free) ?? 0,
      max_weight: percentToFraction(form.max_weight) ?? 1,
      allow_short: form.allow_short,
      target_return: percentToFraction(form.target),
      frontier_points: Number(form.points),
    })
      .then(setData)
      .catch((err) => {
        setData(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  };

  const allocations = data
    ? ALLOCATIONS.map((a) => ({ ...a, value: a.key === "current" ? data.current : data.optimized[a.key] })).filter((a) => a.value)
    : [];

  return (
    <>
      <article className="panel">
        <div className="act-filters">
          <Field label="Portefeuille">
            <select value={form.portfolio_id} onChange={set("portfolio_id")}>
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Période d'estimation">
            <select value={form.lookback} onChange={set("lookback")}>
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Taux sans risque (%)">
            <input value={form.risk_free} onChange={set("risk_free")} inputMode="decimal" />
          </Field>
          <Field label="Pondération maximale par actif (%)">
            <input value={form.max_weight} onChange={set("max_weight")} inputMode="decimal" />
          </Field>
          <Field label="Rendement cible (%, facultatif)">
            <input value={form.target} onChange={set("target")} inputMode="decimal" />
          </Field>
          <Field label="Points de la frontière">
            <input value={form.points} onChange={set("points")} inputMode="numeric" />
          </Field>
        </div>
        <label className="act-check">
          <input type="checkbox" checked={form.allow_short} onChange={set("allow_short")} />
          Autoriser la vente à découvert (simulation théorique uniquement)
        </label>
        <p className="act-note">Actifs ajoutés à l'univers, en plus des positions détenues :</p>
        <div className="act-chips">
          {assetsWithHistory.map((a) => (
            <button key={a.symbol} type="button" className={extras.includes(a.symbol) ? "active" : ""} onClick={() => toggle(a.symbol)} title={a.name}>
              {a.symbol}
            </button>
          ))}
        </div>
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={run} disabled={loading || !form.portfolio_id}>
            {loading ? "Optimisation…" : "Optimiser"}
          </button>
          {data && (
            <span className="act-meta">
              <SourceBadge source={data.data_source} />
              {data.observations} jours, du {data.period_start} au {data.period_end}
            </span>
          )}
        </div>
      </article>

      <Status loading={loading && !data} error={error} warnings={data?.warnings} />

      {data && (
        <div className={loading ? "act-results act-stale" : "act-results"}>
          <p className="banner act-info">
            Résultats théoriques : aucun ordre n'est passé. Pour modifier votre portefeuille, utilisez l'écran Trading.
          </p>
          <div className="stat-grid act-kpis">
            {allocations.map((a) => (
              <Kpi
                key={a.key}
                label={a.label}
                value={`${fmtPct(a.value.expected_return)} / an`}
                note={`volatilité ${fmtPct(a.value.volatility)} · Sharpe ${fmtRatio(a.value.sharpe_ratio)}`}
              />
            ))}
          </div>

          <div className="act-grid">
            <Panel title="Frontière efficiente" subtitle={`${data.frontier.length} portefeuilles efficients.`}>
              <FrontierChart
                frontier={data.frontier}
                points={allocations.map((a) => ({ name: a.label, color: a.color, ...a.value }))}
              />
            </Panel>
            <Panel title="Corrélations de l'univers">
              <CorrelationHeatmap symbols={data.correlation.symbols} matrix={data.correlation.matrix} />
            </Panel>
          </div>

          <Panel title="Allocations comparées" subtitle="Poids de chaque actif dans la partie investie.">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Actif</th>
                    <th>Rendement espéré</th>
                    <th>Volatilité</th>
                    {allocations.map((a) => (
                      <th key={a.key}>{a.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.symbols.map((symbol, i) => (
                    <tr key={symbol}>
                      <td><strong>{symbol}</strong></td>
                      <td className={data.assets[i].expected_return >= 0 ? "up" : "down"}>{fmtPct(data.assets[i].expected_return)}</td>
                      <td>{fmtPct(data.assets[i].volatility)}</td>
                      {allocations.map((a) => (
                        <td key={a.key}>
                          <div className="act-weight">
                            <span style={{ width: `${Math.min(100, Math.abs(a.value.weights[i]) * 100)}%`, background: a.color }} />
                            {fmtPct(a.value.weights[i])}
                          </div>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel
            title="Rééquilibrage indicatif vers le Sharpe maximal"
            subtitle={`Sur un montant investi de ${fmtAmount(data.notional)}, aux derniers cours connus.`}
          >
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Actif</th>
                    <th>Cours</th>
                    <th>Quantité actuelle</th>
                    <th>Valeur cible</th>
                    <th>Quantité cible</th>
                    <th>Écart</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rebalance.map((r) => (
                    <tr key={r.symbol}>
                      <td><strong>{r.symbol}</strong></td>
                      <td>{fmtAmount(r.price)}</td>
                      <td>{fmtNum(r.current_quantity, 2)}</td>
                      <td>{fmtAmount(r.target_value)}</td>
                      <td>{fmtNum(r.target_quantity, 2)}</td>
                      <td className={r.quantity_change > 0 ? "up" : r.quantity_change < 0 ? "down" : ""}>
                        {r.quantity_change > 0 ? "+" : ""}
                        {fmtNum(r.quantity_change, 2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Conventions items={CONVENTIONS} />
        </div>
      )}
    </>
  );
}
