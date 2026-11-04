import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { ApiError, get, post, setToken, setUnauthorizedHandler, getToken } from "./api";
import type { Me } from "./types";

export interface LoginChoice {
  account: string;
  company: string | null;
  role: string;
}

interface AuthState {
  user: Me | null;
  loading: boolean;
  /** Signs in, or returns the accounts to choose from when the email works for several companies. */
  login: (email: string, password: string, account?: string) => Promise<Me | LoginChoice[]>;
  logout: () => void;
  /** True after the server ended the session (401): the login page explains it. */
  sessionEnded: boolean;
  can: (permission: string) => boolean;
  refresh: () => Promise<void>;
  /** The session check failed without an answer (server asleep, network): shown with a Retry button. */
  loadError: string | null;
  retry: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [sessionEnded, setSessionEnded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setSessionEnded(true);
      logout();
    });
    if (!getToken()) {
      setLoading(false);
      return;
    }
    checkSession();
  }, [logout]); // eslint-disable-line react-hooks/exhaustive-deps

  // Only a refused login (401/403) signs the person out; a server that is slow to wake up or a lost
  // connection keeps the login and offers to try again.
  function checkSession() {
    setLoading(true);
    setLoadError(null);
    get<Me>("/api/auth/me")
      .then(setUser)
      .catch((e) => {
        if (e instanceof ApiError && (e.status === 401 || e.status === 403)) setToken(null);
        else setLoadError((e as Error).message);
      })
      .finally(() => setLoading(false));
  }
  const retry = useCallback(() => checkSession(), []); // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (email: string, password: string, account?: string) => {
    const res = await post<{ access_token: string; user: Me } | { choose: LoginChoice[] }>(
      "/api/auth/login", { email, password, account: account ?? null });
    if ("choose" in res) return res.choose;
    setToken(res.access_token);
    setSessionEnded(false);
    setUser(res.user);
    return res.user;
  };

  const refresh = useCallback(async () => {
    setUser(await get<Me>("/api/auth/me"));
  }, []);

  const can = (permission: string) => !!user && user.permissions.includes(permission);

  return <AuthContext.Provider value={{ user, loading, login, logout, sessionEnded, can, refresh, loadError, retry }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function homePath(user: Me): string {
  if (user.role === "system_admin") return "/system";
  if (user.permissions.includes("reports.view")) return "/app/dashboard";
  if (user.permissions.includes("conversations.view")) return "/app/conversations";
  if (user.permissions.includes("tickets.view")) return "/app/tickets";
  return "/app/account";
}
