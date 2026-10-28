import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api.js";
import { formatDateTime, formatDecimal, formatSigned, signClass } from "../services/format.js";
import "./trading.css";

const pct = (value) => (value === null || value === undefined ? "—" : `${formatDecimal(value)} %`);

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [risk, setRisk] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/trading/risk")
      .then(setRisk)
      .catch(() => setRisk(null));
  }, []);

  useEffect(() => {
    Promise.all([api("/trading/portfolio"), api("/trading/transactions")])
      .then(([nextPortfolio, nextTransactions]) => {
        setPortfolio(nextPortfolio);
        setTransactions(nextTransactions);
      })
      .catch((err) => setError(err.message));
  }, []);

  const positions = portfolio?.positions || [];
  const unpriced = positions.filter((row) => row.price_error).map((row) => row.symbol);

  return (
    <section className="page trade-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Portefeuille</p>
          <h1>Portefeuille</h1>
          <p className="page-lead">Positions ouvertes valorisées au dernier cours connu.</p>
        </div>
        <Link className="primary-btn" to="/trading">
          Passer un ordre
        </Link>
      </div>
      {error && <p className="banner">Portefeuille indisponible : {error}</p>}
      {!portfolio && !error && <p className="banner">Chargement du portefeuille...</p>}
      {portfolio && !portfolio.valuation_complete && (
        <p className="banner trade-warning">
          Valorisation incomplète : cours indisponible pour {unpriced.join(", ")}. La valeur
          des positions et la valeur totale ne comptent pas ces lignes.
        </p>
      )}

      <div className="stat-grid">
        <article className="stat-card">
          <p>Cash</p>
          <strong>{portfolio ? formatDecimal(portfolio.cash) : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Valeur des positions</p>
          <strong>{portfolio ? formatDecimal(portfolio.positions_value) : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Valeur totale</p>
          <strong>{portfolio ? formatDecimal(portfolio.total_value) : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Positions ouvertes</p>
          <strong>{portfolio ? positions.length : "—"}</strong>
        </article>
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Performance et risque</h2>
            <p>
              {risk
                ? `Calculés sur les proportions actuelles du portefeuille et ${risk.days_used} jours d'historique de prix (simulation historique).`
                : "Indicateurs indisponibles pour le moment."}
            </p>
          </div>
        </div>
        <div className="stat-grid risk-grid">
          <article className="stat-card">
            <p>Rendement total</p>
            <strong className={risk ? signClass(risk.total_return_pct) : ""}>
              {risk ? `${formatSigned(risk.total_return_pct)} %` : "—"}
            </strong>
            <em>{risk ? `depuis ${formatDecimal(risk.initial_capital, 0)} de capital` : ""}</em>
          </article>
          <article className="stat-card">
            <p>Gain réalisé</p>
            <strong className={risk ? signClass(risk.realized_pnl_total) : ""}>
              {risk ? formatSigned(risk.realized_pnl_total) : "—"}
            </strong>
            <em>sur les ventes effectuées</em>
          </article>
          <article className="stat-card">
            <p>Volatilité annualisée</p>
            <strong>{risk ? pct(risk.volatility_pct) : "—"}</strong>
            <em>amplitude des variations</em>
          </article>
          <article className="stat-card">
            <p>VaR 95 % sur 1 jour</p>
            <strong>{risk ? pct(risk.var_95_pct) : "—"}</strong>
            <em>{risk && risk.var_95_amount ? `perte dépassée 5 jours sur 100 : ${formatDecimal(risk.var_95_amount)}` : ""}</em>
          </article>
          <article className="stat-card">
            <p>Drawdown maximal</p>
            <strong>{risk ? pct(risk.max_drawdown_pct) : "—"}</strong>
            <em>{risk && risk.max_drawdown_amount ? `pire chute depuis un sommet : ${formatDecimal(risk.max_drawdown_amount)}` : ""}</em>
          </article>
        </div>
      </article>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Positions ouvertes</h2>
            <p>Gain ou perte latent par rapport au prix moyen d'achat.</p>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Instrument</th>
                <th>Quantité</th>
                <th>Prix moyen</th>
                <th>Prix actuel</th>
                <th>Valeur</th>
                <th>+/- latent</th>
                <th>+/- %</th>
              </tr>
            </thead>
            <tbody>
              {portfolio && positions.length === 0 && (
                <tr>
                  <td colSpan="7">
                    Aucune position ouverte. <Link to="/trading">Passez un premier ordre</Link>.
                  </td>
                </tr>
              )}
              {positions.map((row) => (
                <tr key={row.symbol}>
                  <td>
                    <strong>{row.symbol}</strong>
                    <span>{row.name}</span>
                  </td>
                  <td>{formatDecimal(row.quantity, 0)}</td>
                  <td>{formatDecimal(row.average_buy_price)}</td>
                  <td>
                    {row.price_error ? <span title={row.price_error}>Cours indisponible</span> : formatDecimal(row.current_price)}
                  </td>
                  <td>{formatDecimal(row.market_value)}</td>
                  <td className={signClass(row.unrealized_pnl)}>{formatSigned(row.unrealized_pnl)}</td>
                  <td className={signClass(row.unrealized_pnl_pct)}>
                    {row.unrealized_pnl_pct === null ? "—" : `${formatSigned(row.unrealized_pnl_pct)} %`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Historique des transactions</h2>
            <p>Les 50 derniers ordres, du plus récent au plus ancien.</p>
          </div>
        </div>
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Instrument</th>
                <th>Sens</th>
                <th>Quantité</th>
                <th>Prix d'exécution</th>
                <th>Stop loss</th>
                <th>Take profit</th>
                <th>Gain réalisé</th>
              </tr>
            </thead>
            <tbody>
              {portfolio && transactions.length === 0 && (
                <tr>
                  <td colSpan="8">Aucune transaction pour le moment.</td>
                </tr>
              )}
              {transactions.map((row) => (
                <tr key={row.id}>
                  <td>{formatDateTime(row.executed_at)}</td>
                  <td>
                    <strong>{row.symbol}</strong>
                  </td>
                  <td className={row.side === "buy" ? "up" : "down"}>
                    {row.side === "buy" ? "Achat" : "Vente"}
                  </td>
                  <td>{formatDecimal(row.quantity, 0)}</td>
                  <td>{formatDecimal(row.price)}</td>
                  <td>{formatDecimal(row.stop_loss)}</td>
                  <td>{formatDecimal(row.take_profit)}</td>
                  <td className={signClass(row.realized_pnl)}>
                    {row.realized_pnl === null || row.realized_pnl === undefined ? "—" : formatSigned(row.realized_pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
