import { createContext, useContext, useEffect, useState } from "react";
import * as SecureStore from "expo-secure-store";
import apiClient from "../services/apiClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const token = await SecureStore.getItemAsync("access_token");
      if (!token) {
        setIsLoading(false);
        return;
      }
      try {
        const { data } = await apiClient.get("/auth/me");
        setUser(data);
      } catch {
        await SecureStore.deleteItemAsync("access_token");
        await SecureStore.deleteItemAsync("refresh_token");
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  async function login(email, password) {
    const { data } = await apiClient.post("/auth/login", { email, password });
    await SecureStore.setItemAsync("access_token", data.access_token);
    await SecureStore.setItemAsync("refresh_token", data.refresh_token);
    const { data: me } = await apiClient.get("/auth/me");
    setUser(me);
    return me;
  }

  async function logout() {
    const refreshToken = await SecureStore.getItemAsync("refresh_token");
    await SecureStore.deleteItemAsync("access_token");
    await SecureStore.deleteItemAsync("refresh_token");
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
