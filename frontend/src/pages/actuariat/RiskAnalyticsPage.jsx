import { useEffect, useState } from "react";
import {
  BacktestChart,
  BinsHistogram,
  CorrelationHeatmap,
  RiskShareChart,
  SourceBadge,
  lossColor,
} from "../../components/actuarial/ActuarialCharts.jsx";
import { Conventions, Field, Kpi, Panel, Status } from "../../components/actuarial/Controls.jsx";
import useActuarialRefs from "../../hooks/useActuarialRefs.js";
import {
  METHOD_LABELS,
  PERIODS,
  actuarialApi,
  fmtAmount,
  fmtNum,
  fmtPct,
  fmtRatio,
  parseNumber,
  percentToFraction,
  postActuarial,
} from "../../services/actuarial.js";

const METHODS = ["historical", "parametric", "monte_carlo"];

const CONVENTIONS = [
  "Rendements simples quotidiens sur les dates communes aux actifs ; composition actuelle supposée constante.",
  "Perte = −rendement. VaR = quantile empirique des pertes (méthode inverted_cdf, sans interpolation).",
  "Historique : VaR et ES à 1 jour × √horizon (rendements supposés indépendants et de même loi).",
  "Paramétrique : loi normale, VaR = −μh + z·σ√h ; ES = −μh + σ√h·φ(z)/(1−α).",
  "Monte Carlo : rendements log multinormaux N(μh, Σh) estimés sur l'historique, puis composés ; graine fixe = résultat reproductible.",
  "Expected Shortfall = perte moyenne au-delà de la VaR ; toujours ≥ VaR.",
  "Backtesting : VaR historique à 1 jour recalculée chaque jour sur une fenêtre glissante, test de Kupiec au seuil de 5 %.",
  "Contributions : σp = √(wᵀΣw), contribution marginale (Σw)ᵢ/σp, contribution wᵢ × marginale, annualisées (× √252).",
];

