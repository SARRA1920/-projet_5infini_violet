// Éléments de formulaire et de mise en page communs aux écrans Actuariat.
import { SourceBadge } from "./ActuarialCharts.jsx";

export function Field({ label, hint, children }) {
  return (
    <label className="act-field">
      {label}
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

export function Kpi({ label, value, note, tone = "" }) {
  return (
    <article className="stat-card">
      <p>{label}</p>
      <strong className={tone}>{value}</strong>
      <em>{note}</em>
    </article>
  );
}

export function Panel({ title, subtitle, source, children, className = "" }) {
  return (
    <article className={`panel ${className}`}>
      <div className="panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {source && <SourceBadge source={source} />}
      </div>
      {children}
    </article>
  );
}

export function Status({ loading, error, warnings = [] }) {
  return (
    <>
      {error && <p className="banner act-error">{error}</p>}
      {loading && <p className="banner">Calcul en cours…</p>}
      {warnings.map((w) => (
        <p key={w} className="banner act-warning">
          {w}
        </p>
      ))}
    </>
  );
}

export function Conventions({ items }) {
  return (
    <details className="panel act-conventions">
      <summary>Hypothèses et conventions de calcul</summary>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </details>
  );
}
