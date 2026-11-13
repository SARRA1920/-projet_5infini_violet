import { useState } from "react";
import { BinsHistogram, SimpleLineChart, SourceBadge } from "../../components/actuarial/ActuarialCharts.jsx";
import { Conventions, Field, Kpi, Panel, Status } from "../../components/actuarial/Controls.jsx";
import useActuarialRefs from "../../hooks/useActuarialRefs.js";
import { PERIODS, fmtAmount, fmtCompact, fmtNum, fmtPct, parseNumber, percentToFraction, postActuarial } from "../../services/actuarial.js";

const FREQUENCY = {
  poisson: { label: "Poisson", params: [{ name: "lam", label: "λ (pertes / période)", value: "2" }] },
  negative_binomial: {
    label: "Binomiale négative",
    params: [
      { name: "r", label: "r", value: "3" },
      { name: "p", label: "p", value: "0,6" },
    ],
  },
};
const SEVERITY = {
  gamma: { label: "Gamma", params: [{ name: "shape", label: "Forme k", value: "2" }, { name: "scale", label: "Échelle θ", value: "500" }] },
  lognormal: { label: "Lognormale", params: [{ name: "mu", label: "μ de ln X", value: "7" }, { name: "sigma", label: "σ de ln X", value: "1" }] },
  pareto: { label: "Pareto", params: [{ name: "alpha", label: "Indice α", value: "2,5" }, { name: "xm", label: "Seuil x_m", value: "500" }] },
};
const DEFAULT_SCENARIOS = [
  { name: "Central", frequency_multiplier: "1", severity_multiplier: "1", tail_multiplier: "1" },
  { name: "Fréquence +50 %", frequency_multiplier: "1,5", severity_multiplier: "1", tail_multiplier: "1" },
  { name: "Sévérité +50 %", frequency_multiplier: "1", severity_multiplier: "1,5", tail_multiplier: "1" },
  { name: "Queue épaissie +25 %", frequency_multiplier: "1", severity_multiplier: "1", tail_multiplier: "1,25" },
  { name: "Combiné adverse", frequency_multiplier: "1,5", severity_multiplier: "1,5", tail_multiplier: "1,25" },
];
const MODEL_LABELS = { ...Object.fromEntries(Object.entries(FREQUENCY).map(([k, v]) => [k, v.label])), ...Object.fromEntries(Object.entries(SEVERITY).map(([k, v]) => [k, v.label])) };

const CONVENTIONS = [
  "Modèle collectif : S = X₁ + … + X_N, nombre N et montants Xᵢ indépendants, montants de même loi.",
  "E[S] = E[N]·E[X] ; Var[S] = E[N]·Var[X] + Var[N]·E[X]² (comparés au résultat simulé).",
  "Pertes de marché : un événement est un jour où la perte dépasse le seuil ; fréquence = événements par mois civil ; sévérité = montant perdu ce jour-là. Les événements sont supposés indépendants, ce que le regroupement de la volatilité contredit en partie.",
  "Ajustements par maximum de vraisemblance ; AIC = 2k − 2 ln L (plus petit = meilleur). La p-valeur de Kolmogorov-Smirnov est optimiste car les paramètres sont estimés sur les mêmes données.",
  "Pareto : seuil x_m = seuil de perte connu (données de marché) ou plus petit montant ; moyenne infinie si α ≤ 1, variance infinie si α ≤ 2.",
  "Fréquence annuelle : somme de k périodes indépendantes (Poisson kλ, binomiale négative (k·r, p)).",
  "Franchise d et plafond L par sinistre : perte retenue = min(max(X − d, 0), L).",
  "Capital économique = VaR₉₉,₅ %(S) − E[S] (perte inattendue, convention Solvabilité II à un an) ; variante TVaR.",
  "Stress : fréquence × m (moyenne), sévérité × s (échelle), queue × t (σ × t pour la lognormale, α / t pour Pareto, coefficient de variation × t pour la Gamma). Mêmes tirages aléatoires pour tous les scénarios.",
];

