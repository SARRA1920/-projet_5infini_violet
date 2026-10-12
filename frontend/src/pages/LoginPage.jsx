import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout.jsx";
import { useAuth } from "../context/AuthContext.jsx";

function MailIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M4 7l8 6 8-6" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true">
      <rect x="5" y="10" width="14" height="10" rx="2" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 10V8a4 4 0 0 1 8 0v2" fill="none" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [remember, setRemember] = useState(true);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    setInfo("");
    setPending(true);
    try {
      await login(email.trim(), password, remember);
      navigate("/accueil");
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout>
      <form className="auth-form" onSubmit={onSubmit}>
        <p className="auth-kicker">Heureux de vous revoir</p>
        <h2>Connectez-vous</h2>
        <p className="auth-lead">Accédez à votre salle de marché virtuelle.</p>

        <label className="field">
          Adresse e-mail
          <span className="field-box">
            <MailIcon />
            <input
              type="email"
              autoComplete="email"
              placeholder="vous@exemple.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </span>
        </label>

        <label className="field">
          Mot de passe
          <span className="field-box">
            <LockIcon />
            <input
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              placeholder="8 caractères minimum"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
            <button
              type="button"
              className="ghost-icon"
              aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
              onClick={() => setShowPassword((value) => !value)}
            >
              {showPassword ? "Masquer" : "Voir"}
            </button>
          </span>
        </label>

        <div className="auth-row">
          <label className="check">
            <input
              type="checkbox"
              checked={remember}
              onChange={(event) => setRemember(event.target.checked)}
            />
            Se souvenir de moi
          </label>
          <button
            type="button"
            className="text-link"
            onClick={() =>
              setInfo("La réinitialisation du mot de passe n'est pas encore disponible.")
            }
          >
            Mot de passe oublié ?
          </button>
        </div>

        {error && <p className="auth-error">{error}</p>}
        {info && <p className="auth-info">{info}</p>}

        <button className="auth-submit" type="submit" disabled={pending}>
          {pending ? "Connexion…" : "Se connecter →"}
        </button>

        <p className="auth-switch">
          Pas encore de compte ? <Link to="/register">Créer un compte</Link>
        </p>
        <p className="auth-secure">Connexion sécurisée · Données chiffrées</p>
      </form>
    </AuthLayout>
  );
}
