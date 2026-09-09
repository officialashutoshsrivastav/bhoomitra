"use client";

/**
 * Motion primitives for Bhoomitra.
 *
 * The vocabulary comes from land survey, not from generic UI:
 *   draw   — lines trace themselves the way a plot is plotted
 *   plant  — a point lands and a contour ring spreads from it
 *   settle — panels and figures arrive with weight, no bounce
 *
 * Everything here degrades to its final state when the OS asks for reduced motion.
 */

import clsx from "clsx";
import React, { useEffect, useRef, useState } from "react";
import { fmtIN, useCountUp, useInView, usePrefersReducedMotion, useScrollProgress } from "@/lib/motion";

/* ------------------------------------------------------------------ *
 * Reveal — a panel settles into place when it enters the viewport.
 * Deliberately quiet: 8px of travel, no scale, no bounce.
 * ------------------------------------------------------------------ */
export function Reveal({
  children,
  className,
  delay = 0,
  from = "up",
  as: Tag = "div",
}: {
  children: React.ReactNode;
  className?: string;
  delay?: number;
  from?: "up" | "left" | "right" | "none";
  as?: React.ElementType;
}) {
  const reduced = usePrefersReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>();
  const shown = reduced || inView;

  const offset = from === "left" ? "translate3d(-10px,0,0)" : from === "right" ? "translate3d(10px,0,0)" : from === "none" ? "none" : "translate3d(0,8px,0)";

  return (
    <Tag
      ref={ref}
      className={className}
      style={{
        opacity: shown ? 1 : 0,
        transform: shown ? "none" : offset,
        transition: reduced ? "none" : `opacity 460ms var(--ease-settle) ${delay}ms, transform 460ms var(--ease-settle) ${delay}ms`,
        willChange: shown ? undefined : "opacity, transform",
      }}
    >
      {children}
    </Tag>
  );
}

/* ------------------------------------------------------------------ *
 * Stagger — reveals direct children in sequence. One call wraps a grid.
 * ------------------------------------------------------------------ */