const defaults = (spec) => Object.fromEntries(spec.params.map((p) => [p.name, p.value]));
const toNumbers = (values) => Object.fromEntries(Object.entries(values).map(([k, v]) => [k, parseNumber(v)]));
const toText = (params) => Object.fromEntries(Object.entries(params).map(([k, v]) => [k, fmtNum(v, 4).replace(/\s/g, "")]));
const parseList = (text) => text.split(/[\s;]+/).map(parseNumber).filter((v) => v !== null);

function ParamInputs({ spec, values, onChange }) {
  return spec.params.map((p) => (
    <Field key={p.name} label={p.label}>
      <input value={values[p.name] ?? ""} inputMode="decimal" onChange={(e) => onChange({ ...values, [p.name]: e.target.value })} />
    </Field>
  ));
}

function FitTable({ title, fits, best, onUse }) {
  return (
    <Panel title={title} subtitle="Maximum de vraisemblance ; meilleur AIC surligné.">
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Loi</th>
              <th>Paramètres</th>
              <th>AIC</th>
              <th>KS (p-valeur)</th>
              <th>Moyenne</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {fits.map((f) => (
              <tr key={f.model} className={f.model === best ? "act-row-selected" : ""}>
                <td><strong>{MODEL_LABELS[f.model]}</strong></td>
                {f.error ? (
                  <td colSpan={5} className="act-note">{f.error}</td>
                ) : (
                  <>
                    <td>{Object.entries(f.params).map(([k, v]) => `${k} = ${fmtNum(v, v >= 100 ? 1 : 3)}`).join(" · ")}</td>
                    <td>{fmtNum(f.aic, 1)}</td>
                    <td>{f.ks_p_value == null ? "—" : `${fmtNum(f.ks_statistic, 3)} (${fmtNum(f.ks_p_value, 3)})`}</td>
                    <td>{f.mean == null ? "infinie" : f.model in FREQUENCY ? fmtNum(f.mean, 2) : fmtAmount(f.mean)}</td>
                    <td>
                      <button type="button" className="act-link-btn" onClick={() => onUse(f)}>Utiliser</button>
                    </td>
                  </>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export default function LossModelingPage() {
  const { portfolios, assetsWithHistory } = useActuarialRefs();
  const [source, setSource] = useState("market");
  const [market, setMarket] = useState({ target: "portfolio", symbol: "SPY", threshold: "1", notional: "", lookback: 0 });
  const [manual, setManual] = useState({ counts: "", amounts: "", periods_per_year: "12" });
  const [synth, setSynth] = useState({ freq: "negative_binomial", freqParams: defaults(FREQUENCY.negative_binomial), sev: "lognormal",
                                       sevParams: defaults(SEVERITY.lognormal), periods: "60", seed: "42" });
  const [fit, setFit] = useState(null);
  const [fitting, setFitting] = useState(false);

  const [model, setModel] = useState({ freq: "poisson", freqParams: defaults(FREQUENCY.poisson), periods_per_year: "12",
                                       sev: "lognormal", sevParams: defaults(SEVERITY.lognormal), fromFit: false });
  const [sim, setSim] = useState({ n_years: "20000", seed: "42", deductible: "0", limit: "" });
  const [scenarios, setScenarios] = useState(DEFAULT_SCENARIOS);
  const [result, setResult] = useState(null);
  const [simulating, setSimulating] = useState(false);
  const [simError, setSimError] = useState("");
  const [error, setError] = useState("");

  const runFit = () => {
    let body;
    if (source === "market") {
      body = {
        source,
        threshold: percentToFraction(market.threshold),
        notional: parseNumber(market.notional),
        lookback: Number(market.lookback),
        ...(market.target === "portfolio" ? { portfolio_id: portfolios[0]?.id ?? null } : { symbol: market.symbol }),
      };
    } else if (source === "manual") {
      body = { source, counts: parseList(manual.counts), amounts: parseList(manual.amounts), periods_per_year: Number(manual.periods_per_year) };
    } else {
      body = {
        source,
        frequency_model: synth.freq,
        frequency_params: toNumbers(synth.freqParams),
        severity_model: synth.sev,
        severity_params: toNumbers(synth.sevParams),
        periods: parseNumber(synth.periods),
        seed: parseNumber(synth.seed),
      };
    }
    setFitting(true);
    setError("");
    postActuarial("/loss-model/fit", body)
      .then((data) => {
        setFit(data);
        const ds = data.dataset;
        const bestFreq = data.frequency_fits.find((f) => f.model === data.best_frequency);
        const bestSev = data.severity_fits.find((f) => f.model === data.best_severity);
        setModel((m) => ({
          ...m,
          periods_per_year: String(ds.periods_per_year),
          ...(bestFreq && { freq: bestFreq.model, freqParams: toText(bestFreq.params) }),
          ...(bestSev && { sev: bestSev.model, sevParams: toText(bestSev.params) }),
          fromFit: true,
        }));
      })
      .catch((err) => {
        setFit(null);
        setError(err.message);
      })
      .finally(() => setFitting(false));
  };

  const useFit = (f) =>
    setModel((m) =>
      f.model in FREQUENCY ? { ...m, freq: f.model, freqParams: toText(f.params), fromFit: true } : { ...m, sev: f.model, sevParams: toText(f.params), fromFit: true },
    );

  const runSimulation = () => {
    setSimulating(true);
    setSimError("");
    postActuarial("/loss-model/simulate", {
      frequency_model: model.freq,
      frequency_params: toNumbers(model.freqParams),
      periods_per_year: parseNumber(model.periods_per_year),
      severity_model: model.sev,
      severity_params: toNumbers(model.sevParams),
      n_years: parseNumber(sim.n_years),
      seed: parseNumber(sim.seed),
      deductible: parseNumber(sim.deductible) ?? 0,
      limit: parseNumber(sim.limit),
      scenarios: scenarios.map((s) => ({
        name: s.name,
        frequency_multiplier: parseNumber(s.frequency_multiplier) ?? 1,
        severity_multiplier: parseNumber(s.severity_multiplier) ?? 1,
        tail_multiplier: parseNumber(s.tail_multiplier) ?? 1,
      })),
    })
      .then(setResult)
      .catch((err) => {
        setResult(null);
        setSimError(err.message);
      })
      .finally(() => setSimulating(false));
  };

  const ds = fit?.dataset;
  const capital = result?.economic_capital;

  return (
    <>
      <Panel title="1. Données de pertes" subtitle="Source des observations utilisées pour estimer fréquence et sévérité.">
        <div className="act-segmented">
          {[
            ["market", "Pertes de marché réelles"],
            ["manual", "Données saisies"],
            ["synthetic", "Données synthétiques"],
          ].map(([key, label]) => (
            <button key={key} type="button" className={source === key ? "active" : ""} onClick={() => setSource(key)}>
              {label}
            </button>
          ))}
        </div>

        {source === "market" && (
          <div className="act-filters">
            <Field label="Exposition">
              <select value={market.target} onChange={(e) => setMarket((m) => ({ ...m, target: e.target.value }))}>
                <option value="portfolio">Mon portefeuille (composition actuelle)</option>
                <option value="asset">Un actif</option>
              </select>
            </Field>
            {market.target === "asset" && (
              <Field label="Actif">
                <select value={market.symbol} onChange={(e) => setMarket((m) => ({ ...m, symbol: e.target.value }))}>
                  {assetsWithHistory.map((a) => (
                    <option key={a.symbol} value={a.symbol}>{a.symbol} — {a.name}</option>
                  ))}
                </select>
              </Field>
            )}
            <Field label="Seuil de perte quotidienne (%)">
              <input value={market.threshold} onChange={(e) => setMarket((m) => ({ ...m, threshold: e.target.value }))} inputMode="decimal" />
            </Field>
            <Field label="Valeur exposée" hint={market.target === "portfolio" ? "vide = valeur du portefeuille" : "vide = 100 000"}>
              <input value={market.notional} onChange={(e) => setMarket((m) => ({ ...m, notional: e.target.value }))} inputMode="decimal" />
            </Field>
            <Field label="Période">
              <select value={market.lookback} onChange={(e) => setMarket((m) => ({ ...m, lookback: e.target.value }))}>
                {PERIODS.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </Field>
          </div>
        )}
        {source === "manual" && (
          <div className="act-filters">
            <Field label="Nombre de pertes par période (séparés par des espaces)">
              <textarea rows={3} value={manual.counts} onChange={(e) => setManual((m) => ({ ...m, counts: e.target.value }))} placeholder="2 0 3 1 4 …" />
            </Field>
            <Field label="Montants des pertes">
              <textarea rows={3} value={manual.amounts} onChange={(e) => setManual((m) => ({ ...m, amounts: e.target.value }))} placeholder="1250 830 4100 …" />
            </Field>
            <Field label="Périodes par an">
              <select value={manual.periods_per_year} onChange={(e) => setManual((m) => ({ ...m, periods_per_year: e.target.value }))}>
                <option value="1">1 (annuelles)</option>
                <option value="4">4 (trimestrielles)</option>
                <option value="12">12 (mensuelles)</option>
              </select>
            </Field>
          </div>
        )}
        {source === "synthetic" && (
          <>
            <p className="banner act-warning">
              Données synthétiques : générées à partir des lois ci-dessous, elles ne représentent aucune perte réelle.
            </p>
            <div className="act-filters">
              <Field label="Loi de fréquence">
                <select value={synth.freq} onChange={(e) => setSynth((s) => ({ ...s, freq: e.target.value, freqParams: defaults(FREQUENCY[e.target.value]) }))}>
                  {Object.entries(FREQUENCY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </Field>
              <ParamInputs spec={FREQUENCY[synth.freq]} values={synth.freqParams} onChange={(v) => setSynth((s) => ({ ...s, freqParams: v }))} />
              <Field label="Loi de sévérité">
                <select value={synth.sev} onChange={(e) => setSynth((s) => ({ ...s, sev: e.target.value, sevParams: defaults(SEVERITY[e.target.value]) }))}>
                  {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                </select>
              </Field>
              <ParamInputs spec={SEVERITY[synth.sev]} values={synth.sevParams} onChange={(v) => setSynth((s) => ({ ...s, sevParams: v }))} />
              <Field label="Périodes générées">
                <input value={synth.periods} onChange={(e) => setSynth((s) => ({ ...s, periods: e.target.value }))} inputMode="numeric" />
              </Field>
              <Field label="Graine">
                <input value={synth.seed} onChange={(e) => setSynth((s) => ({ ...s, seed: e.target.value }))} inputMode="numeric" />
              </Field>
            </div>
          </>
        )}
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={runFit} disabled={fitting}>
            {fitting ? "Ajustement…" : "Ajuster les lois"}
          </button>
        </div>
      </Panel>

      <Status loading={fitting && !fit} error={error} warnings={fit?.warnings} />

      {ds && (
        <div className="act-results">
          <p className="act-meta">
            <SourceBadge source={ds.data_source} /> {ds.description}
          </p>
          <div className="stat-grid act-kpis">
            <Kpi label={`Périodes (${ds.period_label}s)`} value={ds.periods} note={`${ds.periods_per_year} par an`} />
            <Kpi label="Événements de perte" value={ds.events} note={`moyenne ${fmtNum(ds.count_mean, 2)} par ${ds.period_label}`} />
            <Kpi
              label="Dispersion de la fréquence"
              value={ds.count_mean ? fmtNum(ds.count_variance / ds.count_mean, 2) : "—"}
              note="variance / moyenne (1 = Poisson)"
            />
            <Kpi label="Montant moyen" value={fmtAmount(ds.amounts?.mean)} note={`maximum ${fmtAmount(ds.amounts?.max)}`} />
          </div>
          <div className="act-grid">
            <Panel title="Montants des pertes" subtitle="Distribution observée.">
              <BinsHistogram bins={ds.amounts_histogram} format={fmtAmount} axisFormat={fmtCompact} unit="Pertes" />
            </Panel>
            <Panel title={`Nombre de pertes par ${ds.period_label}`}>
              <BinsHistogram
                bins={ds.count_frequencies.map((r) => ({ from: r.count - 0.5, to: r.count + 0.5, count: r.periods }))}
                format={(v) => fmtNum(Math.round(v), 0)}
                unit="Périodes"
              />
            </Panel>
          </div>
          <FitTable title="Ajustement de la fréquence" fits={fit.frequency_fits} best={fit.best_frequency} onUse={useFit} />
          <FitTable title="Ajustement de la sévérité" fits={fit.severity_fits} best={fit.best_severity} onUse={useFit} />
        </div>
      )}

      <Panel
        title="2. Perte annuelle et capital économique"
        subtitle={model.fromFit ? "Paramètres repris de l'ajustement (modifiables)." : "Paramètres indicatifs à remplacer par un ajustement ou vos hypothèses."}
        source={model.fromFit ? fit?.dataset.data_source : "user_assumption"}
      >
        <div className="act-filters">
          <Field label="Loi de fréquence">
            <select value={model.freq} onChange={(e) => setModel((m) => ({ ...m, freq: e.target.value, freqParams: defaults(FREQUENCY[e.target.value]), fromFit: false }))}>
              {Object.entries(FREQUENCY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </Field>
          <ParamInputs spec={FREQUENCY[model.freq]} values={model.freqParams} onChange={(v) => setModel((m) => ({ ...m, freqParams: v }))} />
          <Field label="Périodes par an" hint="la fréquence ci-dessus est par période">
            <input value={model.periods_per_year} onChange={(e) => setModel((m) => ({ ...m, periods_per_year: e.target.value }))} inputMode="numeric" />
          </Field>
          <Field label="Loi de sévérité">
            <select value={model.sev} onChange={(e) => setModel((m) => ({ ...m, sev: e.target.value, sevParams: defaults(SEVERITY[e.target.value]), fromFit: false }))}>
              {Object.entries(SEVERITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </Field>
          <ParamInputs spec={SEVERITY[model.sev]} values={model.sevParams} onChange={(v) => setModel((m) => ({ ...m, sevParams: v }))} />
          <Field label="Années simulées">
            <input value={sim.n_years} onChange={(e) => setSim((s) => ({ ...s, n_years: e.target.value }))} inputMode="numeric" />
          </Field>
          <Field label="Graine">
            <input value={sim.seed} onChange={(e) => setSim((s) => ({ ...s, seed: e.target.value }))} inputMode="numeric" />
          </Field>
          <Field label="Franchise par sinistre">
            <input value={sim.deductible} onChange={(e) => setSim((s) => ({ ...s, deductible: e.target.value }))} inputMode="decimal" />
          </Field>
          <Field label="Plafond par sinistre" hint="vide = sans plafond">
            <input value={sim.limit} onChange={(e) => setSim((s) => ({ ...s, limit: e.target.value }))} inputMode="decimal" />
          </Field>
        </div>
        <details className="act-calibrate">
          <summary>Scénarios de stress des hypothèses ({scenarios.length})</summary>
          <div className="act-scenario act-scenario-head">
            <span>Nom</span><span>Fréquence ×</span><span>Sévérité ×</span><span>Queue ×</span><span />
          </div>
          {scenarios.map((s, i) => (
            <div key={i} className="act-scenario">
              {["name", "frequency_multiplier", "severity_multiplier", "tail_multiplier"].map((key) => (
                <input key={key} value={s[key]} aria-label={key} inputMode={key === "name" ? "text" : "decimal"}
                       onChange={(e) => setScenarios((list) => list.map((r, j) => (j === i ? { ...r, [key]: e.target.value } : r)))} />
              ))}
              <button type="button" className="act-icon-btn" aria-label="Retirer" disabled={scenarios.length === 1}
                      onClick={() => setScenarios((list) => list.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
          <button type="button" className="act-link-btn" disabled={scenarios.length >= 8}
                  onClick={() => setScenarios((list) => [...list, { name: `Scénario ${list.length + 1}`, frequency_multiplier: "1", severity_multiplier: "1", tail_multiplier: "1" }])}>
            + Ajouter un scénario
          </button>
        </details>
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={runSimulation} disabled={simulating}>
            {simulating ? "Simulation…" : "Simuler la perte annuelle"}
          </button>
        </div>
      </Panel>

      <Status loading={simulating && !result} error={simError} warnings={result?.warnings} />

      {result && (
        <div className={simulating ? "act-results act-stale" : "act-results"}>
          <div className="stat-grid act-kpis">
            <Kpi label="Perte annuelle moyenne" value={fmtAmount(result.aggregate.mean)}
                 note={`théorique : ${fmtAmount(result.analytic.mean)} · ${fmtNum(result.frequency_moments.mean, 1)} pertes / an`} />
            <Kpi label="VaR 99,5 % à un an" value={fmtAmount(capital.var)} note={`TVaR ${fmtAmount(result.risk_measures.find((r) => r.confidence === 0.995).tvar)}`} />
            <Kpi label="Capital économique (VaR − E[S])" value={fmtAmount(capital.capital)} tone="down" note={`variante TVaR : ${fmtAmount(capital.capital_tvar)}`} />
            <Kpi label="Probabilité d'aucune perte" value={fmtPct(result.probability_no_loss)} note={`${result.n_years.toLocaleString("fr-FR")} années simulées, graine ${result.seed ?? "aléatoire"}`} />
          </div>
          <div className="act-grid">
            <Panel title="Distribution de la perte annuelle" subtitle="En rouge : au-delà de la VaR 99,5 %." source="simulated">
              <BinsHistogram bins={result.histogram} format={fmtAmount} axisFormat={fmtCompact} unit="Années"
                             colorOf={(bin) => (bin.to > capital.var ? "#ff5d73" : "#8eb7ff")} />
            </Panel>
            <Panel title="Densité de la sévérité" subtitle={`Moyenne ${fmtAmount(result.severity.mean)} · quantile 99 % ${fmtAmount(result.severity.quantile_99)}`}>
              <SimpleLineChart data={result.severity_curve} x="x" y="density" name="Densité" xFormat={fmtAmount}
                               yFormat={(v) => v.toExponential(1)} />
            </Panel>
          </div>
          <Panel title="Mesures de risque et capital">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>Confiance</th><th>VaR</th><th>TVaR</th><th>Capital (VaR)</th><th>Capital (TVaR)</th></tr>
                </thead>
                <tbody>
                  {result.risk_measures.map((r) => (
                    <tr key={r.confidence} className={r.confidence === 0.995 ? "act-row-selected" : ""}>
                      <td><strong>{fmtNum(r.confidence * 100, 1)} %</strong></td>
                      <td>{fmtAmount(r.var)}</td>
                      <td>{fmtAmount(r.tvar)}</td>
                      <td>{fmtAmount(r.capital_var)}</td>
                      <td>{fmtAmount(r.capital_tvar)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Stress testing des hypothèses" subtitle="Capital à 99,5 % sous chaque scénario." source="simulated">
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr><th>Scénario</th><th>Perte moyenne</th><th>VaR 99,5 %</th><th>Capital</th><th>Écart</th></tr>
                </thead>
                <tbody>
                  {result.stress.map((r) => (
                    <tr key={r.name}>
                      <td>
                        <strong>{r.name}</strong>
                        <span>F×{fmtNum(r.frequency_multiplier, 2)} · S×{fmtNum(r.severity_multiplier, 2)} · Q×{fmtNum(r.tail_multiplier, 2)}</span>
                      </td>
                      <td>{fmtAmount(r.expected_loss)}</td>
                      <td>{fmtAmount(r.var)}</td>
                      <td>{fmtAmount(r.capital)}</td>
                      <td className={r.capital_change > 0 ? "down" : r.capital_change < 0 ? "up" : ""}>
                        {r.capital_change == null ? "—" : `${r.capital_change > 0 ? "+" : ""}${fmtPct(r.capital_change)}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}
      <Conventions items={CONVENTIONS} />
    </>
  );
}
