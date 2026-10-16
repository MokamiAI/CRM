import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import apiClient from "../services/apiClient";
import i18n from "../i18n";

const AuthContext = createContext(null);

// Tabs of this browser tell each other when the email has been confirmed.
const AUTH_CHANNEL = "ygt-auth";

/** The confirm-email page calls this: other open tabs update at once. */
export function announceVerified() {
  try {
    const channel = new BroadcastChannel(AUTH_CHANNEL);
    channel.postMessage("verified");
    channel.close();
  } catch {
    /* older browsers: the other tabs notice on their next check */
  }
}

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

  /** An invited team member chose their password: signed in. */
  async function acceptInvite(token, password) {
    const { data } = await apiClient.post("/auth/invite", { token, password });
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

  // After something changed on the server (e.g. the email was confirmed).
  async function reloadUser() {
    try {
      const { data } = await apiClient.get("/auth/me");
      setUser(data);
    } catch {
      /* not signed in */
    }
  }

  // Waiting for the email to be confirmed: notice as soon as it is, even
  // if the link was opened on another device. Other tabs here say so at
  // once; otherwise check every 30 seconds and whenever the tab is back
  // in view.
  const waitingForLink = Boolean(user && !user.email_verified_at);
  useEffect(() => {
    if (!waitingForLink) return undefined;
    const check = () => reloadUser();
    const onVisible = () => document.visibilityState === "visible" && check();
    const timer = setInterval(check, 30 * 1000);
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", check);
    let channel;
    try {
      channel = new BroadcastChannel(AUTH_CHANNEL);
      channel.onmessage = check;
    } catch {
      /* no BroadcastChannel: the timer and focus checks still work */
    }
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", check);
      channel?.close();
    };
  }, [waitingForLink]); // eslint-disable-line react-hooks/exhaustive-deps

  // It just turned confirmed (here or elsewhere): say thank you, once.
  const wasWaiting = useRef(false);
  useEffect(() => {
    if (wasWaiting.current && user?.email_verified_at && !window.location.pathname.startsWith("/verify-email")) {
      toast.success(i18n.t("verify.confirmedToast"));
    }
    wasWaiting.current = waitingForLink;
  }, [waitingForLink, user?.email_verified_at]);

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
    <AuthContext.Provider value={{ user, isLoading, login, register, acceptInvite, logout, setLanguage, markTourDone, updateProfile, reloadUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within an AuthProvider");
  return context;
}
