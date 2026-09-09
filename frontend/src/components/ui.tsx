"use client";

import clsx from "clsx";
import { ChevronRight, Info, Leaf } from "lucide-react";
import Link from "next/link";
import React, { useEffect, useRef, useState } from "react";
import { parseNumeric, useMounted, usePrefersReducedMotion } from "@/lib/motion";
import { Counter, Reveal, Ripple, Skeleton, SkeletonText, useSlidingIndicator } from "./motion";

/* Every export keeps the signature it had, so no page needs editing. */

export function DemoBadge({ show = true, className }: { show?: boolean; className?: string }) {
  if (!show) return null;
  return (
    <span title="Demo / Synthetic Data — not an official statistic" className={clsx("badge border border-amber-200 bg-amber-50 text-amber-800", className)}>
      <span className="h-1.5 w-1.5 rounded-full bg-amber-500" aria-hidden />
      Demo
    </span>
  );
}

export function ValueKind({ kind }: { kind?: string | null }) {
  if (!kind) return null;
  const k = kind.split(" ")[0];
  const cls: Record<string, string> = {
    OBSERVED: "border-emerald-200 bg-emerald-50 text-emerald-800",
    MODELLED: "border-blue-200 bg-blue-50 text-blue-800",
    ASSUMPTION: "border-purple-200 bg-purple-50 text-purple-800",
    SCENARIO: "border-orange-200 bg-orange-50 text-orange-800",
    UNCERTAINTY: "border-slate-300 bg-slate-100 text-slate-700",
  };
  return <span className={clsx("badge border", cls[k] || "border-slate-200 bg-slate-50 text-slate-700")}>{k}</span>;
}

/** A status change is the consequential event in an approval queue, so the badge
 *  re-animates when the value actually changes — never on first paint. */
export function StatusBadge({ status }: { status?: string | null }) {
  const s = (status || "").toLowerCase();
  const cls =
    s.includes("publish") || s === "active" || s === "ready" || s === "approved" || s === "completed" || s === "open"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : s.includes("review") || s.includes("pending") || s === "evaluation" || s === "under_evaluation" || s === "submitted"
      ? "border-amber-200 bg-amber-50 text-amber-800"
      : s === "failed" || s === "rejected" || s === "not_selected"
      ? "border-red-200 bg-red-50 text-red-700"
      : s === "draft" || s === "todo"
      ? "border-slate-200 bg-slate-50 text-slate-600"
      : "border-blue-200 bg-blue-50 text-blue-800";

  const first = useRef(true);
  const [changed, setChanged] = useState(false);
  useEffect(() => {
    if (first.current) { first.current = false; return; }
    setChanged(true);
    const t = window.setTimeout(() => setChanged(false), 500);
    return () => clearTimeout(t);
  }, [s]);

  return <span className={clsx("badge border capitalize", cls, changed && "animate-settle-in")}>{s.replace(/_/g, " ") || "—"}</span>;
}

/**
 * Hero. A survey-sheet band: the cadastral grid sits behind the title, and a
 * thin horizon of the valley photograph anchors the bottom edge. On a phone the
 * photograph drops away entirely so the heading keeps its contrast.
 */
