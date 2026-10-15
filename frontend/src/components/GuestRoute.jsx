import { useAuth } from "../context/AuthContext.jsx";

export default function GuestRoute({ children }) {
  const { ready } = useAuth();
  if (!ready) return <p className="status">Chargement…</p>;
  return children;
}
