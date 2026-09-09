"use client";

import { Bell, ChevronRight, Menu, Search, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import React, { useEffect, useState } from "react";
import clsx from "clsx";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useCondensed, usePrefersReducedMotion } from "@/lib/motion";
import { Collapse, useSlidingIndicator } from "./motion";

const NAV = [
  { href: "/", label: "Home" },
  { href: "/about", label: "About" },
  { href: "/features", label: "Features" },
  { href: "/research", label: "Research" },
  { href: "/datasets", label: "Datasets" },
  { href: "/map", label: "Map" },
  { href: "/policy", label: "Policy" },
  { href: "/innovation", label: "Innovation" },
  { href: "/contact", label: "Contact" },
];

export function Logo({ dark = false, compact = false }: { dark?: boolean; compact?: boolean }) {
  return (
    <Link href="/" className="group flex shrink-0 items-center gap-2.5" aria-label="Bhoomitra — home">
      <img
        src="/logo.jpeg"
        alt=""
        aria-hidden
        className={clsx("rounded-full object-cover ring-1 transition-all duration-panel ease-settle group-hover:scale-105 motion-reduce:transform-none", dark ? "ring-white/20" : "ring-paper-200", compact ? "h-9 w-9" : "h-10 w-10 sm:h-11 sm:w-11")}
      />
      <span className="leading-tight">
        <span className={clsx("block font-display font-bold tracking-tight", compact ? "text-lg" : "text-xl sm:text-2xl", dark ? "text-white" : "text-navy-800")}>
          Bhoo<span className={dark ? "text-brand-300" : "text-brand-600"}>Mitra</span>
        </span>
        <span className={clsx("hidden text-[9px] font-semibold tracking-[0.13em] sm:block", dark ? "text-brand-200/60" : "text-slate-500")}>
          PEOPLE · LAND · KNOWLEDGE
        </span>
      </span>
    </Link>
  );
}

