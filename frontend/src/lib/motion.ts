"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/** Honours the OS "reduce motion" setting. Every animated component checks this. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return reduced;
}

/** True once the component has hydrated — used to run load sequences client-side only. */
export function useMounted(): boolean {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  return mounted;
}

type InViewOptions = { threshold?: number; rootMargin?: string; once?: boolean };

/** Fires when an element scrolls into the viewport. */
export function useInView<T extends HTMLElement = HTMLDivElement>(
  { threshold = 0.15, rootMargin = "0px 0px -10% 0px", once = true }: InViewOptions = {}
) {
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") return setInView(true);

    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) io.disconnect();
        } else if (!once) {
          setInView(false);
        }
      },
      { threshold, rootMargin }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [threshold, rootMargin, once]);

  return { ref, inView };
}

const easeSettle = (t: number) => 1 - Math.pow(1 - t, 4);

type CountUpOptions = { duration?: number; decimals?: number; start?: number; run?: boolean };

/**
 * Ticks a number up to its target. Re-runs whenever the target changes, so a live
 * dashboard figure animates from its previous value rather than from zero.
 */
export function useCountUp(target: number | null, { duration = 900, decimals = 0, start, run = true }: CountUpOptions = {}) {
  const reduced = usePrefersReducedMotion();
  const [value, setValue] = useState(() => start ?? target ?? 0);
  const fromRef = useRef(start ?? target ?? 0);
  const frameRef = useRef<number | null>(null);

  useEffect(() => {
    if (target === null || !Number.isFinite(target)) return;

    if (reduced || !run || duration <= 0) {
      fromRef.current = target;
      setValue(target);
      return;
    }

    const from = fromRef.current;
    const delta = target - from;
    if (delta === 0) return;

    const t0 = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - t0) / duration);
      const next = from + delta * easeSettle(p);
      setValue(decimals > 0 ? next : Math.round(next));
      if (p < 1) frameRef.current = requestAnimationFrame(step);
      else fromRef.current = target;
    };
    frameRef.current = requestAnimationFrame(step);

    return () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      fromRef.current = target;
    };
  }, [target, duration, decimals, reduced, run]);

  return value;
}

/** 0 → 1 reading progress for the whole document. */
export function useScrollProgress(): number {
  const [progress, setProgress] = useState(0);
  useEffect(() => {
    let ticking = false;
    const read = () => {
      const doc = document.documentElement;
      const max = doc.scrollHeight - doc.clientHeight;
      setProgress(max > 0 ? Math.min(1, doc.scrollTop / max) : 0);
      ticking = false;
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(read);
      }
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);
  return progress;
}

/** True once the page has scrolled past `threshold` — used to condense the header. */
export function useCondensed(threshold = 24): boolean {
  const [condensed, setCondensed] = useState(false);
  useEffect(() => {
    let ticking = false;
    const read = () => {
      setCondensed(window.scrollY > threshold);
      ticking = false;
    };
    const onScroll = () => {
      if (!ticking) {
        ticking = true;
        requestAnimationFrame(read);
      }
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [threshold]);
  return condensed;
}

/**
 * Runs a load sequence: returns how many steps have fired so far.
 * Used for the one orchestrated moment on the landing page.
 */
export function useSequence(steps: number, stepMs = 220): number {
  const reduced = usePrefersReducedMotion();
  const mounted = useMounted();
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!mounted) return;
    if (reduced) return setStep(steps);
    const timers = Array.from({ length: steps }, (_, i) => window.setTimeout(() => setStep(i + 1), i * stepMs));
    return () => timers.forEach(clearTimeout);
  }, [mounted, reduced, steps, stepMs]);

  return step;
}

/** Parses "1,23,456" or 1234 into a number. Returns null for "—" and other non-numeric nodes. */
export function parseNumeric(input: unknown): number | null {
  if (typeof input === "number") return Number.isFinite(input) ? input : null;
  if (typeof input !== "string") return null;
  const cleaned = input.replace(/[,\s\u00a0]/g, "");
  if (!/^-?\d+(\.\d+)?$/.test(cleaned)) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export const fmtIN = (v: number, decimals = 0) => v.toLocaleString("en-IN", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });

/** Scrolls the active item of a horizontal nav into view when the route changes. */
export function useScrollActiveIntoView(deps: unknown[]) {
  const ref = useRef<HTMLElement | null>(null);
  const reduced = usePrefersReducedMotion();
  const cb = useCallback(() => {
    const el = ref.current?.querySelector<HTMLElement>("[data-active='true']");
    el?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest", inline: "center" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reduced, ...deps]);
  useEffect(cb, [cb]);
  return ref;
}