export default function RiskAnalyticsPage() {
  const { portfolios, assetsWithHistory } = useActuarialRefs();
  const [mode, setMode] = useState("portfolio");
  const [form, setForm] = useState({
    portfolio_id: "",
    lookback: 252,
    confidence: 0.95,
    horizon: 1,
    n_simulations: 10000,
    seed: "42",
    backtest_window: "100",
    risk_free: "0",
    notional: "100000",
  });
  const [basket, setBasket] = useState([{ symbol: "SPY", weight: "60" }, { symbol: "TLT", weight: "40" }]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!form.portfolio_id && portfolios.length) setForm((f) => ({ ...f, portfolio_id: portfolios[0].id }));
  }, [portfolios, form.portfolio_id]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const run = () => {
    const common = {
      lookback: Number(form.lookback),
      confidence: Number(form.confidence),
      horizon: Number(form.horizon),
      n_simulations: Number(form.n_simulations),
      seed: parseNumber(form.seed),
      risk_free_rate: percentToFraction(form.risk_free) ?? 0,
      backtest_window: parseNumber(form.backtest_window) ?? 100,
    };
    if (common.seed === null) delete common.seed;
    setLoading(true);
    setError("");
    const request =
      mode === "portfolio"
        ? actuarialApi(`/portfolio-risk/${form.portfolio_id}`, common)
        : postActuarial("/risk/var", {
            ...common,
            symbols: basket.map((row) => row.symbol),
            weights: basket.map((row) => parseNumber(row.weight) ?? 0),
            notional: parseNumber(form.notional) ?? 100000,
          });
    request
      .then(setData)
      .catch((err) => {
        setData(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (mode === "portfolio" && form.portfolio_id) run();
    // Calcul automatique au choix du portefeuille ; les autres réglages attendent « Calculer ».
  }, [form.portfolio_id]);

  const selected = (data?.var_table || []).filter(
    (r) => r.confidence === data.confidence && r.horizon_days === data.horizon_days,
  );
  const byMethod = Object.fromEntries(selected.map((r) => [r.method, r]));
  const conf = data ? `${Math.round(data.confidence * 100)} %` : "";
  const grid = [0.95, 0.99].flatMap((c) =>
    [1, 10, 20].map((h) => ({
      key: `${c}-${h}`,
      confidence: c,
      horizon: h,
      rows: Object.fromEntries(
        (data?.var_table || []).filter((r) => r.confidence === c && r.horizon_days === h).map((r) => [r.method, r]),
      ),
    })),
  );
  const mcVar = byMethod.monte_carlo?.var;

  return (
    <>
      <article className="panel">
        <div className="act-segmented" role="tablist">
          <button type="button" className={mode === "portfolio" ? "active" : ""} onClick={() => setMode("portfolio")}>
            Mon portefeuille
          </button>
          <button type="button" className={mode === "basket" ? "active" : ""} onClick={() => setMode("basket")}>
            Panier libre
          </button>
        </div>

        {mode === "basket" && (
          <div className="act-basket">
            {basket.map((row, i) => (
              <div key={i} className="act-basket-row">
                <select
                  value={row.symbol}
                  onChange={(e) => setBasket((b) => b.map((r, j) => (j === i ? { ...r, symbol: e.target.value } : r)))}
                >
                  {assetsWithHistory.map((a) => (
                    <option key={a.symbol} value={a.symbol}>
                      {a.symbol} — {a.name}
                    </option>
                  ))}
                </select>
                <input
                  value={row.weight}
                  inputMode="decimal"
                  aria-label="Poids"
                  onChange={(e) => setBasket((b) => b.map((r, j) => (j === i ? { ...r, weight: e.target.value } : r)))}
                />
                <button type="button" className="act-icon-btn" onClick={() => setBasket((b) => b.filter((_, j) => j !== i))}
                        disabled={basket.length === 1} aria-label="Retirer">
                  ×
                </button>
              </div>
            ))}
            <button
              type="button"
              className="act-link-btn"
              onClick={() => setBasket((b) => [...b, { symbol: assetsWithHistory[0]?.symbol || "SPY", weight: "10" }])}
              disabled={basket.length >= 20}
            >
              + Ajouter un actif
            </button>
            <p className="act-note">Poids relatifs, normalisés à 100 %. Panier fictif : aucun ordre n'est passé.</p>
          </div>
        )}

        <div className="act-filters">
          {mode === "portfolio" ? (
            <Field label="Portefeuille">
              <select value={form.portfolio_id} onChange={set("portfolio_id")}>
                {portfolios.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </Field>
          ) : (
            <Field label="Montant exposé">
              <input value={form.notional} onChange={set("notional")} inputMode="decimal" />
            </Field>
          )}
          <Field label="Période historique">
            <select value={form.lookback} onChange={set("lookback")}>
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field label="Niveau de confiance">
            <select value={form.confidence} onChange={set("confidence")}>
              <option value={0.95}>95 %</option>
              <option value={0.99}>99 %</option>
            </select>
          </Field>
          <Field label="Horizon">
            <select value={form.horizon} onChange={set("horizon")}>
              <option value={1}>1 jour</option>
              <option value={10}>10 jours</option>
              <option value={20}>20 jours</option>
            </select>
          </Field>
          <Field label="Simulations Monte Carlo">
            <select value={form.n_simulations} onChange={set("n_simulations")}>
              <option value={1000}>1 000</option>
              <option value={10000}>10 000</option>
              <option value={50000}>50 000</option>
            </select>
          </Field>
          <Field label="Graine aléatoire" hint="vide = tirage non reproductible">
            <input value={form.seed} onChange={set("seed")} inputMode="numeric" />
          </Field>
          <Field label="Fenêtre de backtest (jours)">
            <input value={form.backtest_window} onChange={set("backtest_window")} inputMode="numeric" />
          </Field>
          <Field label="Taux sans risque (%)">
            <input value={form.risk_free} onChange={set("risk_free")} inputMode="decimal" />
          </Field>
        </div>
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={run} disabled={loading || (mode === "portfolio" && !form.portfolio_id)}>
            {loading ? "Calcul…" : "Calculer"}
          </button>
          {data && (
            <span className="act-meta">
              <SourceBadge source={data.data_source} />
              <SourceBadge source="simulated" />
              {data.observations} jours, du {data.period_start} au {data.period_end}
            </span>
          )}
        </div>
      </article>

      <Status loading={loading && !data} error={error} warnings={data?.warnings} />

      {data && (
        <div className={loading ? "act-results act-stale" : "act-results"}>
          <div className="stat-grid act-kpis act-kpis-3">
            {METHODS.map((m) => (
              <Kpi
                key={m}
                label={`${METHOD_LABELS[m]} · VaR ${conf} · ${data.horizon_days} j`}
                value={fmtPct(byMethod[m]?.var)}
                note={`${fmtAmount(byMethod[m]?.var_amount)} · ES ${fmtPct(byMethod[m]?.expected_shortfall)} (${fmtAmount(byMethod[m]?.expected_shortfall_amount)})`}
              />
            ))}
          </div>
          <div className="stat-grid act-kpis">
            <Kpi label="Volatilité annualisée" value={fmtPct(data.metrics.annualized_volatility)} note={`rendement annualisé ${fmtPct(data.metrics.annualized_return)}`} />
            <Kpi label="Drawdown maximal" value={fmtPct(data.metrics.max_drawdown)} tone="down" note="pire chute depuis un sommet" />
            <Kpi label="Sharpe Ratio" value={fmtRatio(data.metrics.sharpe_ratio)} note="annualisé" />
            <Kpi label="Sortino Ratio" value={fmtRatio(data.metrics.sortino_ratio)} note="risque baissier seul" />
          </div>

          <div className="act-grid">
            <Panel title="VaR et Expected Shortfall : toutes les combinaisons" subtitle={`Valeur exposée : ${fmtAmount(data.total_value)}`}>
              <div className="table-scroll">
                <table className="data-table act-table">
                  <thead>
                    <tr>
                      <th>Confiance · horizon</th>
                      {METHODS.map((m) => (
                        <th key={m}>{METHOD_LABELS[m]}<br /><span>VaR / ES</span></th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {grid.map((g) => (
                      <tr key={g.key} className={g.confidence === data.confidence && g.horizon === data.horizon_days ? "act-row-selected" : ""}>
                        <td><strong>{Math.round(g.confidence * 100)} % · {g.horizon} j</strong></td>
                        {METHODS.map((m) => (
                          <td key={m}>
                            {fmtPct(g.rows[m]?.var)} <span>/ {fmtPct(g.rows[m]?.expected_shortfall)}</span>
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
            <Panel
              title="Distribution Monte Carlo"
              subtitle={`${data.n_simulations.toLocaleString("fr-FR")} rendements simulés à ${data.horizon_days} j${data.seed != null ? `, graine ${data.seed}` : ""} ; en rouge au-delà de la VaR.`}
              source="simulated"
            >
              <BinsHistogram bins={data.monte_carlo_distribution} unit="Simulations" colorOf={(bin) => lossColor(bin, mcVar)} />
            </Panel>
          </div>

          <div className="act-grid">
            <Panel title="Matrice de corrélation" subtitle="Rendements quotidiens sur la période.">
              <CorrelationHeatmap symbols={data.correlation.symbols} matrix={data.correlation.matrix} />
            </Panel>
            <Panel title="Contribution au risque" subtitle="Poids (gris) et part de la volatilité (bleu).">
              <RiskShareChart rows={data.risk_contributions} />
            </Panel>
          </div>

          <Panel title="Risque par actif" subtitle={`VaR historique ${conf} à 1 jour de chaque actif pris isolément.`}>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Actif</th>
                    <th>Poids</th>
                    <th>Rendement annualisé</th>
                    <th>Volatilité</th>
                    <th>VaR 1 j</th>
                    <th>Drawdown max</th>
                    <th>Contrib. marginale</th>
                    <th>Part du risque</th>
                  </tr>
                </thead>
                <tbody>
                  {data.assets.map((a) => {
                    const rc = data.risk_contributions.find((r) => r.symbol === a.symbol);
                    return (
                      <tr key={a.symbol}>
                        <td><strong>{a.symbol}</strong></td>
                        <td>{fmtPct(a.weight)}</td>
                        <td className={a.annualized_return >= 0 ? "up" : "down"}>{fmtPct(a.annualized_return)}</td>
                        <td>{fmtPct(a.annualized_volatility)}</td>
                        <td>{fmtPct(a.var_1d)}</td>
                        <td>{fmtPct(a.max_drawdown)}</td>
                        <td>{fmtPct(rc?.marginal_contribution)}</td>
                        <td>{fmtPct(rc?.risk_share)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Panel>

          {data.backtest && (
            <Panel
              title="Backtesting de la VaR historique à 1 jour"
              subtitle={`Fenêtre glissante de ${data.backtest.window} jours, ${data.backtest.observations} jours testés.`}
            >
              <div className="act-inline-stats">
                <span>Exceptions : <strong>{data.backtest.exceptions}</strong> (attendues : {fmtNum(data.backtest.expected_exceptions, 1)})</span>
                <span>Taux : <strong>{fmtPct(data.backtest.exception_rate)}</strong></span>
                <span>LR Kupiec : <strong>{fmtNum(data.backtest.lr_statistic, 3)}</strong></span>
                <span>p-valeur : <strong>{fmtNum(data.backtest.p_value, 3)}</strong></span>
                <span className={data.backtest.rejected ? "down" : "up"}>
                  {data.backtest.rejected ? "Modèle rejeté au seuil de 5 %" : "Modèle non rejeté au seuil de 5 %"}
                </span>
              </div>
              <BacktestChart series={data.backtest.series} />
            </Panel>
          )}

          <Conventions items={CONVENTIONS} />
        </div>
      )}
    </>
  );
}
