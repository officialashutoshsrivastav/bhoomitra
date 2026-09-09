"use client";

/**
 * Loading identity for Bhoomitra.
 *
 * The logo sits inside a survey ring that plots itself, the way a station is
 * fixed on a survey sheet. Three states share the same gesture so loading feels
 * like one thing at three sizes:
 *
 *   BootLoader   — first paint, full screen, once per session
 *   RouteProgress — a hairline that runs across the top on navigation
 *   PanelLoader  — the same ring, small, inside a card or panel
 */

import clsx from "clsx";
import { usePathname } from "next/navigation";
import React, { useEffect, useRef, useState } from "react";
import { usePrefersReducedMotion } from "@/lib/motion";

/* ------------------------------------------------------------------ *
 * The mark: logo + plotting ring
 * ------------------------------------------------------------------ */
export function LogoMark({ size = 96, drawn = true, spin = true }: { size?: number; drawn?: boolean; spin?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const r = size / 2 - 3;
  const c = 2 * Math.PI * r;

  return (
    <span className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <img
        src="/logo.jpeg"
        alt=""
        aria-hidden
        className="rounded-full object-cover"
        style={{ width: size * 0.74, height: size * 0.74 }}
      />
      <svg className="absolute inset-0" width={size} height={size} aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(15,95,58,0.14)" strokeWidth="2" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="#0f5f3a"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeDasharray={`${c * 0.28} ${c}`}
          strokeDashoffset={drawn ? 0 : c}
          className={clsx(spin && !reduced && "animate-spin-slow")}
          style={{ transformOrigin: "center", transition: reduced ? "none" : "stroke-dashoffset 900ms var(--ease-survey)" }}
        />
        {/* Four register ticks, like the corners of a survey sheet. */}
        {[0, 90, 180, 270].map((deg) => (
          <line
            key={deg}
            x1={size / 2}
            y1={2}
            x2={size / 2}
            y2={7}
            stroke="#0f5f3a"
            strokeWidth="2"
            strokeLinecap="round"
            opacity={0.45}
            transform={`rotate(${deg} ${size / 2} ${size / 2})`}
          />
        ))}
      </svg>
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Full-screen boot loader
 * ------------------------------------------------------------------ */
export function BootLoader({ minMs = 700 }: { minMs?: number }) {
  const reduced = usePrefersReducedMotion();
  const [phase, setPhase] = useState<"in" | "out" | "gone">("in");
  const [pct, setPct] = useState(8);

  useEffect(() => {
    if (reduced) {
      setPhase("gone");
      return;
    }

    let raf = 0;
    const t0 = performance.now();
    const tick = (now: number) => {
      const elapsed = now - t0;
      setPct(Math.min(96, 8 + (elapsed / minMs) * 88));
      if (elapsed < minMs) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    const done = () => {
      setPct(100);
      window.setTimeout(() => setPhase("out"), 180);
      window.setTimeout(() => setPhase("gone"), 640);
    };

    const remaining = Math.max(0, minMs - (performance.now() - t0));
    const timer = window.setTimeout(done, remaining);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(timer);
    };
  }, [minMs, reduced]);

  if (phase === "gone") return null;

  return (
    <div
      className={clsx(
        "fixed inset-0 z-[100] flex flex-col items-center justify-center bg-paper-50",
        phase === "out" && "pointer-events-none"
      )}
      style={{ opacity: phase === "out" ? 0 : 1, transition: "opacity 420ms var(--ease-settle)" }}
      role="status"
      aria-live="polite"
      aria-label="Loading Bhoomitra"
    >
      <div className="absolute inset-0 bg-survey opacity-60" style={{ backgroundSize: "28px 28px" }} aria-hidden />

      <div className="relative flex flex-col items-center">
        <LogoMark size={104} />
        <div className="mt-6 text-center">
          <div className="font-display text-2xl font-bold tracking-tight text-navy-800">
            Bhoo<span className="text-brand-600">Mitra</span>
          </div>
          <div className="mt-1 text-[11px] font-semibold tracking-[0.14em] text-slate-500">
            PEOPLE · LAND · KNOWLEDGE
          </div>
        </div>

        <div className="mt-7 h-[3px] w-52 overflow-hidden rounded-full bg-paper-200">
          <div
            className="h-full rounded-full bg-gradient-to-r from-brand-600 to-saffron"
            style={{ width: `${pct}%`, transition: "width 260ms var(--ease-settle)" }}
          />
        </div>
      </div>

      <p className="absolute bottom-8 px-6 text-center text-[11px] text-slate-400">
        Department of Land Resources · Ministry of Rural Development
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Route-change progress. A hairline that runs, then completes and fades.
 * ------------------------------------------------------------------ */
export function RouteProgress() {
  const pathname = usePathname();
  const reduced = usePrefersReducedMotion();
  const first = useRef(true);
  const [pct, setPct] = useState(0);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    if (reduced) return;

    setVisible(true);
    setPct(18);

    const creep = window.setInterval(() => setPct((p) => (p < 88 ? p + (90 - p) * 0.12 : p)), 120);
    const finish = window.setTimeout(() => {
      window.clearInterval(creep);
      setPct(100);
      window.setTimeout(() => setVisible(false), 260);
      window.setTimeout(() => setPct(0), 520);
    }, 420);

    return () => {
      window.clearInterval(creep);
      window.clearTimeout(finish);
    };
  }, [pathname, reduced]);

  return (
    <div className="pointer-events-none fixed inset-x-0 top-0 z-[90] h-0.5" aria-hidden>
      <div
        className="h-full bg-gradient-to-r from-brand-600 via-brand-400 to-saffron"
        style={{ width: `${pct}%`, opacity: visible ? 1 : 0, transition: "width 200ms var(--ease-settle), opacity 260ms linear" }}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Panel loader — same ring, used inside a card while data lands.
 * ------------------------------------------------------------------ */
export function PanelLoader({ label = "Loading…", className }: { label?: string; className?: string }) {
  return (
    <div className={clsx("flex flex-col items-center justify-center gap-3 py-12", className)} role="status">
      <LogoMark size={54} />
      <span className="text-sm text-slate-500">{label}</span>
    </div>
  );
}
