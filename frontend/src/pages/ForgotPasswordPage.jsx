import { useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import AuthLayout from "../components/AuthLayout.jsx";
import { api } from "../services/api.js";

export default function ForgotPasswordPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [email, setEmail] = useState(location.state?.email || "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [sent, setSent] = useState(false);
  const [pending, setPending] = useState(false);

  async function requestLink(event) {
    event.preventDefault();
    setError("");
    setPending(true);
    try {
      await api("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: email.trim() }),
      });
      setSent(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  async function changePassword(event) {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Le mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (password !== confirm) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setPending(true);
    try {
      await api("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({ reset_token: token, password }),
      });
      navigate("/login", { replace: true, state: { info: "Mot de passe mis à jour. Connectez-vous." } });
    } catch (err) {
      setError(err.message);
    } finally {
      setPending(false);
    }
  }

  return (
    <AuthLayout>
      <form className="auth-form" onSubmit={token ? changePassword : requestLink}>
        <p className="auth-kicker">Compte</p>
        <h2>Mot de passe oublié</h2>
        <p className="auth-lead">
          {token
            ? "Choisissez un nouveau mot de passe. Ce lien ne sert qu'une fois."
            : sent
              ? "Un e-mail vient d'être envoyé. Ouvrez le lien qu'il contient. Il est valable 30 minutes."
              : "Indiquez l'e-mail du compte. Un lien pour choisir un nouveau mot de passe vous sera envoyé."}
        </p>

        {!token && !sent && (
          <label className="field">
            Adresse e-mail
            <span className="field-box">
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
        )}

        {token && (
          <>
            <label className="field">
              Nouveau mot de passe
              <span className="field-box">
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="8 caractères minimum"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
              </span>
            </label>
            <label className="field">
              Confirmation
              <span className="field-box">
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Répétez le mot de passe"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  required
                />
              </span>
            </label>
          </>
        )}

        {error && <p className="auth-error">{error}</p>}

        {!sent && (
          <button className="auth-submit" type="submit" disabled={pending}>
            {pending ? "Envoi…" : token ? "Enregistrer le mot de passe" : "Envoyer le lien"}
          </button>
        )}

        <p className="auth-switch">
          <Link to="/login">Retour à la connexion</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
