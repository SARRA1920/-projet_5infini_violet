import { useEffect, useState } from "react";
import { BinsHistogram, SourceBadge, lossColor } from "../../components/actuarial/ActuarialCharts.jsx";
import { Field, Panel, Status } from "../../components/actuarial/Controls.jsx";
import useActuarialRefs from "../../hooks/useActuarialRefs.js";
import { actuarialApi, fmtAmount, fmtCompact, fmtNum, fmtPct, parseNumber, postActuarial } from "../../services/actuarial.js";

const FAMILIES = {
  risk: "Value at Risk",
  stochastic: "Modèles stochastiques",
  optimization: "Optimisation",
  frequency: "Fréquence des pertes",
  severity: "Sévérité des pertes",
};
const MAX_CONFIGS = 6;
// Calculs enregistrés par les autres écrans (hors catalogue du laboratoire).
const OTHER_RUNS = {
  var: "VaR d'un panier (Risk Analytics)",
  bond: "Obligation théorique",
  loss_model: "Modèle de pertes fréquence-sévérité",
};

const formatters = {
  pct: fmtPct,
  amount: fmtAmount,
  number: (v) => fmtNum(v, 4),
  count: (v) => fmtNum(v, 0),
};
const formatValue = (kind, value) => (formatters[kind] || formatters.number)(value);

// Paramètres en % affichés × 100 ; listes saisies séparées par « ; ».
function paramToText(param, value) {
  if (value === null || value === undefined) return "";
  const scale = param.unit === "%" ? 100 : 1;
  const one = (v) => fmtNum(v * scale, 4).replace(/\s/g, "").replace(/,?0+$/, "");
  return Array.isArray(value) ? value.map(one).join("; ") : one(value);
}

function textToParam(param, text) {
  if (text === "" || text === undefined) return null;
  const scale = param.unit === "%" ? 100 : 1;
  if (Array.isArray(param.default)) return text.split(";").map((t) => parseNumber(t.trim())).filter((v) => v !== null).map((v) => v / scale);
  const value = parseNumber(text);
  return value === null ? null : value / scale;
}

function newConfig(model, catalog, defaults = {}) {
  const spec = catalog.find((m) => m.id === model);
  return {
    id: Math.random().toString(36).slice(2),
    model,
    target: "portfolio",
    symbols: ["SPY"],
    confidence: 0.95,
    horizon: 1,
    lookback: 252,
    horizon_years: "1",
    steps: "52",
    n_simulations: "5000",
    seed: "42",
    params: Object.fromEntries((spec?.params || []).map((p) => [p.name, paramToText(p, p.default)])),
    ...defaults,
  };
}

function toRequest(config, spec, portfolioId) {
  const usesAssets = spec.target === "asset" || (spec.target === "portfolio_or_assets" && config.target === "assets");
  const usesPortfolio = spec.target === "portfolio" || (spec.target === "portfolio_or_assets" && config.target === "portfolio");
  return {
    model: config.model,
    symbols: usesAssets || spec.target === "portfolio" ? config.symbols : [],
    portfolio_id: usesPortfolio ? portfolioId : null,
    lookback: Number(config.lookback),
    confidence: Number(config.confidence),
    horizon: Number(config.horizon),
    horizon_years: parseNumber(config.horizon_years) ?? 1,
    steps: parseNumber(config.steps) ?? 52,
    n_simulations: parseNumber(config.n_simulations) ?? 5000,
    seed: parseNumber(config.seed),
    params: Object.fromEntries(spec.params.map((p) => [p.name, textToParam(p, config.params[p.name])])),
  };
}

