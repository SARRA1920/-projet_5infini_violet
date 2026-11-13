import { useEffect, useState } from "react";
import { BinsHistogram, FanChart, SourceBadge } from "../../components/actuarial/ActuarialCharts.jsx";
import { Conventions, Field, Kpi, Panel, Status } from "../../components/actuarial/Controls.jsx";
import useActuarialRefs from "../../hooks/useActuarialRefs.js";
import {
  PERIODS,
  fmtAmount,
  fmtNum,
  fmtPct,
  parseNumber,
  percentToFraction,
  postActuarial,
} from "../../services/actuarial.js";

const MODELS = {
  gbm: {
    label: "Mouvement brownien géométrique (GBM)",
    formula: "dS = μ S dt + σ S dW",
    about: "Prix d'un actif : rendements log normaux, μ et σ constants. Calibré sur les cours réels.",
  },
  vasicek: {
    label: "Vasicek",
    formula: "dr = a (b − r) dt + σ dW",
    about: "Taux court gaussien avec retour à la moyenne b à la vitesse a ; le taux peut devenir négatif.",
  },
  cir: {
    label: "Cox-Ingersoll-Ross (CIR)",
    formula: "dr = a (b − r) dt + σ √r dW",
    about: "Taux court positif si la condition de Feller 2ab ≥ σ² est respectée.",
  },
  hull_white: {
    label: "Hull-White (1 facteur)",
    formula: "dr = (θ(t) − a r) dt + σ dW",
    about: "θ(t) ajusté pour reproduire exactement la courbe zéro-coupon initiale saisie.",
  },
};

// Valeurs de départ des modèles de taux : hypothèses à modifier, affichées comme telles.
const RATE_DEFAULTS = { r0: "3", a: "0,5", b: "4", sigma: "1" };
const CURVE_DEFAULT = [
  { maturity: "1", rate: "3" },
  { maturity: "5", rate: "3,5" },
  { maturity: "10", rate: "4" },
];
const DT_CHOICES = [
  { value: 1 / 252, label: "Quotidienne (1/252)" },
  { value: 1 / 52, label: "Hebdomadaire (1/52)" },
  { value: 1 / 12, label: "Mensuelle (1/12)" },
];

const CONVENTIONS = [
  "Temps en années, paramètres annualisés ; taux en composition continue.",
  "Simulation exacte des lois de transition (lognormale pour le GBM, gaussienne pour Vasicek et Hull-White, khi-deux non centré pour le CIR) : pas d'erreur de discrétisation.",
  "GBM calibré par maximum de vraisemblance sur les rendements log : σ² = Var(x)/Δ, μ = moyenne(x)/Δ + σ²/2. La dérive μ est très imprécise sur un an (erreur standard ≈ σ).",
  "Vasicek et Hull-White (a, σ) : AR(1) estimé par moindres carrés sur la série de taux fournie. CIR : régression sur la discrétisation d'Euler, série strictement positive.",
  "Aucune série de taux n'est stockée dans l'application : les paramètres de taux et la courbe initiale sont des hypothèses de l'utilisateur.",
  "Intervalle de confiance à 95 % de la moyenne : ± 1,96 × écart-type / √n. Les quantiles 5 % et 95 % encadrent 90 % des valeurs simulées.",
  "Analyse de sensibilité : volatilité σ multipliée de 0,5 à 1,5 avec les mêmes tirages aléatoires (2 000 trajectoires au plus).",
  "Ces modèles décrivent une distribution de scénarios ; ils ne prédisent pas l'évolution future.",
];

