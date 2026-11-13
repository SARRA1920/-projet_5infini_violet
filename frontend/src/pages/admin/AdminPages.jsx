import { useMemo, useState } from "react";
import {
  assets as seedAssets,
  audit as seedAudit,
  courses as seedCourses,
  models as seedModels,
  news as seedNews,
  results as seedResults,
  scenarios as seedScenarios,
  usage,
  users as seedUsers,
} from "../../data/adminData.js";

function Page({ kicker, title, lead, children }) {
  return (
    <section className="page">
      <div className="page-head">
        <div>
          <p className="page-kicker">{kicker}</p>
          <h1>{title}</h1>
          <p className="page-lead">{lead}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

export function AdminDashboard() {
  return (
    <Page kicker="Administration" title="Vue globale" lead="Activité de la plateforme, chiffres de démonstration.">
      <div className="stat-grid">
        <article className="stat-card"><p>Utilisateurs</p><strong>128</strong><em className="up">14 actifs aujourd'hui</em></article>
        <article className="stat-card"><p>Ordres du jour</p><strong>86</strong><em className="up">+12 %</em></article>
        <article className="stat-card"><p>Modules ouverts</p><strong>5</strong><em>Trading en tête</em></article>
        <article className="stat-card"><p>Simulations</p><strong>3</strong><em>2 scénarios de stress</em></article>
      </div>
      <article className="panel" style={{ marginTop: "0.8rem" }}>
        <h2>Usage des modules</h2>
        <div className="bars">
          {usage.map((item) => (
            <div className="bar-row" key={item.label}>
              <span>{item.label}</span>
              <div className="bar-track"><span style={{ width: `${item.value}%` }} /></div>
              <b>{item.value}</b>
            </div>
          ))}
        </div>
      </article>
    </Page>
  );
}

export function AdminUsers() {
  const [rows, setRows] = useState(seedUsers);
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("tous");
  const [state, setState] = useState("tous");
  const [selected, setSelected] = useState(seedUsers[0]);

  const visible = useMemo(
    () =>
      rows.filter((row) => {
        const text = `${row.name} ${row.email}`.toLowerCase();
        const okQuery = text.includes(query.trim().toLowerCase());
        const okRole = role === "tous" || row.role === role;
        const okState = state === "tous" || (state === "actif" ? row.active : !row.active);
        return okQuery && okRole && okState;
      }),
    [rows, query, role, state],
  );

  function patch(id, change) {
    setRows((current) => current.map((row) => (row.id === id ? { ...row, ...change } : row)));
    setSelected((current) => (current?.id === id ? { ...current, ...change } : current));
  }

  return (
    <Page kicker="Administration" title="Utilisateurs" lead="Recherche, rôle, activation et performances.">
      <div className="admin-tools">
        <input placeholder="Nom ou e-mail" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select value={role} onChange={(event) => setRole(event.target.value)}>
          <option value="tous">Tous les rôles</option>
          <option value="user">Trader</option>
          <option value="admin">Admin</option>
        </select>
        <select value={state} onChange={(event) => setState(event.target.value)}>
          <option value="tous">Tous les états</option>
          <option value="actif">Actifs</option>
          <option value="inactif">Désactivés</option>
        </select>
      </div>
      <div className="split">
        <article className="panel">
          <table className="data-table">
            <thead>
              <tr><th>Nom</th><th>Rôle</th><th>État</th><th></th></tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <tr key={row.id} onClick={() => setSelected(row)}>
                  <td><strong>{row.name}</strong><span>{row.email}</span></td>
                  <td>{row.role === "admin" ? "Admin" : "Trader"}</td>
                  <td><span className={row.active ? "tag" : "tag off"}>{row.active ? "Actif" : "Désactivé"}</span></td>
                  <td>
                    <button type="button" className="mini-btn" onClick={() => patch(row.id, { role: row.role === "admin" ? "user" : "admin" })}>Rôle</button>{" "}
                    <button type="button" className="mini-btn" onClick={() => patch(row.id, { active: !row.active })}>{row.active ? "Désactiver" : "Activer"}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
        {selected && (
          <article className="panel">
            <h2>{selected.name}</h2>
            <p className="page-lead">Inscrit le {selected.joined}</p>
            <p>Cash {selected.cash}</p>
            <p>Performance {selected.pnl}</p>
            <p>Ordres {selected.orders}</p>
          </article>
        )}
      </div>
    </Page>
  );
}

export function AdminMarkets() {
  const [rows, setRows] = useState(seedAssets);
  const [feeds, setFeeds] = useState(seedNews);
  const [symbol, setSymbol] = useState("");

  return (
    <Page kicker="Administration" title="Marchés et actualités" lead="Actifs et sources. L'activation reste locale à cet écran.">
      <div className="admin-tools">
        <input placeholder="Nouveau symbole" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
        <button
          type="button"
          onClick={() => {
            if (!symbol.trim()) return;
            setRows((current) => [...current, { id: Date.now(), symbol: symbol.trim().toUpperCase(), name: "Ajout manuel", type: "Action", source: "Manuel", active: true }]);
            setSymbol("");
          }}
        >
          Ajouter
        </button>
      </div>
      <article className="panel">
        <h2>Actifs</h2>
        <table className="data-table">
          <thead><tr><th>Symbole</th><th>Type</th><th>Source</th><th></th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td><strong>{row.symbol}</strong><span>{row.name}</span></td>
                <td>{row.type}</td>
                <td>{row.source}</td>
                <td><button type="button" className="mini-btn" onClick={() => setRows((current) => current.map((item) => item.id === row.id ? { ...item, active: !item.active } : item))}>{row.active ? "Désactiver" : "Activer"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
      <article className="panel" style={{ marginTop: "0.8rem" }}>
        <h2>Actualités</h2>
        <table className="data-table">
          <thead><tr><th>Titre</th><th>Source</th><th></th></tr></thead>
          <tbody>
            {feeds.map((row) => (
              <tr key={row.id}>
                <td>{row.title}</td>
                <td>{row.source}</td>
                <td><button type="button" className="mini-btn" onClick={() => setFeeds((current) => current.map((item) => item.id === row.id ? { ...item, active: !item.active } : item))}>{row.active ? "Désactiver" : "Activer"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}

export function AdminFormation() {
  const [rows, setRows] = useState(seedCourses);
  const [title, setTitle] = useState("");
  const [kind, setKind] = useState("Cours");

  return (
    <Page kicker="Administration" title="Formation" lead="Cours, exercices, quiz et défis. Statut brouillon ou publié.">
      <div className="admin-tools">
        <input placeholder="Titre" value={title} onChange={(event) => setTitle(event.target.value)} />
        <select value={kind} onChange={(event) => setKind(event.target.value)}>
          <option>Cours</option>
          <option>Exercice</option>
          <option>Quiz</option>
          <option>Défi</option>
        </select>
        <button type="button" onClick={() => { if (!title.trim()) return; setRows((current) => [...current, { id: Date.now(), title: title.trim(), kind, status: "Brouillon" }]); setTitle(""); }}>Ajouter</button>
      </div>
      <article className="panel">
        <table className="data-table">
          <thead><tr><th>Titre</th><th>Type</th><th>Statut</th><th></th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.title}</td>
                <td>{row.kind}</td>
                <td><span className={row.status === "Publié" ? "tag" : "tag off"}>{row.status}</span></td>
                <td><button type="button" className="mini-btn" onClick={() => setRows((current) => current.map((item) => item.id === row.id ? { ...item, status: item.status === "Publié" ? "Brouillon" : "Publié" } : item))}>Changer le statut</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}

export function AdminScenarios() {
  const [rows] = useState(seedScenarios);
  const [notice, setNotice] = useState("");

  return (
    <Page kicker="Administration" title="Scénarios" lead="Chocs de marché et de stress testing.">
      {notice && <p className="banner">{notice}</p>}
      <article className="panel">
        <table className="data-table">
          <thead><tr><th>Nom</th><th>Type</th><th>Choc</th><th>Intensité</th><th></th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td>{row.kind}</td>
                <td>{row.shock}</td>
                <td>{row.intensity}</td>
                <td><button type="button" className="mini-btn" onClick={() => setNotice(`Simulation « ${row.name} » lancée sur cet écran seulement.`)}>Lancer</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}

export function AdminSettings() {
  const [capital, setCapital] = useState("100000");
  const [fees, setFees] = useState("0.1");
  const [days, setDays] = useState("30");
  const [saved, setSaved] = useState(false);

  return (
    <Page kicker="Administration" title="Paramètres des simulations" lead="Capital, frais, durée et actifs autorisés.">
      <form className="admin-form panel" onSubmit={(event) => { event.preventDefault(); setSaved(true); }}>
        <label>Capital initial (TND)<input value={capital} onChange={(event) => setCapital(event.target.value)} /></label>
        <label>Frais par ordre (%)<input value={fees} onChange={(event) => setFees(event.target.value)} /></label>
        <label>Durée (jours)<input value={days} onChange={(event) => setDays(event.target.value)} /></label>
        <label><input type="checkbox" defaultChecked /> Actions</label>
        <label><input type="checkbox" defaultChecked /> Devises</label>
        <label><input type="checkbox" defaultChecked /> Matières premières</label>
        <label><input type="checkbox" /> Obligations</label>
        <button className="primary-btn" type="submit">Enregistrer l'aperçu</button>
        {saved && <p className="banner">Réglages gardés sur cet écran uniquement.</p>}
      </form>
    </Page>
  );
}

export function AdminModels() {
  const [rows, setRows] = useState(seedModels);
  const [fileName, setFileName] = useState("");

  return (
    <Page kicker="Administration" title="Modèles d'IA" lead="Versions, métriques et statut. L'envoi de fichier ne quitte pas le navigateur.">
      <div className="admin-tools">
        <input type="file" onChange={(event) => setFileName(event.target.files?.[0]?.name || "")} />
        {fileName && <span>Fichier choisi : {fileName}</span>}
      </div>
      <article className="panel">
        <table className="data-table">
          <thead><tr><th>Modèle</th><th>Version</th><th>Métrique</th><th>Statut</th><th></th></tr></thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id}>
                <td>{row.name}</td>
                <td>{row.version}</td>
                <td>{row.metric}</td>
                <td>{row.status}</td>
                <td><button type="button" className="mini-btn" onClick={() => setRows((current) => current.map((item) => ({ ...item, status: item.id === row.id ? "Actif" : item.status === "Actif" ? "Inactif" : item.status })))}>Activer</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}

export function AdminResults() {
  const [scenario, setScenario] = useState("tous");
  const names = ["tous", ...new Set(seedResults.map((row) => row.scenario))];
  const visible = seedResults.filter((row) => scenario === "tous" || row.scenario === scenario);

  return (
    <Page kicker="Administration" title="Résultats des simulations" lead="Comparaison statique entre scénarios et types de banques.">
      <div className="admin-tools">
        <select value={scenario} onChange={(event) => setScenario(event.target.value)}>
          {names.map((name) => <option key={name} value={name}>{name === "tous" ? "Tous les scénarios" : name}</option>)}
        </select>
      </div>
      <article className="panel">
        <table className="data-table">
          <thead><tr><th>Scénario</th><th>Banque</th><th>Type</th><th>Impact</th></tr></thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <td>{row.scenario}</td>
                <td>{row.bank}</td>
                <td>{row.type}</td>
                <td>{row.impact}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}

export function AdminAudit() {
  const [query, setQuery] = useState("");
  const [action, setAction] = useState("tous");
  const actions = ["tous", ...new Set(seedAudit.map((row) => row.action))];
  const visible = seedAudit.filter((row) => {
    const text = `${row.who} ${row.target}`.toLowerCase();
    return text.includes(query.trim().toLowerCase()) && (action === "tous" || row.action === action);
  });

  return (
    <Page kicker="Administration" title="Journal d'audit" lead="Qui a fait quoi, et quand. Exemples statiques.">
      <div className="admin-tools">
        <input placeholder="Personne ou cible" value={query} onChange={(event) => setQuery(event.target.value)} />
        <select value={action} onChange={(event) => setAction(event.target.value)}>
          {actions.map((item) => <option key={item} value={item}>{item === "tous" ? "Toutes les actions" : item}</option>)}
        </select>
      </div>
      <article className="panel">
        <table className="data-table">
          <thead><tr><th>Qui</th><th>Action</th><th>Cible</th><th>Quand</th></tr></thead>
          <tbody>
            {visible.map((row) => (
              <tr key={row.id}>
                <td>{row.who}</td>
                <td>{row.action}</td>
                <td>{row.target}</td>
                <td>{row.when}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </Page>
  );
}
