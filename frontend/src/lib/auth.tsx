"use client";

import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getAccessToken, onTokenChange, refreshAccessToken, setAccessToken } from "./api";

export type Me = { id: string; email: string; full_name: string; designation?: string | null; status: string; is_superuser: boolean; roles: string[]; permissions: string[]; organization_name?: string | null; primary_organization_id?: string | null };

type AuthCtx = {
  user: Me | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<Me>;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  can: (...perms: string[]) => boolean;
  hasRole: (...roles: string[]) => boolean;
};

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      if (!getAccessToken()) {
        const ok = await refreshAccessToken();
        if (!ok) {
          setUser(null);
          return;
        }
      }
      setUser(await api<Me>("/auth/me"));
    } catch {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    reload().finally(() => setLoading(false));
    return onTokenChange((t) => {
      if (!t) setUser(null);
    });
  }, [reload]);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<{ access_token: string }>("/auth/login", { body: { email, password }, auth: false });
    setAccessToken(data.access_token);
    const me = await api<Me>("/auth/me");
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { body: {} });
    } catch {}
    setAccessToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthCtx>(() => ({ user, loading, login, logout, reload, can: (...p) => !!user && (user.is_superuser || p.some((x) => user.permissions.includes(x))), hasRole: (...r) => !!user && r.some((x) => user.roles.includes(x)) }), [user, loading, login, logout, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}

export const ROLE_LABELS: Record<string, string> = {
  super_administrator: "Super Administrator", platform_administrator: "Platform Administrator", government_official: "Government Official", policy_maker: "Policy Maker", researcher: "Researcher", academic_user: "Academic", research_organization_user: "Research Organisation", gis_analyst: "GIS Analyst", data_analyst: "Data Analyst", project_manager: "Project Manager", innovation_evaluator: "Innovation Evaluator", expert_industry_user: "Expert / Industry", public_user: "Public User",
};
