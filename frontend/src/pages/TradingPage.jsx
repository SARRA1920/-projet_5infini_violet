import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import { formatDecimal } from "../services/format.js";
import "./trading.css";

const SIDES = [
  { id: "buy", label: "Acheter" },
  { id: "sell", label: "Vendre" },
];

// Nos catégories d'actifs
const ASSET_GROUPS = [
  { id: "actions", label: "Actions" },
  { id: "obligations", label: "Obligations" },
  { id: "devises", label: "Devises" },
  { id: "matieres", label: "Matières Premières" },
];

// Accepte la virgule française ; reste une chaîne envoyée telle quelle.
function decimalText(value) {
  return value.trim().replace(",", ".");
}

export default function TradingPage() {
  const [quotes, setQuotes] = useState([]);
  const [portfolio, setPortfolio] = useState(null);
  const [activeGroup, setActiveGroup] = useState("actions"); // Onglet actif par défaut
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState("buy");
  const [quantity, setQuantity] = useState("");
  const [stopLoss, setStopLoss] = useState("");
  const [takeProfit, setTakeProfit] = useState("");
  const [pending, setPending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function loadPortfolio() {
    return api("/trading/portfolio")
      .then(setPortfolio)
      .catch((err) => setNotice(`Portefeuille indisponible : ${err.message}`));
  }

  useEffect(() => {
    api("/quotes")
      .then((rows) => {
        setQuotes(rows);
        // Sélectionner le premier actif de la catégorie "actions" par défaut
        const firstStock = rows.find((row) => row.group === "actions");
        if (firstStock) setSymbol(firstStock.symbol);
      })
      .catch((err) => setNotice(`Cours indisponibles : ${err.message}`));
    loadPortfolio();
  }, []);

  // Quand on change d'onglet, on met à jour le symbole sélectionné
  function changeGroup(group_id) {
    setActiveGroup(group_id);
    const firstInGroup = quotes.find((row) => row.group === group_id);
    if (firstInGroup) setSymbol(firstInGroup.symbol);
  }

  function chooseSide(next) {
    setSide(next);
    if (next === "sell") {
      setStopLoss("");
      setTakeProfit("");
    }
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setResult(null);
    if (!quantity.trim()) {
      setError("Indiquez une quantité.");
      return;
    }
    const body = { symbol, side, quantity: decimalText(quantity) };
    if (side === "buy") {
      if (stopLoss.trim()) body.stop_loss = decimalText(stopLoss);
      if (takeProfit.trim()) body.take_profit = decimalText(takeProfit);
    }
    setPending(true);
    try {
      const transaction = await api("/trading/orders", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setResult(transaction);
      setQuantity("");
      setStopLoss("");
      setTakeProfit("");
      await loadPortfolio();
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  // Filtrer les actifs pour ne montrer que ceux de l'onglet actif
  const filteredQuotes = quotes.filter((row) => row.group === activeGroup);
  const selected = quotes.find((row) => row.symbol === symbol);
  const held = portfolio?.positions.find((row) => row.symbol === symbol);

  return (
    <section className="page trade-page">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Trading</p>
          <h1>Trading</h1>
          <p className="page-lead">Passez un ordre au marché, exécuté au dernier cours connu.</p>
        </div>
      </div>
      {notice && <p className="banner">{notice}</p>}

      <div className="stat-grid">
        <article className="stat-card">
          <p>Cash disponible</p>
          <strong>{portfolio ? formatDecimal(portfolio.cash) : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Valeur totale</p>
          <strong>{portfolio ? formatDecimal(portfolio.total_value) : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Dernier cours {symbol}</p>
          <strong>{selected ? selected.last : "—"}</strong>
        </article>
        <article className="stat-card">
          <p>Quantité détenue</p>
          <strong>{held ? formatDecimal(held.quantity, 0) : "0"}</strong>
        </article>
      </div>

      <article className="panel">
        <div className="panel-head">
          <div>
            <h2>Nouvel ordre</h2>
            <p>Stop loss et take profit sont enregistrés avec l'achat, sans exécution automatique.</p>
          </div>
        </div>

        <div className="ranges trade-tabs">
          {ASSET_GROUPS.map((group) => (
            <button
              key={group.id}
              type="button"
              className={group.id === activeGroup ? "range active" : "range"}
              onClick={() => changeGroup(group.id)}
            >
              {group.label}
            </button>
          ))}
        </div>

        <form className="trade-form" onSubmit={onSubmit}>
          <label className="trade-field">
            <span>Actif</span>
            <select
              value={symbol}
              onChange={(event) => setSymbol(event.target.value)}
              disabled={filteredQuotes.length === 0}
            >
              {filteredQuotes.map((row) => (
                <option key={row.symbol} value={row.symbol}>
                  {row.symbol} — {row.name} · {row.last}
                </option>
              ))}
            </select>
          </label>
          <div className="trade-field">
            <span>Sens</span>
            <div className="ranges">
              {SIDES.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={item.id === side ? "range active" : "range"}
                  onClick={() => chooseSide(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
          <label className="trade-field">
            <span>Quantité</span>
            <input
              inputMode="decimal"
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              placeholder="ex. 10"
            />
          </label>
          <label className="trade-field">
            <span>Stop loss (optionnel)</span>
            <input
              inputMode="decimal"
              value={stopLoss}
              onChange={(event) => setStopLoss(event.target.value)}
              disabled={side === "sell"}
              placeholder={side === "sell" ? "Achat uniquement" : "Inférieur au cours actuel"}
            />
          </label>
          <label className="trade-field">
            <span>Take profit (optionnel)</span>
            <input
              inputMode="decimal"
              value={takeProfit}
              onChange={(event) => setTakeProfit(event.target.value)}
              disabled={side === "sell"}
              placeholder={side === "sell" ? "Achat uniquement" : "Supérieur au cours actuel"}
            />
          </label>
          <button className="primary-btn" type="submit" disabled={pending || !symbol}>
            {pending ? "Envoi..." : side === "buy" ? "Acheter" : "Vendre"}
          </button>
        </form>
        {error && <p className="trade-error">{error}</p>}
        {result && (
          <p className="trade-ok">
            Ordre exécuté : {result.side === "buy" ? "achat" : "vente"} de{" "}
            {formatDecimal(result.quantity, 0)} {result.symbol} au prix de{" "}
            {formatDecimal(result.price)}.
          </p>
        )}
      </article>
    </section>
  );
}