export function Stagger({ children, className, step = 60, from = "up" }: { children: React.ReactNode; className?: string; step?: number; from?: "up" | "left" | "right" | "none" }) {
  const items = React.Children.toArray(children);
  return (
    <div className={className}>
      {items.map((child, i) => (
        <Reveal key={i} delay={i * step} from={from}>
          {child}
        </Reveal>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Counter — a figure tallies up to its value, ledger style.
 * Re-runs from the previous value when live data changes.
 * ------------------------------------------------------------------ */
export function Counter({ value, decimals = 0, duration = 900, className }: { value: number; decimals?: number; duration?: number; className?: string }) {
  const { ref, inView } = useInView<HTMLSpanElement>();
  const shown = useCountUp(value, { duration, decimals, start: 0, run: inView });
  return (
    <span ref={ref} className={clsx("tabular-nums", className)}>
      {fmtIN(shown, decimals)}
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * Ripple — a contour ring spreads from the pointer.
 * Wrap any clickable surface. Host gets position:relative + overflow:hidden.
 * ------------------------------------------------------------------ */
type Ring = { id: number; x: number; y: number; size: number };

export function Ripple({ children, className, color = "currentColor", as: Tag = "div" }: { children: React.ReactNode; className?: string; color?: string; as?: React.ElementType }) {
  const reduced = usePrefersReducedMotion();
  const [rings, setRings] = useState<Ring[]>([]);
  const seq = useRef(0);

  const spawn = (e: React.PointerEvent<HTMLElement>) => {
    if (reduced) return;
    const box = e.currentTarget.getBoundingClientRect();
    const size = Math.max(box.width, box.height) * 1.6;
    const id = ++seq.current;
    setRings((r) => [...r, { id, x: e.clientX - box.left, y: e.clientY - box.top, size }]);
    window.setTimeout(() => setRings((r) => r.filter((ring) => ring.id !== id)), 620);
  };

  return (
    <Tag className={clsx("relative overflow-hidden", className)} onPointerDown={spawn}>
      {children}
      {rings.map((r) => (
        <span
          key={r.id}
          aria-hidden
          className="pointer-events-none absolute rounded-full border-2 opacity-40 animate-contour"
          style={{ left: r.x - r.size / 2, top: r.y - r.size / 2, width: r.size, height: r.size, borderColor: color }}
        />
      ))}
    </Tag>
  );
}

/* ------------------------------------------------------------------ *
 * DrawPath — an SVG path traces itself. The core survey gesture.
 * ------------------------------------------------------------------ */
export function DrawPath({ d, active = true, duration = 1100, delay = 0, className, ...rest }: { d: string; active?: boolean; duration?: number; delay?: number; className?: string } & React.SVGProps<SVGPathElement>) {
  const reduced = usePrefersReducedMotion();
  const drawn = reduced || active;
  return (
    <path
      d={d}
      pathLength={1}
      className={className}
      style={{
        strokeDasharray: 1,
        strokeDashoffset: drawn ? 0 : 1,
        transition: reduced ? "none" : `stroke-dashoffset ${duration}ms var(--ease-survey) ${delay}ms`,
      }}
      {...rest}
    />
  );
}

/* ------------------------------------------------------------------ *
 * PlantedNode — a survey marker lands, with a contour ring behind it.
 * ------------------------------------------------------------------ */
export function PlantedNode({ x, y, active = true, delay = 0, r = 13, pulse = false }: { x: number; y: number; active?: boolean; delay?: number; r?: number; pulse?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const shown = reduced || active;
  return (
    <g style={{ opacity: shown ? 1 : 0, transform: shown ? "scale(1)" : "scale(0.4)", transformOrigin: `${x}px ${y}px`, transition: reduced ? "none" : `opacity 320ms var(--ease-settle) ${delay}ms, transform 420ms var(--ease-settle) ${delay}ms` }}>
      {pulse && !reduced && shown && <circle cx={x} cy={y} r={r} fill="none" stroke="#0f5f3a" strokeWidth="1.5" className="animate-contour-slow" />}
      <circle cx={x} cy={y} r={r} fill="#ffffff" stroke="#0f5f3a" strokeWidth="2" />
      <circle cx={x} cy={y} r={r * 0.36} fill="#f28c28" />
    </g>
  );
}

/* ------------------------------------------------------------------ *
 * Collapse — height animation using grid-template-rows, so there is no
 * scrollHeight measuring and no max-height guesswork.
 * ------------------------------------------------------------------ */
export function Collapse({ open, children, className }: { open: boolean; children: React.ReactNode; className?: string }) {
  const reduced = usePrefersReducedMotion();
  return (
    <div
      className={clsx("grid", className)}
      style={{ gridTemplateRows: open ? "1fr" : "0fr", transition: reduced ? "none" : "grid-template-rows 320ms var(--ease-settle)" }}
      aria-hidden={!open}
    >
      <div className="overflow-hidden" style={{ opacity: open ? 1 : 0, transition: reduced ? "none" : "opacity 240ms var(--ease-settle)" }}>
        {children}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Skeleton — a loading placeholder shaped like the content it replaces,
 * so the layout does not jump when data lands.
 * ------------------------------------------------------------------ */
export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-shimmer rounded-md bg-slate-200/70 bg-[length:200%_100%]", className)} aria-hidden />;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={clsx("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={clsx("h-3", i === lines - 1 ? "w-2/3" : "w-full")} />
      ))}
    </div>
  );
}

export function SkeletonCards({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={clsx("grid grid-cols-2 gap-4 md:grid-cols-4", className)} role="status" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card flex items-center gap-4 p-4">
          <Skeleton className="h-12 w-12 shrink-0 rounded-lg" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-3 w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * ProgressRing — a value drawn as an arc. Used for confidence scores.
 * ------------------------------------------------------------------ */
export function ProgressRing({ value, size = 64, stroke = 6, label, tone = "#0f5f3a" }: { value: number; size?: number; stroke?: number; label?: string; tone?: string }) {
  const reduced = usePrefersReducedMotion();
  const { ref, inView } = useInView<HTMLDivElement>();
  const pct = Math.max(0, Math.min(100, value));
  const shown = reduced || inView ? pct : 0;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  return (
    <div ref={ref} className="inline-flex flex-col items-center gap-1">
      <svg width={size} height={size} role="img" aria-label={`${pct}%${label ? ` ${label}` : ""}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={tone}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c - (c * shown) / 100}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          style={{ transition: reduced ? "none" : "stroke-dashoffset 900ms var(--ease-survey)" }}
        />
        <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fontSize={size * 0.26} fontWeight={700} fill="#17244a">
          {Math.round(shown)}
        </text>
      </svg>
      {label && <span className="text-xs text-slate-500">{label}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * LiveDot — a slow contour pulse for anything genuinely live.
 * ------------------------------------------------------------------ */
export function LiveDot({ tone = "bg-emerald-500", className }: { tone?: string; className?: string }) {
  return (
    <span className={clsx("relative inline-flex h-2 w-2", className)} aria-hidden>
      <span className={clsx("absolute inline-flex h-full w-full rounded-full opacity-70 animate-ping-slow motion-reduce:hidden", tone)} />
      <span className={clsx("relative inline-flex h-2 w-2 rounded-full", tone)} />
    </span>
  );
}

/* ------------------------------------------------------------------ *
 * ScrollProgress — a thin rule that fills as the page is read.
 * ------------------------------------------------------------------ */
export function ScrollProgress({ className }: { className?: string }) {
  const p = useScrollProgress();
  return (
    <div className={clsx("pointer-events-none h-0.5 w-full bg-transparent", className)} aria-hidden>
      <div className="h-full origin-left bg-gradient-to-r from-brand-600 to-saffron" style={{ transform: `scaleX(${p})`, transition: "transform 90ms linear" }} />
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * SlidingIndicator — a rail that travels to the active tab or nav item.
 * Measures the active child, so it works with any number of items.
 * ------------------------------------------------------------------ */
export function useSlidingIndicator(activeKey: string, axis: "x" | "y" = "x") {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [box, setBox] = useState<{ offset: number; size: number } | null>(null);
  const reduced = usePrefersReducedMotion();

  useEffect(() => {
    const container = containerRef.current;
    const active = container?.querySelector<HTMLElement>("[data-active='true']");
    if (!container || !active) return setBox(null);
    const cb = container.getBoundingClientRect();
    const ab = active.getBoundingClientRect();
    setBox(axis === "x" ? { offset: ab.left - cb.left + container.scrollLeft, size: ab.width } : { offset: ab.top - cb.top + container.scrollTop, size: ab.height });
  }, [activeKey, axis]);

  const style: React.CSSProperties = box
    ? axis === "x"
      ? { transform: `translateX(${box.offset}px)`, width: box.size, opacity: 1 }
      : { transform: `translateY(${box.offset}px)`, height: box.size, opacity: 1 }
    : { opacity: 0 };

  return {
    containerRef,
    indicatorStyle: { ...style, transition: reduced ? "none" : "transform 320ms var(--ease-settle), width 320ms var(--ease-settle), height 320ms var(--ease-settle), opacity 160ms linear" },
  };
}

/* ------------------------------------------------------------------ *
 * Swap — cross-fades between states so a loading→loaded change reads
 * as one thing becoming another rather than a flash of new layout.
 * ------------------------------------------------------------------ */
export function Swap({ swapKey, children, className }: { swapKey: string; children: React.ReactNode; className?: string }) {
  const reduced = usePrefersReducedMotion();
  const [rendered, setRendered] = useState({ key: swapKey, node: children });
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (swapKey === rendered.key) {
      setRendered({ key: swapKey, node: children });
      return;
    }
    if (reduced) {
      setRendered({ key: swapKey, node: children });
      return;
    }
    setVisible(false);
    const t = window.setTimeout(() => {
      setRendered({ key: swapKey, node: children });
      setVisible(true);
    }, 160);
    return () => clearTimeout(t);
  }, [swapKey, children, rendered.key, reduced]);

  return (
    <div className={className} style={{ opacity: visible ? 1 : 0, transition: reduced ? "none" : "opacity 160ms var(--ease-settle)" }}>
      {rendered.node}
    </div>
  );
}
