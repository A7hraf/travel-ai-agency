import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { get, post, setToken, setUnauthorizedHandler, getToken } from "./api";
import type { Me } from "./types";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => void;
  can: (permission: string) => boolean;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!getToken()) {
      setLoading(false);
      return;
    }
    get<Me>("/api/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, [logout]);

  const login = async (email: string, password: string) => {
    const res = await post<{ access_token: string; user: Me }>("/api/auth/login", { email, password });
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const can = (permission: string) => !!user && user.permissions.includes(permission);

  return <AuthContext.Provider value={{ user, loading, login, logout, can }}>{children}</AuthContext.Provider>;
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