export function Hero({ title, accent, subtitle, crumbs, tag }: { title: string; accent?: string; subtitle?: string; crumbs?: { label: string; href?: string }[]; tag?: string }) {
  const mounted = useMounted();
  const reduced = usePrefersReducedMotion();
  const on = mounted || reduced;

  return (
    <section className="relative isolate overflow-hidden border-b border-paper-200 bg-paper-100">
      <div className="absolute inset-0 bg-survey opacity-70" style={{ backgroundSize: "28px 28px" }} aria-hidden />
      <div
        className="pointer-events-none absolute inset-y-0 right-0 hidden w-[46%] bg-cover bg-center md:block"
        style={{
          backgroundImage: "url('/hero-valley.png')",
          maskImage: "linear-gradient(to right, transparent, black 55%)",
          WebkitMaskImage: "linear-gradient(to right, transparent, black 55%)",
          opacity: on ? 0.5 : 0,
          transition: reduced ? "none" : "opacity 900ms var(--ease-settle)",
        }}
        aria-hidden
      />
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-brand-300 to-transparent" aria-hidden />

      <div className="relative mx-auto max-w-7xl px-4 py-10 sm:px-6 md:py-14 lg:px-8">
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            {crumbs && (
              <nav className="mb-3 flex flex-wrap items-center gap-1 text-xs text-slate-500" aria-label="Breadcrumb">
                {crumbs.map((c, i) => (
                  <React.Fragment key={i}>
                    {i > 0 && <ChevronRight className="h-3 w-3" aria-hidden />}
                    {c.href ? <Link href={c.href} className="transition-colors duration-state hover:text-brand-700">{c.label}</Link> : <span className="font-medium text-navy-800">{c.label}</span>}
                  </React.Fragment>
                ))}
              </nav>
            )}
            <h1 className="page-title text-balance">{title} {accent && <em>{accent}</em>}</h1>
            {subtitle && <p className="prose-body mt-3 text-navy-700">{subtitle}</p>}
          </div>
          {tag && (
            <div className="card-tick flex items-center gap-3 rounded-xl border border-paper-200 bg-white/90 px-4 py-3 shadow-card backdrop-blur">
              <Leaf className="h-6 w-6 shrink-0 text-brand-600" aria-hidden />
              <span className="max-w-[170px] text-sm font-semibold leading-snug text-navy-800">{tag}</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

/**
 * StatCard. Figures tally up, so a number that moved between two loads is
 * visibly a number that moved. Works unchanged with existing `fmtNum(...)`
 * call sites: the formatted string is parsed back to a number, counted, then
 * re-formatted in en-IN. Non-numeric values ("—") render as they are.
 */
export function StatCard({ label, value, sub, color = "brand", icon, demo }: { label: string; value: React.ReactNode; sub?: string; color?: "brand" | "blue" | "orange" | "purple"; icon?: React.ReactNode; demo?: boolean }) {
  const tone = {
    brand: "from-brand-600 to-brand-500 shadow-brand-600/25",
    blue: "from-blue-600 to-blue-500 shadow-blue-600/25",
    orange: "from-saffron to-amber-400 shadow-amber-500/25",
    purple: "from-purple-600 to-purple-500 shadow-purple-600/25",
  }[color];

  const numeric = parseNumeric(value);
  const decimals = typeof value === "string" && value.includes(".") ? (value.split(".")[1]?.length ?? 0) : 0;

  return (
    <Ripple className="card card-link flex items-center gap-3.5 p-4" color="rgba(15,95,58,0.3)">
      <div className={clsx("flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-white shadow-lg [&>svg]:h-5 [&>svg]:w-5", tone)}>{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display text-2xl font-bold leading-none text-navy-800">
          {numeric === null ? value : <Counter value={numeric} decimals={decimals} />}
          {demo && <DemoBadge />}
        </div>
        <div className="mt-1.5 truncate text-[13px] font-semibold text-slate-700">{label}</div>
        {sub && <div className="truncate text-xs text-slate-500">{sub}</div>}
      </div>
    </Ripple>
  );
}

/**
 * Section. `reveal` is opt-in and off by default — a fade-up on every section
 * of every page is noise. Turn it on where the scroll itself is the story.
 */
export function Section({ title, subtitle, action, children, className, reveal = false }: { title?: string; subtitle?: string; action?: React.ReactNode; children: React.ReactNode; className?: string; reveal?: boolean }) {
  const body = (
    <>
      {(title || action) && (
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="font-display text-xl font-bold text-navy-800 sm:text-2xl">{title}</h2>}
            {subtitle && <p className="prose-body mt-1 text-sm">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </>
  );

  return (
    <section className={clsx("mx-auto max-w-7xl px-4 py-8 sm:px-6 md:py-12 lg:px-8", className)}>
      {reveal ? <Reveal>{body}</Reveal> : body}
    </section>
  );
}

export function Alert({ kind = "info", children, className }: { kind?: "info" | "warn" | "error" | "success"; children: React.ReactNode; className?: string }) {
  const cls = {
    info: "border-blue-200 bg-blue-50 text-blue-900",
    warn: "border-amber-200 bg-amber-50 text-amber-900",
    error: "border-red-200 bg-red-50 text-red-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[kind];
  return (
    <div role={kind === "error" ? "alert" : "status"} className={clsx("flex animate-settle-up items-start gap-2.5 rounded-lg border px-3.5 py-2.5 text-sm", cls, className)}>
      <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div className="min-w-0">{children}</div>
    </div>
  );
}

/**
 * Loading. The spinner stays the default so existing call sites are unchanged;
 * the skeleton variants are shaped like the content they replace, which stops
 * the layout jumping when data lands.
 */
export function Loading({ label = "Loading…", variant = "spinner", rows = 3 }: { label?: string; variant?: "spinner" | "text" | "cards" | "table" | "grid"; rows?: number }) {
  if (variant === "text") return <SkeletonText lines={rows} className="py-4" />;

  if (variant === "cards")
    return (
      <div className="grid grid-cols-2 gap-3 sm:gap-4 lg:grid-cols-4" role="status" aria-label={label}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="card flex items-center gap-3.5 p-4">
            <Skeleton className="h-11 w-11 shrink-0 rounded-xl" />
            <div className="min-w-0 flex-1 space-y-2"><Skeleton className="h-5 w-16" /><Skeleton className="h-3 w-full" /></div>
          </div>
        ))}
      </div>
    );

  if (variant === "grid")
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" role="status" aria-label={label}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="card space-y-3 p-4">
            <div className="flex gap-2"><Skeleton className="h-5 w-20 rounded-full" /><Skeleton className="h-5 w-14 rounded-full" /></div>
            <Skeleton className="h-4 w-4/5" />
            <SkeletonText lines={2} />
          </div>
        ))}
      </div>
    );

  if (variant === "table")
    return (
      <div className="space-y-2.5 py-2" role="status" aria-label={label}>
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 shrink-0 rounded-lg" />
            <Skeleton className="h-3 flex-1" />
            <Skeleton className="hidden h-3 w-24 sm:block" />
            <Skeleton className="h-5 w-16 shrink-0 rounded-full" />
          </div>
        ))}
      </div>
    );

  return (
    <div className="flex items-center gap-3 py-10 text-sm text-slate-500" role="status">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" aria-hidden />
      {label}
    </div>
  );
}

