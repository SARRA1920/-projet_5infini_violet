import { useEffect, useState } from "react";
import {
  ExposureBars,
  ReturnHistogram,
  RiskShareChart,
  SourceBadge,
  ValueCurveChart,
} from "../../components/actuarial/ActuarialCharts.jsx";
import { actuarialApi, fmtAmount, fmtPct, fmtRatio, toneOf } from "../../services/actuarial.js";

const PERIODS = [
  { value: 63, label: "3 mois" },
  { value: 126, label: "6 mois" },
  { value: 252, label: "1 an" },
  { value: 504, label: "2 ans" },
  { value: 0, label: "Tout l'historique" },
];

function Kpi({ label, value, note, tone = "" }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong className={tone}>{value}</strong>
      <em>{note}</em>
    </article>
  );
}

export default function ActuarialDashboard() {
  const [portfolios, setPortfolios] = useState([]);
  const [filters, setFilters] = useState({ portfolio_id: "", lookback: 252, confidence: 0.95, horizon: 1 });
  const [riskFree, setRiskFree] = useState("0");
  const [appliedRiskFree, setAppliedRiskFree] = useState(0);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    actuarialApi("/portfolios")
      .then(setPortfolios)
      .catch(() => setPortfolios([]));
  }, []);

  useEffect(() => {
    const params = { ...filters, risk_free_rate: appliedRiskFree };
    if (!params.portfolio_id) delete params.portfolio_id;
    setLoading(true);
    setError("");
    actuarialApi("/dashboard", params)
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [filters, appliedRiskFree]);

  const update = (key) => (event) => setFilters((prev) => ({ ...prev, [key]: Number(event.target.value) || "" }));
  const applyRiskFree = () => {
    const value = Number(String(riskFree).replace(",", ".")) / 100;
    if (Number.isFinite(value)) setAppliedRiskFree(value);
  };

  const m = data?.metrics;
  const conf = `${Math.round(filters.confidence * 100)} %`;
  const horizon = `${filters.horizon} j`;
  const var1d = m ? m.var / Math.sqrt(filters.horizon) : null;

  return (
    <>
      <article className="panel act-filters-panel">
        <div className="act-filters">
          <label className="act-field">
            Portefeuille
            <select value={filters.portfolio_id} onChange={update("portfolio_id")}>
              {portfolios.length === 0 && <option value="">Portefeuille principal</option>}
              {portfolios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="act-field">
            Période historique
            <select value={filters.lookback} onChange={(e) => setFilters((prev) => ({ ...prev, lookback: Number(e.target.value) }))}>
              {PERIODS.map((p) => (
                <option key={p.value} value={p.value}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label className="act-field">
            Niveau de confiance
            <select value={filters.confidence} onChange={update("confidence")}>
              <option value={0.95}>95 %</option>
              <option value={0.99}>99 %</option>
            </select>
          </label>
          <label className="act-field">
            Horizon
            <select value={filters.horizon} onChange={update("horizon")}>
              <option value={1}>1 jour</option>
              <option value={10}>10 jours</option>
              <option value={20}>20 jours</option>
            </select>
          </label>
          <label className="act-field">
            Taux sans risque annuel (%)
            <input
              type="text"
              inputMode="decimal"
              value={riskFree}
              onChange={(e) => setRiskFree(e.target.value)}
              onBlur={applyRiskFree}
              onKeyDown={(e) => e.key === "Enter" && applyRiskFree()}
            />
          </label>
        </div>
        {data && (
          <p className="act-meta">
            <SourceBadge source={data.data_source} />
            {data.observations > 0
              ? `${data.observations} jours de bourse, du ${data.period_start} au ${data.period_end}. Composition actuelle supposée constante sur la période.`
              : "Aucun historique exploitable."}
            {appliedRiskFree !== 0 && <SourceBadge source="user_assumption" />}
          </p>
        )}
      </article>

      {error && <p className="banner">Tableau de bord indisponible : {error}</p>}
      {loading && !data && <p className="banner">Calcul des indicateurs…</p>}
      {data?.warnings.map((w) => (
        <p key={w} className="banner act-warning">
          {w}
        </p>
      ))}

      {data && (
        <div className={loading ? "act-results act-stale" : "act-results"}>
          <div className="stat-grid act-kpis">
            <Kpi
              label="Valeur totale"
              value={fmtAmount(data.total_value)}
              note={`dont liquidités ${fmtAmount(data.cash)}`}
            />
            <Kpi
              label="Rendement sur la période"
              value={fmtPct(m?.cumulative_return)}
              tone={toneOf(m?.cumulative_return)}
              note={m ? `annualisé : ${fmtPct(m.annualized_return)}` : "historique insuffisant"}
            />
            <Kpi label="Volatilité annualisée" value={fmtPct(m?.annualized_volatility)} note="écart-type x √252" />
            <Kpi
              label="Drawdown maximal"
              value={fmtPct(m?.max_drawdown)}
              tone={m?.max_drawdown ? "down" : ""}
              note="pire chute depuis un sommet"
            />
            <Kpi
              label={`VaR historique ${conf} · ${horizon}`}
              value={fmtPct(m?.var)}
              note={m ? `perte potentielle : ${fmtAmount(m.var_amount)}` : ""}
            />
            <Kpi
              label={`Expected Shortfall ${conf} · ${horizon}`}
              value={fmtPct(m?.expected_shortfall)}
              note={m ? `perte moyenne au-delà : ${fmtAmount(m.expected_shortfall_amount)}` : ""}
            />
            <Kpi label="Sharpe Ratio" value={fmtRatio(m?.sharpe_ratio)} tone={toneOf(m?.sharpe_ratio)} note="annualisé" />
            <Kpi label="Sortino Ratio" value={fmtRatio(m?.sortino_ratio)} tone={toneOf(m?.sortino_ratio)} note="risque baissier seul" />
          </div>

          <div className="act-grid">
            <article className="panel">
              <div className="panel-head">
                <div>
                  <h2>Valeur simulée du portefeuille</h2>
                  <p>Composition actuelle appliquée à l'historique des cours.</p>
                </div>
              </div>
              {data.value_curve.length > 1 ? (
                <ValueCurveChart points={data.value_curve} />
              ) : (
                <p className="act-empty">Pas assez d'historique pour tracer la courbe.</p>
              )}
            </article>
            <article className="panel">
              <div className="panel-head">
                <div>
                  <h2>Exposition par classe d'actifs</h2>
                  <p>
                    {data.transactions_count} transaction(s) · gains réalisés{" "}
                    <span className={toneOf(data.realized_pnl_total)}>{fmtAmount(data.realized_pnl_total)}</span>
                  </p>
                </div>
              </div>
              <ExposureBars rows={data.exposure} />
              <p className="act-note">
                Concentration (Herfindahl, hors liquidités) :{" "}
                <strong>{data.concentration_hhi == null ? "—" : fmtRatio(data.concentration_hhi)}</strong>
              </p>
            </article>
          </div>

          <div className="act-grid">
            <article className="panel">
              <div className="panel-head">
                <div>
                  <h2>Distribution des rendements quotidiens</h2>
                  <p>En rouge : jours au-delà de la VaR {conf} à 1 jour ({fmtPct(var1d)}).</p>
                </div>
              </div>
              {data.daily_returns.length > 1 ? (
                <ReturnHistogram returns={data.daily_returns} var1d={var1d} />
              ) : (
                <p className="act-empty">Pas assez d'historique.</p>
              )}
            </article>
            <article className="panel">
              <div className="panel-head">
                <div>
                  <h2>Principaux facteurs de risque</h2>
                  <p>Poids (gris) et part de la volatilité (bleu), décomposition d'Euler.</p>
                </div>
              </div>
              {data.risk_contributions.length > 0 ? (
                <>
                  <RiskShareChart rows={data.risk_contributions} />
                  <div className="table-scroll">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Actif</th>
                          <th>Poids</th>
                          <th>Contrib. marginale</th>
                          <th>Contrib. au risque</th>
                          <th>Part</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.risk_contributions.map((row) => (
                          <tr key={row.symbol}>
                            <td>
                              <strong>{row.symbol}</strong>
                            </td>
                            <td>{fmtPct(row.weight)}</td>
                            <td>{fmtPct(row.marginal_contribution)}</td>
                            <td>{fmtPct(row.component_contribution)}</td>
                            <td>{fmtPct(row.risk_share)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              ) : (
                <p className="act-empty">Aucune position avec historique de cours.</p>
              )}
            </article>
          </div>

          <details className="panel act-conventions">
            <summary>Conventions de calcul</summary>
            <ul>
              <li>Rendements simples quotidiens r = P(t) / P(t-1) − 1, sur les dates communes à tous les actifs détenus (aucune interpolation).</li>
              <li>Composition actuelle appliquée à tout l'historique ; liquidités à rendement nul ; 252 jours de bourse par an.</li>
              <li>VaR historique : quantile empirique des pertes (sans interpolation), multiplié par √horizon (rendements supposés i.i.d.).</li>
              <li>Expected Shortfall : moyenne des pertes supérieures ou égales à la VaR, même mise à l'échelle.</li>
              <li>Sharpe = moyenne(r − rf/252) / écart-type(r) × √252 ; Sortino : même numérateur, écart baissier au dénominateur.</li>
              <li>Contributions au risque : σp = √(wᵀΣw), contribution marginale = (Σw)ᵢ/σp, contribution = wᵢ × marginale, annualisées.</li>
              <li>La VaR de l'écran Portefeuille lit le quantile par indice et la borne à 0 : un écart léger est possible sur un petit échantillon.</li>
            </ul>
          </details>
        </div>
      )}
    </>
  );
}
