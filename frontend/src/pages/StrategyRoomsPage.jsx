import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api.js";
import "./arcade.css";

export default function StrategyRoomsPage() {
  const navigate = useNavigate();
  const [strategies, setStrategies] = useState(null);
  const [assets, setAssets] = useState([]);
  const [strategyKey, setStrategyKey] = useState("");
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api("/salles-de-jeu/strategies")
      .then((list) => {
        setStrategies(list);
        setStrategyKey((cur) => cur || list[0]?.key || "");
      })
      .catch((err) => setError(err.message));
    api("/quotes")
      .then((list) => {
        const actions = list.filter((q) => q.group === "actions");
        setAssets(actions);
        setSymbol((cur) => cur || actions[0]?.symbol || "");
      })
      .catch(() => {});
  }, []);

  async function start() {
    if (!strategyKey || !symbol) return;
    setBusy(true);
    setError("");
    try {
      const state = await api("/salles-de-jeu/strategies/start", {
        method: "POST",
        body: JSON.stringify({ strategy_key: strategyKey, symbol }),
      });
      navigate(`/salles-de-jeu/strategie/${state.run_id}`);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  if (error && !strategies) return <p className="status error">{error}</p>;
  if (!strategies) return <p className="status">Chargement…</p>;

  const active = strategies.find((s) => s.key === strategyKey);

  return (
    <section className="page ag">
      <div className="ag-header">
        <div>
          <p className="ag-prompt">Salles de jeu / Type 2</p>
          <h1>Salle de stratégie</h1>
          <p className="page-lead">
            Choisis une stratégie de trading et un actif réel de la Bourse de Tunis, puis rejoue
            une période historique sans connaître les cours à venir. Tu restes libre de tes
            décisions : si une action ne correspond pas à la stratégie choisie, tu seras juste
            averti·e, et ton score final en tiendra compte.
          </p>
        </div>
      </div>
      {error && <p className="status error">{error}</p>}

      <div className="ag-strategy-pick">
        <div className="ag-strategy-list">
          {strategies.map((s) => (
            <button
              key={s.key}
              className={`ag-strategy-card${s.key === strategyKey ? " active" : ""}`}
              onClick={() => setStrategyKey(s.key)}
            >
              <strong>{s.name}</strong>
              <span>{s.horizon}</span>
            </button>
          ))}
        </div>

        {active && (
          <div className="ag-strategy-detail">
            <h2>{active.name}</h2>
            <p>{active.description}</p>
            <p className="ag-muted">Horizon typique : {active.horizon}</p>

            <label className="trade-field">
              Actif à trader
              <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                {assets.map((a) => (
                  <option key={a.symbol} value={a.symbol}>
                    {a.symbol} — {a.name}
                  </option>
                ))}
              </select>
            </label>

            <button className="ag-btn" disabled={busy || !symbol} onClick={start}>
              {busy ? "Préparation…" : "Démarrer"}
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