export function SiteHeader() {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const reduced = usePrefersReducedMotion();
  const condensed = useCondensed(24);

  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!user) return setUnread(0);
    api<{ unread: number }>("/notifications", { params: { limit: 1 } }).then((r) => setUnread(r.unread)).catch(() => {});
  }, [user, pathname]);

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [open]);

  const { containerRef, indicatorStyle } = useSlidingIndicator(pathname, "x");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (q.trim()) router.push(`/search?q=${encodeURIComponent(q.trim())}`);
  };

  return (
    <>
      {/* Government identification strip. Standard for a GoI property and it
          grounds the whole page before the brand even appears. */}
      <div className="hidden bg-ink-900 text-brand-100/70 md:block">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-1.5 text-[11px] sm:px-6 lg:px-8">
          <span>Department of Land Resources · Ministry of Rural Development · Government of India</span>
          <span className="flex items-center gap-3">
            <Link href="/legal#accessibility" className="hover:text-white">Accessibility</Link>
            <Link href="/legal" className="hover:text-white">Legal</Link>
          </span>
        </div>
      </div>

      <header className={clsx("sticky top-0 z-40 border-b bg-paper-50/90 backdrop-blur transition-[height,box-shadow,border-color] duration-panel ease-settle", condensed ? "border-paper-200 shadow-card" : "border-transparent")}>
        <div className={clsx("mx-auto flex max-w-7xl items-center gap-3 px-4 transition-all duration-panel ease-settle sm:px-6 lg:px-8", condensed ? "h-14" : "h-16 sm:h-[4.5rem]")}>
          <Logo compact={condensed} />

          <nav ref={containerRef} className="relative ml-2 hidden items-center gap-0.5 xl:flex" aria-label="Main">
            {NAV.map((n) => {
              const active = pathname === n.href;
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  data-active={active}
                  aria-current={active ? "page" : undefined}
                  className={clsx("rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-state ease-settle hover:text-brand-700", active ? "text-brand-700" : "text-slate-700")}
                >
                  {n.label}
                </Link>
              );
            })}
            <span className="rail -bottom-px left-0 h-0.5 rounded-full bg-brand-600" style={indicatorStyle} aria-hidden />
          </nav>

          {/* Widens on focus so the placeholder is never clipped at md. */}
          <form onSubmit={submit} className="ml-auto hidden min-w-0 flex-1 md:flex md:max-w-[13rem] lg:max-w-[18rem]" role="search">
            <div className="group relative w-full">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400 transition-colors duration-state group-focus-within:text-brand-600" aria-hidden />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="input rounded-full py-2 pl-9 pr-3 text-sm"
                placeholder="Search"
                aria-label="Search policies, datasets and reports"
              />
            </div>
          </form>

          <div className={clsx("flex items-center gap-2", "ml-auto md:ml-0")}>
            {user ? (
              <>
                <Link href="/app/notifications" className="relative rounded-full p-2 text-brand-700 transition-colors duration-state hover:bg-brand-50" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`}>
                  <Bell className="h-5 w-5" />
                  {unread > 0 && <span className="absolute right-0 top-0 animate-settle-in rounded-full bg-red-600 px-1.5 text-[10px] font-bold tabular-nums text-white">{unread > 99 ? "99+" : unread}</span>}
                </Link>
                <Link href="/app" className="btn-primary btn-sm hidden sm:inline-flex">Dashboard</Link>
              </>
            ) : (
              <>
                <Link href="/login" className="btn-ghost btn-sm hidden sm:inline-flex">Login</Link>
                <Link href="/signup" className="btn-primary btn-sm">Sign up</Link>
              </>
            )}

            <button className="relative h-9 w-9 rounded-lg text-navy-800 hover:bg-paper-100 xl:hidden" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Menu">
              <Menu className={clsx("absolute inset-0 m-auto h-5 w-5 transition-all duration-state ease-settle", open && "rotate-90 opacity-0")} />
              <X className={clsx("absolute inset-0 m-auto h-5 w-5 transition-all duration-state ease-settle", open ? "rotate-0 opacity-100" : "-rotate-90 opacity-0")} />
            </button>
          </div>
        </div>

        <Collapse open={open} className="border-t border-paper-200 bg-paper-50 xl:hidden">
          <div className="max-h-[70vh] overflow-y-auto px-4 py-4">
            <form onSubmit={submit} className="mb-3" role="search">
              <input value={q} onChange={(e) => setQ(e.target.value)} className="input" placeholder="Search the platform" aria-label="Search" />
            </form>
            <div className="grid gap-0.5">
              {NAV.map((n, i) => (
                <Link
                  key={n.href}
                  href={n.href}
                  onClick={() => setOpen(false)}
                  className={clsx("flex items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium transition-colors duration-tap", pathname === n.href ? "bg-brand-50 text-brand-700" : "text-slate-700 hover:bg-paper-100")}
                  style={open && !reduced ? { animation: `settleIn 320ms var(--ease-settle) ${i * 24}ms both` } : undefined}
                >
                  {n.label}
                  <ChevronRight className="h-4 w-4 text-slate-300" aria-hidden />
                </Link>
              ))}
            </div>
            <div className="mt-3 flex gap-2 border-t border-paper-200 pt-3">
              {user ? (
                <>
                  <Link href="/app" className="btn-primary flex-1">Dashboard</Link>
                  <button onClick={logout} className="btn-secondary">Logout</button>
                </>
              ) : (
                <>
                  <Link href="/login" className="btn-secondary flex-1">Login</Link>
                  <Link href="/signup" className="btn-primary flex-1">Sign up</Link>
                </>
              )}
            </div>
          </div>
        </Collapse>
      </header>
    </>
  );
}

const FOOTER_COLS: { title: string; links: [string, string][] }[] = [
  { title: "Platform", links: [["/features", "Features"], ["/map", "Interactive map"], ["/datasets", "Datasets"], ["/research", "Research"], ["/innovation", "Innovation portal"]] },
  { title: "Resources", links: [["/policy", "Policy insights"], ["/about", "About the platform"], ["/contact", "Contact"], ["/signup", "Request access"], ["/search", "Search"]] },
  { title: "Legal", links: [["/legal#privacy", "Privacy policy"], ["/legal#terms", "Terms of use"], ["/legal#disclaimer", "Disclaimer"], ["/legal#accessibility", "Accessibility"], ["/legal#data", "Demo data policy"]] },
];

export function SiteFooter() {
  return (
    <footer className="relative mt-16 overflow-hidden bg-ink-900 text-brand-100">
      <div className="absolute inset-0 bg-survey-dark opacity-70" style={{ backgroundSize: "56px 56px" }} aria-hidden />
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-brand-400/50 to-transparent" aria-hidden />

      <div className="relative mx-auto grid max-w-7xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-2 lg:grid-cols-5 lg:px-8">
        <div className="lg:col-span-2">
          <Logo dark />
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-brand-100/70">
            A national platform for land intelligence, research and policy innovation — bringing documents, datasets, maps and models into one accountable system.
          </p>
          <p className="mt-5 text-xs leading-relaxed text-brand-200/50">
            Department of Land Resources<br />Ministry of Rural Development, Government of India (PME Division)
          </p>
        </div>

        {FOOTER_COLS.map((col) => (
          <div key={col.title}>
            <h4 className="mb-3 text-xs font-semibold tracking-[0.12em] text-white/90">{col.title.toUpperCase()}</h4>
            <ul className="space-y-2 text-sm">
              {col.links.map(([h, l]) => (
                <li key={h}>
                  <Link href={h} className="inline-block text-brand-100/70 transition-all duration-state ease-settle hover:translate-x-0.5 hover:text-white motion-reduce:transform-none">{l}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>

      <div className="relative border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-brand-200/50 sm:px-6 lg:px-8">
          <span>© {new Date().getFullYear()} Bhoomitra. All rights reserved.</span>
          <span>Outputs carry evidence provenance and are not official government decisions.</span>
        </div>
      </div>
    </footer>
  );
}
