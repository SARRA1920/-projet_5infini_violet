import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function HomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState("chargement…");
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/health")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => setStatus(data.status))
      .catch(() => {
        setError(true);
        setStatus("backend injoignable");
      });
  }, []);

  function onLogout() {
    logout();
    navigate("/login");
  }

  return (
    <main className="screen">
      <section className="card">
        <h1>Salle de marché</h1>
        <p>
          Bonjour <strong>{user.username}</strong>
        </p>
        <p className="muted">{user.email}</p>
        <p>
          Statut du backend :{" "}
          <strong className={error ? "error" : "ok"}>{status}</strong>
        </p>
        <button type="button" onClick={onLogout}>
          Se déconnecter
        </button>
      </section>
    </main>
  );
}
