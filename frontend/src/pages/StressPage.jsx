import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import { formatDecimal } from "../services/format.js";
import "./trading.css";

const SHOCKS = [
  { id: "credit", label: "Choc crédit" },
  { id: "real_estate", label: "Choc immobilier" },
];

const TYPE_LABEL = {
  conventional: "Conventionnelle",
  non_conventional: "Non conventionnelle",
};

function pct(value) {
  if (value === null || value === undefined) return "—";
  return `${formatDecimal(value)} %`;
}

export default function StressPage() {
  const [shock, setShock] = useState("real_estate");
  const [intensity, setIntensity] = useState("10");
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const rate = intensity.trim().replace(",", ".");
    if (rate === "" || Number.isNaN(Number(rate))) return undefined;
    let cancelled = false;
    setPending(true);
    api("/stress/run", {
      method: "POST",
      body: JSON.stringify({ shock, intensity: rate }),
    })
      .then((data) => {
        if (!cancelled) {
          setResult(data);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setPending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [shock, intensity]);

  const rows = result?.results ?? [];

  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Intelligence</p>
          <h1>Stress Testing</h1>
          <p className="page-lead">
            Choc sur les banques synthétiques. Les fonds propres absorbent la perte, le ratio est recalculé. Rien n'est enregistré en base.
          </p>
        </div>
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Scénario</h2>
            <p>Le seuil de solvabilité est de 8 % des prêts.</p>
          </div>
        </div>
        <div className="ranges">
          {SHOCKS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={item.id === shock ? "range active" : "range"}
              onClick={() => setShock(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <label className="trade-field" style={{ marginTop: "0.8rem", maxWidth: "16rem" }}>
          <span>Intensité (%)</span>
          <input
            inputMode="decimal"
            value={intensity}
            onChange={(event) => setIntensity(event.target.value)}
          />
        </label>
        {error && <p className="trade-error">{error}</p>}
      </article>

      <div className="stat-grid">
        <article className="stat-card">
          <p>Banques</p>
          <strong>{rows.length || "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Sous le seuil</p>
          <strong className={result && result.below_count > 0 ? "down" : ""}>
            {result ? result.below_count : "—"}
          </strong>
        </article>
        <article className="stat-card">
          <p>Intensité retenue</p>
          <strong>{result ? `${formatDecimal(result.intensity)} %` : pending ? "…" : "—"}</strong>
        </article>
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Ratio avant et après le choc</h2>
            <p>
              {shock === "credit"
                ? "Une part des prêts fait défaut. La perte vaut prêts × intensité."
                : "La part immobilière des prêts perd de la valeur. La perte vaut prêts × part × intensité."}
            </p>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Banque</th>
                <th>Type</th>
                <th>Perte</th>
                <th>Fonds propres après</th>
                <th>Ratio avant</th>
                <th>Ratio après</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr>
                  <td colSpan="6">{pending ? "Calcul…" : "Aucune banque en base."}</td>
                </tr>
              )}
              {rows.map((row) => (
                <tr key={row.name}>
                  <td>
                    <strong>{row.name}</strong>
                  </td>
                  <td>{TYPE_LABEL[row.bank_type] || row.bank_type}</td>
                  <td>{formatDecimal(row.loss, 0)}</td>
                  <td className={String(row.equity_after).startsWith("-") ? "down" : ""}>
                    {formatDecimal(row.equity_after, 0)}
                  </td>
                  <td>{pct(row.ratio_before)}</td>
                  <td className={row.below_threshold ? "down" : ""}>{pct(row.ratio_after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
