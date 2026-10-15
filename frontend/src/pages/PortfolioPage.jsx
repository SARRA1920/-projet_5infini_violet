import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../services/api.js";
import { formatDateTime, formatDecimal, formatSigned, signClass } from "../services/format.js";
import "./trading.css";

export default function PortfolioPage() {
  const [portfolio, setPortfolio] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [error, setError] = useState("");

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
              </tr>
            </thead>
            <tbody>
              {portfolio && transactions.length === 0 && (
                <tr>
                  <td colSpan="7">Aucune transaction pour le moment.</td>
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
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
