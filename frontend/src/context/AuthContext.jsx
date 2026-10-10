import { createContext, useContext, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import apiClient from "../services/apiClient";
import i18n from "../i18n";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    const token = localStorage.getItem("access_token");
    if (!token) {
      setIsLoading(false);
      return;
    }
    apiClient
      .get("/auth/me")
      .then(({ data }) => {
        setUser(data);
        i18n.changeLanguage(data.language);
      })
      .catch(() => {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Each company sees only its own data, and the query cache isn't keyed by
  // company: start every session with an empty cache so nothing from the
  // previous account on this browser can flash on screen.
  async function startSession(tokens) {
    queryClient.clear();
    localStorage.setItem("access_token", tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
    const { data: me } = await apiClient.get("/auth/me");
    setUser(me);
    // The account's saved language wins over whatever was picked on the
    // sign-in screen, so the preference follows the user between devices.
    i18n.changeLanguage(me.language);
    return me;
  }

  async function login(email, password) {
    const { data } = await apiClient.post("/auth/login", { email, password });
    return startSession(data);
  }

  /** Sign up a new company; the person signing up becomes its admin. */
  async function register(details) {
    const { data } = await apiClient.post("/auth/register", details);
    return startSession(data);
  }

  async function logout() {
    const refreshToken = localStorage.getItem("refresh_token");
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
    queryClient.clear();
    if (refreshToken) {
      try {
        await apiClient.post("/auth/logout", { refresh_token: refreshToken });
      } catch {
        // best-effort: the tokens are already cleared client-side
      }
    }
  }

  // Switch now (instant), then save to the account so it follows the user
  // to other devices. Signed out, it's remembered in this browser only.
  async function setLanguage(code) {
    await i18n.changeLanguage(code);
    if (!user) return;
    try {
      const { data } = await apiClient.patch("/auth/me", { language: code });
      setUser(data);
    } catch {
      /* the switch already happened locally; it'll just not follow them */
    }
  }

  // Name and email signature, from the profile sheet. Throws on failure.
  async function updateProfile(changes) {
    const { data } = await apiClient.patch("/auth/me", changes);
    setUser(data);
    return data;
  }

  // The guided tour: done (finished or skipped) or wanted again from Help.
  async function markTourDone(done) {
    setUser((prev) => (prev ? { ...prev, tour_completed_at: done ? new Date().toISOString() : null } : prev));
    try {
      const { data } = await apiClient.patch("/auth/me", { tour_completed: done });
      setUser(data);
    } catch {
      /* the tour still closes; it may offer itself again next time */
    }
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout, setLanguage, markTourDone, updateProfile }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
