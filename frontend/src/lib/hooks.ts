"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "./api";

export function useApi<T = any>(path: string | null, params?: Record<string, any>, deps: any[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<any>(null);
  const [loading, setLoading] = useState(!!path);
  const key = JSON.stringify(params || {});
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    setError(null);
    try {
      setData(await api<T>(path, { params }));
    } catch (e) {
      setError(e);
    } finally {
      setLoading(false);
    }
  }, [path, key, ...deps]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, error, loading, reload, setData };
}

export function useDebounce<T>(value: T, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}
