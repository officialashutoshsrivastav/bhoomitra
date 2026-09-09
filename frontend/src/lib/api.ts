"use client";

export type ApiError = { code: string; message: string; details?: any; request_id?: string; status: number };

const BASE = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const listeners = new Set<(token: string | null) => void>();

export function getAccessToken() {
  return accessToken;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
  if (typeof window !== "undefined") {
    if (token) sessionStorage.setItem("bm_at", token);
    else sessionStorage.removeItem("bm_at");
  }
  listeners.forEach((l) => l(token));
}

export function onTokenChange(fn: (token: string | null) => void): () => void {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

if (typeof window !== "undefined" && !accessToken) {
  accessToken = sessionStorage.getItem("bm_at");
}

export async function refreshAccessToken(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const r = await fetch(`${BASE}/api/v1/auth/refresh`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" }, body: "{}" });
        if (!r.ok) {
          setAccessToken(null);
          return false;
        }
        const data = await r.json();
        setAccessToken(data.access_token);
        return true;
      } catch {
        setAccessToken(null);
        return false;
      } finally {
        refreshing = null;
      }
    })();
  }
  return refreshing;
}

type Options = { method?: string; body?: any; form?: FormData; params?: Record<string, any>; auth?: boolean; retry?: boolean; raw?: boolean };

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const url = new URL(`${BASE}/api/v1${path}`, typeof window !== "undefined" ? window.location.origin : "http://localhost");
  if (opts.params) Object.entries(opts.params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && url.searchParams.set(k, String(v)));
  const headers: Record<string, string> = { "X-Requested-With": "XMLHttpRequest" };
  if (!opts.form) headers["Content-Type"] = "application/json";
  if (accessToken && opts.auth !== false) headers.Authorization = `Bearer ${accessToken}`;
  const res = await fetch(url.toString(), { method: opts.method || (opts.body || opts.form ? "POST" : "GET"), headers, credentials: "include", body: opts.form ? opts.form : opts.body !== undefined ? JSON.stringify(opts.body) : undefined });
  if (res.status === 401 && opts.retry !== false && accessToken) {
    const ok = await refreshAccessToken();
    if (ok) return api<T>(path, { ...opts, retry: false });
  }
  if (opts.raw) return res as unknown as T;
  if (!res.ok) {
    let err: ApiError = { code: "http_error", message: res.statusText, status: res.status };
    try {
      const j = await res.json();
      err = { ...(j.error || {}), status: res.status };
    } catch {}
    throw err;
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const fmtDate = (v?: string | null) => (v ? new Date(v).toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" }) : "—");
export const fmtNum = (v?: number | null, d = 0) => (v === null || v === undefined ? "—" : v.toLocaleString("en-IN", { maximumFractionDigits: d }));
export const titleCase = (s?: string | null) => (s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
export const downloadUrl = (path: string) => `${BASE}/api/v1${path}`;

export async function downloadWithAuth(path: string, filename: string) {
  const res = await api<Response>(path, { raw: true });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}