function download(filename, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function csvCell(value) {
  const text = value === null || value === undefined ? "" : String(value);
  return /[";\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function ConfigCard({ config, index, catalog, assets, onChange, onRemove, onDuplicate, removable }) {
  const spec = catalog.find((m) => m.id === config.model);
  const set = (key, value) => onChange({ ...config, [key]: value });
  const changeModel = (model) => onChange(newConfig(model, catalog, { id: config.id, symbols: config.symbols, seed: config.seed }));
  const multi = spec.target === "portfolio_or_assets" || spec.target === "portfolio";
  const toggleSymbol = (symbol) =>
    set("symbols", config.symbols.includes(symbol) ? config.symbols.filter((s) => s !== symbol) : [...config.symbols, symbol]);

  return (
    <article className="act-config">
      <div className="act-config-head">
        <strong>Modèle {index + 1}</strong>
        <div>
          <button type="button" className="act-link-btn" onClick={onDuplicate}>Dupliquer</button>
          {removable && (
            <button type="button" className="act-icon-btn" aria-label="Retirer" onClick={onRemove}>×</button>
          )}
        </div>
      </div>
      <Field label="Modèle">
        <select value={config.model} onChange={(e) => changeModel(e.target.value)}>
          {Object.entries(FAMILIES).map(([family, label]) => (
            <optgroup key={family} label={label}>
              {catalog.filter((m) => m.family === family).map((m) => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </optgroup>
          ))}
        </select>
      </Field>
      <p className="act-formula"><code>{spec.formula}</code></p>

      {spec.target === "portfolio_or_assets" && (
        <Field label="Exposition">
          <select value={config.target} onChange={(e) => set("target", e.target.value)}>
            <option value="portfolio">Mon portefeuille</option>
            <option value="assets">Panier d'actifs (poids égaux)</option>
          </select>
        </Field>
      )}
      {spec.target === "asset" && (
        <Field label="Actif (calibration si paramètres vides)">
          <select value={config.symbols[0] || ""} onChange={(e) => set("symbols", [e.target.value])}>
            {assets.map((a) => <option key={a.symbol} value={a.symbol}>{a.symbol} — {a.name}</option>)}
          </select>
        </Field>
      )}
      {multi && (spec.target === "portfolio" || config.target === "assets") && (
        <>
          <p className="act-note">{spec.target === "portfolio" ? "Actifs ajoutés à l'univers :" : "Actifs du panier :"}</p>
          <div className="act-chips">
            {assets.map((a) => (
              <button key={a.symbol} type="button" className={config.symbols.includes(a.symbol) ? "active" : ""} onClick={() => toggleSymbol(a.symbol)}>
                {a.symbol}
              </button>
            ))}
          </div>
        </>
      )}

      <div className="act-filters act-filters-tight">
        {spec.params.map((p) => (
          <Field key={p.name} label={`${p.label}${p.unit === "%" ? " (%)" : ""}`}>
            <input value={config.params[p.name] ?? ""} inputMode="decimal"
                   placeholder={spec.target === "asset" ? "calibré" : ""}
                   onChange={(e) => set("params", { ...config.params, [p.name]: e.target.value })} />
          </Field>
        ))}
        {spec.family === "risk" && (
          <>
            <Field label="Confiance">
              <select value={config.confidence} onChange={(e) => set("confidence", e.target.value)}>
                <option value={0.95}>95 %</option>
                <option value={0.99}>99 %</option>
              </select>
            </Field>
            <Field label="Horizon">
              <select value={config.horizon} onChange={(e) => set("horizon", e.target.value)}>
                <option value={1}>1 jour</option>
                <option value={10}>10 jours</option>
                <option value={20}>20 jours</option>
              </select>
            </Field>
          </>
        )}
        {spec.family === "stochastic" && (
          <>
            <Field label="Horizon (années)">
              <input value={config.horizon_years} onChange={(e) => set("horizon_years", e.target.value)} inputMode="decimal" />
            </Field>
            <Field label="Pas">
              <input value={config.steps} onChange={(e) => set("steps", e.target.value)} inputMode="numeric" />
            </Field>
          </>
        )}
        {spec.family !== "optimization" && (
          <>
            <Field label="Simulations">
              <input value={config.n_simulations} onChange={(e) => set("n_simulations", e.target.value)} inputMode="numeric" />
            </Field>
            <Field label="Graine">
              <input value={config.seed} onChange={(e) => set("seed", e.target.value)} inputMode="numeric" />
            </Field>
          </>
        )}
      </div>
    </article>
  );
}

export default function ModelLabPage() {
  const { portfolios, assetsWithHistory } = useActuarialRefs();
  const [catalog, setCatalog] = useState([]);
  const [configs, setConfigs] = useState([]);
  const [items, setItems] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadHistory = () => actuarialApi("/lab/runs", { limit: 20 }).then(setHistory).catch(() => setHistory([]));

  useEffect(() => {
    actuarialApi("/lab/catalog")
      .then((list) => {
        setCatalog(list);
        setConfigs(["var_historical", "var_parametric", "var_monte_carlo"].map((m) => newConfig(m, list)));
      })
      .catch((err) => setError(err.message));
    loadHistory();
  }, []);

  const run = () => {
    setLoading(true);
    setError("");
    const runs = configs.map((c) => toRequest(c, catalog.find((m) => m.id === c.model), portfolios[0]?.id ?? null));
    postActuarial("/lab/compare", { runs })
      .then((result) => {
        setItems(result);
        loadHistory();
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  };

  const update = (id, next) => setConfigs((list) => list.map((c) => (c.id === id ? next : c)));
  const reloadFromHistory = (entry) => {
    const spec = catalog.find((m) => m.id === entry.model);
    if (!spec || configs.length >= MAX_CONFIGS) return;
    const p = entry.params;
    setConfigs((list) => [
      ...list,
      newConfig(entry.model, catalog, {
        target: p.symbols?.length && spec.target === "portfolio_or_assets" ? "assets" : "portfolio",
        symbols: p.symbols?.length ? p.symbols : ["SPY"],
        confidence: p.confidence ?? 0.95,
        horizon: p.horizon ?? 1,
        lookback: p.lookback ?? 252,
        horizon_years: String(p.horizon_years ?? 1),
        steps: String(p.steps ?? 52),
        n_simulations: String(p.n_simulations ?? 5000),
        seed: p.seed == null ? "" : String(p.seed),
        params: Object.fromEntries(spec.params.map((param) => [param.name, paramToText(param, p.params?.[param.name])])),
      }),
    ]);
  };

  const okItems = (items || []).filter((i) => i.ok);
  const metricRows = [];
  okItems.forEach((item) =>
    item.result.metrics.forEach((m) => {
      if (!metricRows.some((r) => r.label === m.label)) metricRows.push({ label: m.label, kind: m.kind });
    }),
  );
  const cell = (item, label) => item.result.metrics.find((m) => m.label === label);

  const exportCsv = () => {
    const header = ["Indicateur", ...okItems.map((i, k) => `${k + 1}. ${i.result.label}`)];
    const lines = [
      header,
      ["Provenance", ...okItems.map((i) => i.result.data_source)],
      ["Graine", ...okItems.map((i) => i.result.seed ?? "")],
      ...metricRows.map((row) => [row.label, ...okItems.map((i) => cell(i, row.label)?.value ?? "")]),
    ];
    download("actuariat-comparaison.csv", "﻿" + lines.map((l) => l.map(csvCell).join(";")).join("\n"), "text/csv;charset=utf-8");
  };
  const exportJson = () =>
    download("actuariat-comparaison.json", JSON.stringify({ exported_at: new Date().toISOString(), items }, null, 2), "application/json");

  if (!catalog.length) return <Status error={error} loading={!error} />;

  return (
    <>
      <Panel
        title="Configurations à comparer"
        subtitle={`Jusqu'à ${MAX_CONFIGS} modèles, chacun avec ses paramètres. Les modèles d'une même famille sont directement comparables.`}
      >
        <div className="act-configs">
          {configs.map((config, index) => (
            <ConfigCard
              key={config.id}
              config={config}
              index={index}
              catalog={catalog}
              assets={assetsWithHistory}
              removable={configs.length > 1}
              onChange={(next) => update(config.id, next)}
              onRemove={() => setConfigs((list) => list.filter((c) => c.id !== config.id))}
              onDuplicate={() => configs.length < MAX_CONFIGS && setConfigs((list) => [...list, { ...config, id: Math.random().toString(36).slice(2) }])}
            />
          ))}
        </div>
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={run} disabled={loading}>
            {loading ? "Calcul…" : "Lancer et comparer"}
          </button>
          <button type="button" className="act-secondary-btn act-inline-btn" disabled={configs.length >= MAX_CONFIGS}
                  onClick={() => setConfigs((list) => [...list, newConfig("lognormal", catalog)])}>
            + Ajouter un modèle
          </button>
        </div>
      </Panel>

      <Status loading={loading && !items} error={error} />

      {items && (
        <div className={loading ? "act-results act-stale" : "act-results"}>
          {items.filter((i) => !i.ok).map((i, k) => (
            <p key={k} className="banner act-error">{i.request.model} : {i.error}</p>
          ))}
          {okItems.length > 0 && (
            <Panel title="Comparaison des résultats" subtitle="Chaque colonne est un modèle ; « — » si l'indicateur ne s'applique pas.">
              <div className="act-actions act-actions-top">
                <button type="button" className="act-secondary-btn act-inline-btn" onClick={exportCsv}>Exporter CSV</button>
                <button type="button" className="act-secondary-btn act-inline-btn" onClick={exportJson}>Exporter JSON</button>
              </div>
              <div className="table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Indicateur</th>
                      {okItems.map((i, k) => (
                        <th key={k}>{k + 1}. {i.result.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Provenance</td>
                      {okItems.map((i, k) => <td key={k}><SourceBadge source={i.result.data_source} /></td>)}
                    </tr>
                    <tr>
                      <td>Cible</td>
                      {okItems.map((i, k) => <td key={k}>{i.result.target || "—"}</td>)}
                    </tr>
                    {metricRows.map((row) => (
                      <tr key={row.label}>
                        <td><strong>{row.label}</strong></td>
                        {okItems.map((i, k) => {
                          const m = cell(i, row.label);
                          return <td key={k}>{m ? formatValue(m.kind, m.value) : "—"}</td>;
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Panel>
          )}
          <div className="act-lab-grid">
            {okItems.map((i, k) => (
              <Panel key={k} title={`${k + 1}. ${i.result.label}`} subtitle={i.result.histogram_label} source={i.result.data_source}>
                {i.result.histogram ? (
                  <BinsHistogram
                    bins={i.result.histogram}
                    format={(v) => formatValue(i.result.histogram_kind, v)}
                    axisFormat={i.result.histogram_kind === "amount" ? fmtCompact : undefined}
                    unit="Tirages"
                    height={200}
                    colorOf={i.result.marker != null ? (bin) => lossColor(bin, -i.result.marker) : undefined}
                  />
                ) : (
                  <p className="act-empty">Pas de distribution pour ce modèle (voir les poids dans le tableau).</p>
                )}
                <details className="act-assumptions">
                  <summary>Hypothèses et paramètres</summary>
                  <p><code>{i.result.formula}</code></p>
                  <ul>
                    {[...i.result.assumptions, ...i.result.notes].map((a) => <li key={a}>{a}</li>)}
                  </ul>
                  <pre>{JSON.stringify(i.result.params_used, null, 1)}</pre>
                </details>
              </Panel>
            ))}
          </div>
        </div>
      )}

      <Panel title="Historique des calculs" subtitle="Vos 20 derniers calculs actuariels (tous écrans). Paramètres et graine permettent de les rejouer à l'identique.">
        {history.length === 0 ? (
          <p className="act-empty">Aucun calcul enregistré.</p>
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr><th>Date</th><th>Modèle</th><th>Provenance</th><th>Graine</th><th /></tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id}>
                    <td>{new Date(`${h.created_at}Z`).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}</td>
                    <td><strong>{catalog.find((m) => m.id === h.model)?.label || OTHER_RUNS[h.model] || h.model}</strong></td>
                    <td><SourceBadge source={h.data_source} /></td>
                    <td>{h.seed ?? "—"}</td>
                    <td className="act-row-actions">
                      {catalog.some((m) => m.id === h.model) && (
                        <button type="button" className="act-link-btn" onClick={() => reloadFromHistory(h)}>Recharger</button>
                      )}
                      <button type="button" className="act-link-btn" onClick={() => download(`actuariat-calcul-${h.id}.json`, JSON.stringify(h, null, 2), "application/json")}>
                        JSON
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
