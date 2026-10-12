import { useEffect, useState } from "react";

export default function App() {
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

  return (
    <main style={{ fontFamily: "sans-serif", padding: "2rem" }}>
      <h1>Simulateur de Salle de Marché</h1>
      <p>
        Statut du backend :{" "}
        <strong style={{ color: error ? "crimson" : "green" }}>{status}</strong>
      </p>
    </main>
  );
}
