import { useEffect, useState } from "react";
import { CashFlowChart, SimpleLineChart, SourceBadge } from "../../components/actuarial/ActuarialCharts.jsx";
import { Conventions, Field, Kpi, Panel, Status } from "../../components/actuarial/Controls.jsx";
import { actuarialApi, fmtAmount, fmtNum, fmtPct, parseNumber, percentToFraction, postActuarial } from "../../services/actuarial.js";

const SCENARIO_LABELS = {
  base: "Courbe de départ",
  "parallel+": "Hausse parallèle",
  "parallel-": "Baisse parallèle",
  "steepening+": "Pentification",
  "steepening-": "Pentification inversée",
  "flattening+": "Aplatissement",
  "flattening-": "Aplatissement inversé",
  "butterfly+": "Papillon (ailes ↑, ventre ↓)",
  "butterfly-": "Papillon (ailes ↓, ventre ↑)",
};

const CONVENTIONS = [
  "Coupon = nominal × taux / fréquence ; dates de coupon obtenues en reculant depuis l'échéance.",
  "Temps des flux en années selon la base (ACT/365, ACT/360, 30/360) ; actualisation périodique DF = (1 + y/f)^(−f·t).",
  "Prix plein = somme des flux actualisés ; prix pied de coupon = prix plein − coupon couru (prorata de la période en cours).",
  "YTM : taux qui égalise prix plein calculé et prix observé (méthode de Brent).",
  "Duration de Macaulay = Σ t·VA / P ; modifiée = Macaulay / (1 + y/f) ; DV01 = duration modifiée × P × 0,0001.",
  "Convexité = Σ CF·t·(t + 1/f)·DF / (P·(1 + y/f)²) ; ΔP/P ≈ −Dmod·Δy + ½·C·Δy².",
  "Déformations : pentification pivot 5 ans (court terme −Δ, long terme +Δ), papillon : ventre 2-10 ans opposé aux ailes. Courbe plate au YTM si aucune courbe n'est saisie.",
  "Les ETF obligataires du référentiel n'ont ni coupon ni échéance uniques : aucune caractéristique n'est inventée pour eux.",
];

const today = () => new Date().toISOString().slice(0, 10);

