import { createContext, useContext, useEffect, useState } from "react";
import apiClient from "../services/apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    apiClient
      .get("/auth/me")
      .then(({ data }) => setUser(data))
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      })
      .finally(() => setIsLoading(false));
  }, []);

  async function login(email, password) {
    const { data } = await apiClient.post("/auth/login", { email, password });
    localStorage.setItem("access_token", data.access_token);
    localStorage.setItem("refresh_token", data.refresh_token);
    const { data: me } = await apiClient.get("/auth/me");
    setUser(me);
    return me;
  }

  async function logout() {
    const refreshToken = localStorage.getItem("refresh_token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
    if (refreshToken) {
      try {
        await apiClient.post("/auth/logout", { refresh_token: refreshToken });
      } catch {
        // best-effort: the tokens are already cleared client-side
      }
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
