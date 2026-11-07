import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";

export default function ProtectedRoute({ children }) {
  const { user, ready } = useAuth();
  const { pathname } = useLocation();
  if (!ready) return <p className="status">Chargement…</p>;
  if (!user) return <Navigate to="/login" replace />;
  // Test de niveau obligatoire à la première connexion (les administrateurs en sont exemptés)
  const mustPlace = user.role !== "admin" && !user.level;
  if (mustPlace && pathname !== "/formation/niveau") {
    return <Navigate to="/formation/niveau" replace />;
  }
  return children;
}