export default function StochasticPage() {
  const { assetsWithHistory } = useActuarialRefs();
  const [model, setModel] = useState("gbm");
  const [symbol, setSymbol] = useState("SPY");
  const [lookback, setLookback] = useState(252);
  const [gbmParams, setGbmParams] = useState({ s0: "", mu: "", sigma: "" });
  const [rateParams, setRateParams] = useState(RATE_DEFAULTS);
  const [curve, setCurve] = useState(CURVE_DEFAULT);
  const [series, setSeries] = useState("");
  const [dt, setDt] = useState(1 / 12);
  const [sim, setSim] = useState({ horizon: "1", steps: "252", n: "5000", seed: "42" });
  const [calibration, setCalibration] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const isGbm = model === "gbm";
  const setSimField = (key) => (e) => setSim((s) => ({ ...s, [key]: e.target.value }));

  const calibrate = () => {
    setError("");
    setLoading(true);
    const body = isGbm
      ? { model, symbol, lookback: Number(lookback) }
      : {
          model,
          dt,
          series: series
            .split(/[\s;]+/)
            .map((v) => percentToFraction(v))
            .filter((v) => v !== null),
        };
    postActuarial("/stochastic/calibrate", body)
      .then((cal) => {
        setCalibration(cal);
        const p = cal.params;
        const pct = (v) => fmtNum(v * 100, 4).replace(/\s/g, "");
        if (isGbm) setGbmParams({ s0: String(p.s0), mu: pct(p.mu), sigma: pct(p.sigma) });
        else
          setRateParams((prev) => ({
            ...prev,
            a: fmtNum(p.a, 4).replace(/\s/g, ""),
            sigma: pct(p.sigma),
            ...(p.b !== undefined && { b: pct(p.b) }),
            ...(p.r0 !== undefined && { r0: pct(p.r0) }),
          }));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  // Calibration GBM automatique au changement d'actif ou de période.
  useEffect(() => {
    if (isGbm) calibrate();
  }, [model, symbol, lookback]);

  const simulate = () => {
    let params;
    if (isGbm) {
      params = {
        s0: parseNumber(gbmParams.s0),
        mu: percentToFraction(gbmParams.mu),
        sigma: percentToFraction(gbmParams.sigma),
      };
    } else if (model === "hull_white") {
      params = {
        a: parseNumber(rateParams.a),
        sigma: percentToFraction(rateParams.sigma),
        curve_maturities: curve.map((c) => parseNumber(c.maturity)),
        curve_rates: curve.map((c) => percentToFraction(c.rate)),
      };
    } else {
      params = {
        r0: percentToFraction(rateParams.r0),
        a: parseNumber(rateParams.a),
        b: percentToFraction(rateParams.b),
        sigma: percentToFraction(rateParams.sigma),
      };
    }
    setError("");
    setLoading(true);
    postActuarial("/stochastic/simulate", {
      model,
      params,
      symbol: isGbm ? symbol : null,
      horizon: parseNumber(sim.horizon),
      steps: parseNumber(sim.steps),
      n_simulations: parseNumber(sim.n),
      seed: parseNumber(sim.seed),
    })
      .then(setResult)
      .catch((err) => {
        setResult(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  };

  const switchModel = (next) => {
    setModel(next);
    setResult(null);
    setCalibration(null);
    setError("");
  };

  const formatValue = (v) => (result?.model === "gbm" ? fmtAmount(v) : fmtPct(v));
  const t = result?.terminal;
  const an = result?.analytics;

  return (
    <>
      <article className="panel">
        <div className="act-segmented">
          {Object.entries(MODELS).map(([key, m]) => (
            <button key={key} type="button" className={model === key ? "active" : ""} onClick={() => switchModel(key)}>
              {m.label}
            </button>
          ))}
        </div>
        <p className="act-formula">
          <code>{MODELS[model].formula}</code> {MODELS[model].about}
        </p>

        <div className="act-two-cols">
          <div>
            <h3 className="act-subtitle">1. Paramètres {isGbm ? "(calibrés sur les cours réels)" : ""}</h3>
            {isGbm ? (
              <div className="act-filters">
                <Field label="Actif">
                  <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                    {assetsWithHistory.map((a) => (
                      <option key={a.symbol} value={a.symbol}>
                        {a.symbol} — {a.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Période de calibration">
                  <select value={lookback} onChange={(e) => setLookback(e.target.value)}>
                    {PERIODS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Prix initial S₀">
                  <input value={gbmParams.s0} onChange={(e) => setGbmParams((p) => ({ ...p, s0: e.target.value }))} inputMode="decimal" />
                </Field>
                <Field label="Dérive μ (% / an)">
                  <input value={gbmParams.mu} onChange={(e) => setGbmParams((p) => ({ ...p, mu: e.target.value }))} inputMode="decimal" />
                </Field>
                <Field label="Volatilité σ (% / an)">
                  <input value={gbmParams.sigma} onChange={(e) => setGbmParams((p) => ({ ...p, sigma: e.target.value }))} inputMode="decimal" />
                </Field>
              </div>
            ) : (
              <>
                <div className="act-filters">
                  {model !== "hull_white" && (
                    <Field label="Taux initial r₀ (%)">
                      <input value={rateParams.r0} onChange={(e) => setRateParams((p) => ({ ...p, r0: e.target.value }))} inputMode="decimal" />
                    </Field>
                  )}
                  <Field label="Vitesse de retour a">
                    <input value={rateParams.a} onChange={(e) => setRateParams((p) => ({ ...p, a: e.target.value }))} inputMode="decimal" />
                  </Field>
                  {model !== "hull_white" && (
                    <Field label="Niveau long terme b (%)">
                      <input value={rateParams.b} onChange={(e) => setRateParams((p) => ({ ...p, b: e.target.value }))} inputMode="decimal" />
                    </Field>
                  )}
                  <Field label={model === "cir" ? "Volatilité σ (% , facteur de √r)" : "Volatilité σ (% / an)"}>
                    <input value={rateParams.sigma} onChange={(e) => setRateParams((p) => ({ ...p, sigma: e.target.value }))} inputMode="decimal" />
                  </Field>
                </div>
                {model === "hull_white" && (
                  <div className="act-curve">
                    <p className="act-note">
                      Courbe zéro-coupon initiale <SourceBadge source="user_assumption" />
                    </p>
                    {curve.map((row, i) => (
                      <div key={i} className="act-basket-row">
                        <input value={row.maturity} aria-label="Maturité (ans)" inputMode="decimal"
                               onChange={(e) => setCurve((c) => c.map((r, j) => (j === i ? { ...r, maturity: e.target.value } : r)))} />
                        <input value={row.rate} aria-label="Taux (%)" inputMode="decimal"
                               onChange={(e) => setCurve((c) => c.map((r, j) => (j === i ? { ...r, rate: e.target.value } : r)))} />
                        <button type="button" className="act-icon-btn" disabled={curve.length === 1} aria-label="Retirer"
                                onClick={() => setCurve((c) => c.filter((_, j) => j !== i))}>
                          ×
                        </button>
                      </div>
                    ))}
                    <button type="button" className="act-link-btn" onClick={() => setCurve((c) => [...c, { maturity: "", rate: "" }])}>
                      + Ajouter un point (maturité en années, taux en %)
                    </button>
                  </div>
                )}
                <p className="act-note">
                  <SourceBadge source="user_assumption" /> Valeurs de départ indicatives, à remplacer par vos hypothèses ou par une calibration.
                </p>
                <details className="act-calibrate">
                  <summary>Calibrer sur une série historique de taux</summary>
                  <Field label="Série de taux en % (séparés par des espaces, retours à la ligne ou ;)">
                    <textarea rows={4} value={series} onChange={(e) => setSeries(e.target.value)} placeholder="3,10 3,12 3,08 …" />
                  </Field>
                  <Field label="Périodicité de la série">
                    <select value={dt} onChange={(e) => setDt(Number(e.target.value))}>
                      {DT_CHOICES.map((c) => (
                        <option key={c.label} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <button type="button" className="act-secondary-btn" onClick={calibrate} disabled={loading || !series.trim()}>
                    Calibrer
                  </button>
                </details>
              </>
            )}
            {calibration && (
              <div className="act-calibration">
                <SourceBadge source={calibration.data_source} />
                <span>
                  {calibration.observations} observations
                  {calibration.period_start && ` du ${calibration.period_start} au ${calibration.period_end}`}
                </span>
                {calibration.standard_errors && (
                  <span>
                    Erreur standard : μ ± {fmtPct(calibration.standard_errors.mu)}, σ ± {fmtPct(calibration.standard_errors.sigma)}
                  </span>
                )}
                {calibration.notes.map((n) => (
                  <span key={n}>{n}</span>
                ))}
              </div>
            )}
          </div>

          <div>
            <h3 className="act-subtitle">2. Simulation Monte Carlo</h3>
            <div className="act-filters">
              <Field label="Horizon (années)">
                <input value={sim.horizon} onChange={setSimField("horizon")} inputMode="decimal" />
              </Field>
              <Field label="Nombre de pas">
                <input value={sim.steps} onChange={setSimField("steps")} inputMode="numeric" />
              </Field>
              <Field label="Simulations" hint="jusqu'à 20 000 ; simulations × pas ≤ 5 040 000">
                <input value={sim.n} onChange={setSimField("n")} inputMode="numeric" />
              </Field>
              <Field label="Graine aléatoire">
                <input value={sim.seed} onChange={setSimField("seed")} inputMode="numeric" />
              </Field>
            </div>
            <div className="act-actions">
              <button type="button" className="primary-btn" onClick={simulate} disabled={loading}>
                {loading ? "Calcul…" : "Simuler"}
              </button>
            </div>
          </div>
        </div>
      </article>

      <Status loading={loading && !result} error={error} />

      {result && (
        <div className={loading ? "act-results act-stale" : "act-results"}>
          <div className="stat-grid act-kpis">
            <Kpi
              label={`Moyenne à ${fmtNum(result.horizon_years, 2)} an(s)`}
              value={formatValue(t.mean)}
              note={`théorique : ${formatValue(an.analytic_mean)} · IC 95 % [${formatValue(t.mean_ci95[0])} ; ${formatValue(t.mean_ci95[1])}]`}
            />
            <Kpi label="Intervalle 90 % des valeurs" value={`${formatValue(t.quantiles.p05)} – ${formatValue(t.quantiles.p95)}`} note={`médiane ${formatValue(t.quantiles.p50)}`} />
            <Kpi label="Écart-type" value={formatValue(t.std)} note={`théorique : ${formatValue(an.analytic_std)}`} />
            {result.model === "gbm" ? (
              <Kpi
                label="Probabilité de perte"
                value={fmtPct(an.probability_of_loss)}
                tone="down"
                note={`théorique : ${fmtPct(an.probability_of_loss_analytic)} · VaR 95 % ${fmtPct(an.var_95)}`}
              />
            ) : (
              <Kpi
                label="Zéro-coupon P(0,T)"
                value={fmtNum(an.zero_coupon_mc, 4)}
                note={`${result.model === "hull_white" ? "courbe initiale" : "formule fermée"} : ${fmtNum(an.zero_coupon_analytic, 4)} · P(r<0) ${fmtPct(an.probability_negative_rate)}`}
              />
            )}
          </div>
          {result.model === "cir" && !an.feller_condition && (
            <p className="banner act-warning">Condition de Feller non respectée (2ab &lt; σ²) : le taux peut atteindre 0.</p>
          )}

          <div className="act-grid">
            <Panel
              title="Trajectoires simulées"
              subtitle={`${result.n_simulations.toLocaleString("fr-FR")} trajectoires, ${result.steps} pas, graine ${result.seed ?? "aléatoire"}.`}
              source="simulated"
            >
              <FanChart fan={result.fan} paths={result.sample_paths} format={formatValue} />
            </Panel>
            <Panel title="Distribution à l'horizon" source="simulated">
              <BinsHistogram bins={result.terminal_histogram} format={formatValue} unit="Simulations" />
            </Panel>
          </div>

          <Panel title="Analyse de sensibilité à la volatilité" subtitle="Mêmes tirages aléatoires pour chaque niveau de σ.">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Multiplicateur</th>
                    <th>Volatilité</th>
                    <th>Moyenne</th>
                    <th>Écart-type</th>
                    {result.model === "gbm" ? (
                      <>
                        <th>P(perte)</th>
                        <th>VaR 95 %</th>
                      </>
                    ) : (
                      <>
                        <th>P(r &lt; 0)</th>
                        <th>Zéro-coupon</th>
                      </>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {result.sensitivity.map((row) => (
                    <tr key={row.sigma_multiplier} className={row.sigma_multiplier === 1 ? "act-row-selected" : ""}>
                      <td><strong>{fmtNum(row.sigma_multiplier, 2)}</strong></td>
                      <td>{fmtPct(row.sigma)}</td>
                      <td>{formatValue(row.mean)}</td>
                      <td>{formatValue(row.std)}</td>
                      {result.model === "gbm" ? (
                        <>
                          <td>{fmtPct(row.probability_of_loss)}</td>
                          <td>{fmtPct(row.var_95)}</td>
                        </>
                      ) : (
                        <>
                          <td>{fmtPct(row.probability_negative_rate)}</td>
                          <td>{fmtNum(row.zero_coupon_mc, 4)}</td>
                        </>
                      )}
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
