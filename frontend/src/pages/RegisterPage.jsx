import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import AuthLayout from "../components/AuthLayout.jsx";
import { useAuth } from "../context/AuthContext.jsx";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    if (username.trim().length < 3) {
      setError("Le nom d'utilisateur doit contenir au moins 3 caractères.");
      return;
    }
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
      await register(email.trim(), username.trim(), password);
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
        <p className="auth-kicker">Nouveau trader</p>
        <h2>Créez votre compte</h2>
        <p className="auth-lead">Un portefeuille de 100 000 est ouvert avec l'inscription.</p>

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
        <label className="field">
          Nom d'utilisateur
          <span className="field-box">
            <input
              type="text"
              autoComplete="username"
              placeholder="Votre nom dans la salle"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </span>
        </label>
        <label className="field">
          Mot de passe
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
          Confirmer le mot de passe
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
        {error && <p className="auth-error">{error}</p>}
        <button className="auth-submit" type="submit" disabled={pending}>
          {pending ? "Création…" : "Créer le compte →"}
        </button>
        <p className="auth-switch">
          Déjà un compte ? <Link to="/login">Se connecter</Link>
        </p>
      </form>
    </AuthLayout>
  );
}