function BondAnalysis({ analysis, source }) {
  const a = analysis;
  return (
    <>
      <div className="stat-grid act-kpis">
        <Kpi label="Rendement actuariel (YTM)" value={fmtPct(a.ytm)} note={`règlement le ${a.settlement}`} />
        <Kpi label="Prix pied de coupon" value={fmtAmount(a.clean_price)} note={`plein ${fmtAmount(a.dirty_price)} · couru ${fmtAmount(a.accrued_interest)}`} />
        <Kpi label="Duration de Macaulay" value={`${fmtNum(a.macaulay_duration, 3)} ans`} note={`modifiée ${fmtNum(a.modified_duration, 3)}`} />
        <Kpi label="Convexité" value={fmtNum(a.convexity, 2)} note={`DV01 ${fmtNum(a.dv01, 4)} par point de base`} />
      </div>
      <div className="act-grid">
        <Panel title="Flux futurs" subtitle={`${a.cash_flows.length} flux, actualisés au YTM.`} source={source}>
          <CashFlowChart flows={a.cash_flows} />
        </Panel>
        <Panel title="Relation prix-rendement" subtitle="Prix plein ; trait pointillé : rendement actuel. La courbure est la convexité.">
          <SimpleLineChart data={a.price_yield_curve} x="yield" y="price" name="Prix plein" xFormat={fmtPct}
                           yFormat={(v) => fmtNum(v, 2)} marker={a.ytm} />
        </Panel>
      </div>
      <div className="act-grid">
        <Panel title="Sensibilité aux chocs parallèles" subtitle="Réévaluation complète comparée aux approximations.">
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Choc</th>
                  <th>Prix</th>
                  <th>Variation</th>
                  <th>Duration seule</th>
                  <th>Duration + convexité</th>
                  <th>Erreur</th>
                </tr>
              </thead>
              <tbody>
                {a.parallel_sensitivity.map((r) => (
                  <tr key={r.shift_bp}>
                    <td><strong>{r.shift_bp > 0 ? "+" : ""}{r.shift_bp} pb</strong></td>
                    <td>{fmtNum(r.price, 3)}</td>
                    <td className={r.change_pct >= 0 ? "up" : "down"}>{fmtPct(r.change_pct)}</td>
                    <td>{fmtNum(r.duration_approx, 3)}</td>
                    <td>{fmtNum(r.duration_convexity_approx, 3)}</td>
                    <td>{fmtNum(r.approx_error, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel
          title={`Déformations de la courbe (± ${a.shock_bp} pb)`}
          subtitle={a.curve_source === "flat_at_ytm" ? "Courbe de départ plate au YTM (hypothèse)." : "Courbe de départ saisie."}
          source="user_assumption"
        >
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Scénario</th>
                  <th>Prix plein</th>
                  <th>Variation</th>
                </tr>
              </thead>
              <tbody>
                {a.curve_scenarios.map((r) => (
                  <tr key={r.scenario}>
                    <td><strong>{SCENARIO_LABELS[r.scenario] || r.scenario}</strong></td>
                    <td>{fmtNum(r.price, 3)}</td>
                    <td className={r.change_pct > 0 ? "up" : r.change_pct < 0 ? "down" : ""}>{fmtPct(r.change_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
      <Panel title="Échéancier détaillé">
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>t (ans)</th>
                <th>Coupon</th>
                <th>Principal</th>
                <th>Facteur d'actualisation</th>
                <th>Valeur actuelle</th>
              </tr>
            </thead>
            <tbody>
              {a.cash_flows.map((f) => (
                <tr key={f.date}>
                  <td>{f.date}</td>
                  <td>{fmtNum(f.time, 4)}</td>
                  <td>{fmtAmount(f.coupon)}</td>
                  <td>{fmtAmount(f.principal)}</td>
                  <td>{fmtNum(f.discount_factor, 6)}</td>
                  <td>{fmtAmount(f.present_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}

export default function FixedIncomePage() {
  const [bonds, setBonds] = useState([]);
  const [detail, setDetail] = useState(null);
  const [bond, setBond] = useState({
    face_value: "100",
    coupon_rate: "4",
    coupon_frequency: 2,
    maturity_date: "2036-05-15",
    issue_date: "",
    day_count: "ACT/365",
    settlement_date: today(),
    mode: "ytm",
    value: "4,5",
    shock_bp: "100",
  });
  const [curve, setCurve] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    actuarialApi("/fixed-income/bonds").then(setBonds).catch((err) => setError(err.message));
  }, []);

  const openBond = (assetId) => {
    setDetail(null);
    actuarialApi(`/fixed-income/${assetId}`).then(setDetail).catch((err) => setError(err.message));
  };

  const set = (key) => (e) => setBond((b) => ({ ...b, [key]: e.target.value }));

  const analyze = () => {
    setLoading(true);
    setError("");
    const body = {
      bond: {
        face_value: parseNumber(bond.face_value),
        coupon_rate: percentToFraction(bond.coupon_rate),
        coupon_frequency: Number(bond.coupon_frequency),
        maturity_date: bond.maturity_date,
        issue_date: bond.issue_date || null,
        day_count: bond.day_count,
      },
      settlement_date: bond.settlement_date || null,
      shock_bp: parseNumber(bond.shock_bp) ?? 100,
      ...(bond.mode === "ytm" ? { ytm: percentToFraction(bond.value) } : { clean_price: parseNumber(bond.value) }),
    };
    if (curve.length) {
      body.curve_maturities = curve.map((c) => parseNumber(c.maturity));
      body.curve_rates = curve.map((c) => percentToFraction(c.rate));
    }
    postActuarial("/fixed-income/analyze", body)
      .then(setAnalysis)
      .catch((err) => {
        setAnalysis(null);
        setError(err.message);
      })
      .finally(() => setLoading(false));
  };

  return (
    <>
      <Panel
        title="Obligations du référentiel"
        subtitle="Statistiques calculées sur les cours importés. Cliquez sur une ligne pour le détail."
        source="real_market_data"
      >
        <div className="table-scroll">
          <table className="data-table act-clickable">
            <thead>
              <tr>
                <th>Actif</th>
                <th>Dernier cours</th>
                <th>Rendement annualisé</th>
                <th>Volatilité</th>
                <th>Drawdown max</th>
                <th>Caractéristiques</th>
                <th>Coupons reçus</th>
              </tr>
            </thead>
            <tbody>
              {bonds.map((b) => (
                <tr key={b.asset_id} onClick={() => openBond(b.asset_id)} className={detail?.asset_id === b.asset_id ? "act-row-selected" : ""}>
                  <td>
                    <strong>{b.symbol}</strong>
                    <span>{b.name}</span>
                  </td>
                  <td>{b.market ? fmtAmount(b.market.last_price) : "—"}</td>
                  <td className={b.market?.annualized_return >= 0 ? "up" : "down"}>{fmtPct(b.market?.annualized_return)}</td>
                  <td>{fmtPct(b.market?.annualized_volatility)}</td>
                  <td>{fmtPct(b.market?.max_drawdown)}</td>
                  <td>{b.has_terms ? "Renseignées" : "Non disponibles"}</td>
                  <td>{b.coupons.count ? `${b.coupons.count} · ${fmtAmount(b.coupons.total)}` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {detail && (
          <div className="act-detail">
            <h3 className="act-subtitle">
              {detail.symbol} — {detail.name}
            </h3>
            {detail.message && <p className="banner act-warning">{detail.message}</p>}
            {detail.terms && (
              <p className="act-note">
                Coupon {fmtPct(detail.terms.coupon_rate)} · {detail.terms.coupon_frequency} fois/an · échéance{" "}
                {detail.terms.maturity_date} · nominal {fmtAmount(detail.terms.face_value)} · source : {detail.terms.source}
              </p>
            )}
            {detail.analysis && <BondAnalysis analysis={detail.analysis} source="real_market_data" />}
          </div>
        )}
      </Panel>

      <Panel
        title="Obligation théorique"
        subtitle="Saisissez les caractéristiques contractuelles d'une obligation à taux fixe."
        source="user_assumption"
      >
        <div className="act-filters">
          <Field label="Nominal">
            <input value={bond.face_value} onChange={set("face_value")} inputMode="decimal" />
          </Field>
          <Field label="Taux de coupon (% / an)">
            <input value={bond.coupon_rate} onChange={set("coupon_rate")} inputMode="decimal" />
          </Field>
          <Field label="Fréquence">
            <select value={bond.coupon_frequency} onChange={set("coupon_frequency")}>
              <option value={1}>Annuelle</option>
              <option value={2}>Semestrielle</option>
              <option value={4}>Trimestrielle</option>
              <option value={12}>Mensuelle</option>
            </select>
          </Field>
          <Field label="Échéance">
            <input type="date" value={bond.maturity_date} onChange={set("maturity_date")} />
          </Field>
          <Field label="Émission (facultatif)">
            <input type="date" value={bond.issue_date} onChange={set("issue_date")} />
          </Field>
          <Field label="Base de calcul">
            <select value={bond.day_count} onChange={set("day_count")}>
              <option>ACT/365</option>
              <option>ACT/360</option>
              <option>30/360</option>
            </select>
          </Field>
          <Field label="Date de règlement">
            <input type="date" value={bond.settlement_date} onChange={set("settlement_date")} />
          </Field>
          <Field label="Donnée connue">
            <select value={bond.mode} onChange={set("mode")}>
              <option value="ytm">Rendement actuariel (%)</option>
              <option value="price">Prix pied de coupon</option>
            </select>
          </Field>
          <Field label={bond.mode === "ytm" ? "Rendement (%)" : "Prix pied de coupon"}>
            <input value={bond.value} onChange={set("value")} inputMode="decimal" />
          </Field>
          <Field label="Amplitude des déformations (pb)">
            <input value={bond.shock_bp} onChange={set("shock_bp")} inputMode="decimal" />
          </Field>
        </div>
        <details className="act-calibrate">
          <summary>Courbe des taux de départ (facultatif, sinon plate au YTM)</summary>
          {curve.map((row, i) => (
            <div key={i} className="act-basket-row">
              <input value={row.maturity} aria-label="Maturité (ans)" placeholder="Maturité (ans)" inputMode="decimal"
                     onChange={(e) => setCurve((c) => c.map((r, j) => (j === i ? { ...r, maturity: e.target.value } : r)))} />
              <input value={row.rate} aria-label="Taux (%)" placeholder="Taux (%)" inputMode="decimal"
                     onChange={(e) => setCurve((c) => c.map((r, j) => (j === i ? { ...r, rate: e.target.value } : r)))} />
              <button type="button" className="act-icon-btn" aria-label="Retirer" onClick={() => setCurve((c) => c.filter((_, j) => j !== i))}>
                ×
              </button>
            </div>
          ))}
          <button type="button" className="act-link-btn" onClick={() => setCurve((c) => [...c, { maturity: "", rate: "" }])}>
            + Ajouter un point
          </button>
        </details>
        <div className="act-actions">
          <button type="button" className="primary-btn" onClick={analyze} disabled={loading}>
            {loading ? "Calcul…" : "Analyser"}
          </button>
        </div>
      </Panel>

      <Status loading={loading && !analysis} error={error} />
      {analysis && <BondAnalysis analysis={analysis} source="user_assumption" />}
      <Conventions items={CONVENTIONS} />
    </>
  );
}