/** An empty screen is an invitation to act, not a dead end. */
export function Empty({ title = "Nothing here yet", hint }: { title?: string; hint?: string }) {
  return (
    <div className="animate-settle-up rounded-xl border border-dashed border-paper-300 bg-white/60 p-8 text-center sm:p-12">
      <div className="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-full border border-paper-200 bg-paper-100" aria-hidden>
        <Leaf className="h-5 w-5 text-brand-400" />
      </div>
      <div className="font-display text-lg font-semibold text-navy-800">{title}</div>
      {hint && <div className="prose-body mx-auto mt-1.5 text-sm">{hint}</div>}
    </div>
  );
}

export function Pagination({ page, pages, onChange }: { page: number; pages: number; onChange: (p: number) => void }) {
  if (pages <= 1) return null;
  return (
    <nav className="mt-6 flex items-center justify-between gap-3 border-t border-paper-200 pt-4 text-sm" aria-label="Pagination">
      <button className="btn-secondary btn-sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>← <span className="hidden sm:inline">Previous</span></button>
      <span className="tabular-nums text-slate-500">Page {page} of {pages}</span>
      <button className="btn-secondary btn-sm" disabled={page >= pages} onClick={() => onChange(page + 1)}><span className="hidden sm:inline">Next</span> →</button>
    </nav>
  );
}

export function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function ErrorText({ error }: { error?: any }) {
  if (!error) return null;
  const msg = typeof error === "string" ? error : error.message || "Something went wrong";
  const details = error?.details && Array.isArray(error.details) ? error.details.map((d: any) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ") : null;
  return <Alert kind="error">{msg}{details && <div className="mt-1 text-xs opacity-80">{details}</div>}</Alert>;
}

export function KV({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 gap-x-8 text-sm sm:grid-cols-2">
      {items.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-4 border-b border-paper-200 py-2 transition-colors duration-tap hover:bg-paper-100/60">
          <dt className="shrink-0 text-slate-500">{k}</dt>
          <dd className="text-right font-medium text-slate-800">{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

/** The underline travels to the tab you picked, which is the clearest way to
 *  show which panel you are now looking at. Scrolls horizontally on a phone. */
export function Tabs({ tabs, value, onChange }: { tabs: { id: string; label: string; count?: number }[]; value: string; onChange: (id: string) => void }) {
  const { containerRef, indicatorStyle } = useSlidingIndicator(value, "x");
  return (
    <div ref={containerRef} className="no-scrollbar relative flex overflow-x-auto border-b border-paper-200" role="tablist">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          data-active={value === t.id}
          className={clsx("tab", value === t.id && "tab-active")}
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {t.count !== undefined && <span className="ml-1.5 tabular-nums text-xs text-slate-400">{t.count}</span>}
        </button>
      ))}
      <span className="rail bottom-0 left-0 h-0.5 rounded-full bg-brand-600" style={indicatorStyle} aria-hidden />
    </div>
  );
}
