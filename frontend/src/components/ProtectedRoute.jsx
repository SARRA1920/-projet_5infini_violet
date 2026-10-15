import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function ProtectedRoute({ children }) {
  const { user, ready } = useAuth();
  if (!ready) return <p className="status">Chargement…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}
