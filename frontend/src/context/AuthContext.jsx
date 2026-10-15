import { createContext, useContext, useEffect, useState } from "react";
import { api, clearToken, getToken, setToken } from "../services/api.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    api("/auth/me")
      .then(setUser)
      .catch(() => {
        clearToken();
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  async function login(email, password, remember = true) {
    const data = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    setToken(data.access_token, remember);
    const me = await api("/auth/me");
    setUser(me);
  }

  async function register(email, username, password) {
    await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, username, password }),
    });
    await login(email, password);
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
