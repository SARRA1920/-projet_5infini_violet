import { useEffect, useState } from "react";
import { api } from "../services/api.js";
import "./rooms.css";

const LEVEL_LABEL = { debutant: "Débutant", intermediaire: "Intermédiaire", pro: "Pro" };
const num = (n) => Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cls = (n) => (n > 0 ? "up" : n < 0 ? "down" : "");
const medal = (rank) => (rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : rank);

export default function ClassementPage() {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("overall");

  useEffect(() => {
    api("/formation/leaderboard")
      .then(setBoard)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p className="status error">{error}</p>;
  if (!board) return <p className="status">Chargement…</p>;

  const room = board.rooms.find((r) => r.key === tab);

  return (
    <section className="page rm">
      <div className="page-head">
        <div>
          <p className="page-kicker">TradeLab / Communauté</p>
          <h1>Classement</h1>
          <p className="page-lead">
            Les meilleurs joueurs des salles de marché. Seules les parties terminées avant la fin du chronomètre
            comptent, avec le meilleur score de chacun.
          </p>
        </div>
      </div>

      <div className="rm-tabs">
        <button className={tab === "overall" ? "active" : ""} onClick={() => setTab("overall")}>
          Général
        </button>
        {board.rooms.map((r) => (
          <button key={r.key} className={tab === r.key ? "active" : ""} onClick={() => setTab(r.key)}>
            {r.name}
          </button>
        ))}
      </div>

      <article className="panel">
        {tab === "overall" ? (
          board.overall.length ? (
            <table className="rm-table rm-board">
              <thead>
                <tr>
                  <th>Rang</th>
                  <th>Joueur</th>
                  <th>Niveau</th>
                  <th>Salles</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {board.overall.map((e) => (
                  <tr key={e.username} className={e.is_me ? "me" : ""}>
                    <td>{medal(e.rank)}</td>
                    <td>
                      {e.username} {e.is_me && <em>(toi)</em>}
                    </td>
                    <td>{LEVEL_LABEL[e.level] || "—"}</td>
                    <td>{e.rooms_done}</td>
                    <td className={cls(e.total)}>{num(e.total)} pts</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="rm-muted">Personne n'a encore terminé de salle. Sois le premier !</p>
          )
        ) : room.entries.length ? (
          <table className="rm-table rm-board">
            <thead>
              <tr>
                <th>Rang</th>
                <th>Joueur</th>
                <th>Rendement</th>
                <th>Perte max.</th>
                <th>Score</th>
              </tr>
            </thead>
            <tbody>
              {room.entries.map((e) => (
                <tr key={e.username} className={e.is_me ? "me" : ""}>
                  <td>{medal(e.rank)}</td>
                  <td>
                    {e.username} {e.is_me && <em>(toi)</em>}
                  </td>
                  <td className={cls(e.return_pct)}>{num(e.return_pct)} %</td>
                  <td className="down">−{num(e.max_drawdown_pct)} %</td>
                  <td className={cls(e.score)}>{num(e.score)} pts</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="rm-muted">Personne n'a encore terminé cette salle.</p>
        )}
      </article>
    </section>
  );
}
