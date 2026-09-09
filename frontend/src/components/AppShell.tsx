"use client";

import clsx from "clsx";
import { BarChart3, Bell, BookOpen, Brain, Database, FlaskConical, Globe2, Home, Lightbulb, LogOut, Map, Menu, Search, Settings, Shield, User, Users, FileBarChart, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "./site";
import { Skeleton, useSlidingIndicator } from "./motion";
import { LogoMark } from "./Loader";
import { usePrefersReducedMotion } from "@/lib/motion";
import { ROLE_LABELS, useAuth } from "@/lib/auth";

type Item = { href: string; label: string; icon: any; perms?: string[] };

/* Grouped, because thirteen flat links is a wall. The labels are what a user
   would say they are doing, not what the module is called internally. */
const GROUPS: { heading: string; items: Item[] }[] = [
  {
    heading: "Work",
    items: [
      { href: "/app", label: "Dashboard", icon: Home },
      { href: "/app/repository", label: "Repository", icon: BookOpen, perms: ["document.read"] },
      { href: "/app/datasets", label: "Datasets", icon: Database, perms: ["document.read"] },
      { href: "/app/workspaces", label: "Workspaces", icon: Users },
    ],
  },
  {
    heading: "Analyse",
    items: [
      { href: "/app/search", label: "Search", icon: Search, perms: ["search.use"] },
      { href: "/app/ai", label: "AI Assistant", icon: Brain, perms: ["ai.query"] },
      { href: "/app/gis", label: "GIS Workbench", icon: Map, perms: ["gis.view"] },
      { href: "/app/analytics", label: "Analytics", icon: BarChart3, perms: ["analytics.run"] },
      { href: "/app/simulation", label: "Simulation Lab", icon: FlaskConical, perms: ["simulation.create", "simulation.run", "simulation.approve"] },
    ],
  },
  {
    heading: "Programmes",
    items: [
      { href: "/app/innovation", label: "Innovation", icon: Lightbulb },
      { href: "/app/reports", label: "Reports", icon: FileBarChart, perms: ["report.generate"] },
      { href: "/app/notifications", label: "Notifications", icon: Bell },
      { href: "/app/admin", label: "Administration", icon: Shield, perms: ["admin.manage_users", "admin.manage_config", "admin.approvals", "audit.read", "integration.manage"] },
    ],
  },
];

function ShellSkeleton() {
  return (
    <div className="flex min-h-screen bg-paper-50">
      <aside className="hidden w-[17rem] shrink-0 flex-col gap-2 bg-ink-900 p-4 lg:flex">
        <Skeleton className="mb-3 h-11 w-40 bg-white/10" />
        {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-9 w-full bg-white/10" />)}
      </aside>
      <div className="flex min-w-0 flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-3"><LogoMark size={54} /><span className="text-sm text-slate-500">Checking your session…</span></div>
      </div>
    </div>
  );
}

function NavList({ groups, activeHref, onNavigate, withRail = true }: { groups: { heading: string; items: Item[] }[]; activeHref: string; onNavigate?: () => void; withRail?: boolean }) {
  const reduced = usePrefersReducedMotion();
  const { containerRef, indicatorStyle } = useSlidingIndicator(activeHref, "y");

  return (
    <div ref={withRail ? containerRef : undefined} className="relative px-3 py-2">
      {withRail && <span className="rail left-0 w-[3px] rounded-r-full bg-brand-400" style={indicatorStyle} aria-hidden />}
      {groups.map((g) => (
        <div key={g.heading} className="mb-4 last:mb-0">
          <div className="px-3 pb-1.5 text-[10px] font-semibold tracking-[0.12em] text-brand-200/50">{g.heading.toUpperCase()}</div>
          <div className="space-y-0.5">
            {g.items.map((i) => {
              const active = i.href === activeHref;
              return (
                <Link
                  key={i.href}
                  href={i.href}
                  data-active={active}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={clsx(
                    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors duration-state ease-settle",
                    active ? "bg-white/10 text-white" : "text-brand-100/70 hover:bg-white/5 hover:text-white"
                  )}
                >
                  <i.icon className={clsx("h-4 w-4 shrink-0 transition-transform duration-state ease-settle", !reduced && "group-hover:scale-110", active ? "text-brand-300" : "text-brand-200/60")} aria-hidden />
                  <span className="truncate">{i.label}</span>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const { user, loading, logout, can } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const reduced = usePrefersReducedMotion();
  const [drawer, setDrawer] = useState(false);

  useEffect(() => {
    if (!loading && !user) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [loading, user, pathname]);

  // Close the drawer on navigation, and lock body scroll while it is open.
  useEffect(() => setDrawer(false), [pathname]);
  useEffect(() => {
    document.body.style.overflow = drawer ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [drawer]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setDrawer(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (loading || !user) return <ShellSkeleton />;

  const groups = GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => !i.perms || can(...i.perms)) })).filter((g) => g.items.length);
  const flat = groups.flatMap((g) => g.items);
  const activeHref = flat.find((i) => (i.href === "/app" ? pathname === "/app" : pathname.startsWith(i.href)))?.href ?? "";
  const activeLabel = flat.find((i) => i.href === activeHref)?.label ?? "Dashboard";

  const footer = (
    <div className="border-t border-white/10 p-3">
      <Link href="/app/profile" className="flex items-center gap-3 rounded-lg px-3 py-2 transition-colors duration-state hover:bg-white/5">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-500/25 text-xs font-bold text-brand-100">
          {user.full_name?.split(" ").map((p) => p[0]).slice(0, 2).join("")}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-white">{user.full_name}</span>
          <span className="block truncate text-xs text-brand-200/60">{user.roles.map((r) => ROLE_LABELS[r] || r).join(", ")}</span>
        </span>
      </Link>
      <div className="mt-1.5 flex gap-1.5">
        <Link href="/" className="btn btn-sm flex-1 border border-white/15 text-brand-100 hover:bg-white/10"><Globe2 className="h-3.5 w-3.5" aria-hidden /> Public site</Link>
        <button onClick={logout} className="btn btn-sm border border-white/15 text-brand-100 hover:bg-white/10" aria-label="Log out"><LogOut className="h-3.5 w-3.5" aria-hidden /></button>
      </div>
    </div>
  );

  return (
    <div className="flex min-h-screen bg-paper-50">
      {/* Desktop sidebar. Ink, so the chrome has weight and the content reads as paper. */}
      <aside className="sticky top-0 hidden h-screen w-[17rem] shrink-0 flex-col bg-ink-900 bg-survey-dark lg:flex" style={{ backgroundSize: "56px 56px" }}>
        <div className="border-b border-white/10 px-4 py-3.5"><Logo dark /></div>
        <nav className="flex-1 overflow-y-auto">
          <NavList groups={groups} activeHref={activeHref} />
        </nav>
        {footer}
      </aside>

      {/* Mobile drawer — the shell previously had no drawer at all, only a
          horizontally scrolling strip of thirteen links. */}
      <div
        className={clsx("fixed inset-0 z-50 bg-ink-900/50 backdrop-blur-sm transition-opacity duration-panel lg:hidden", drawer ? "opacity-100" : "pointer-events-none opacity-0")}
        onClick={() => setDrawer(false)}
        aria-hidden
      />
      <aside
        className={clsx("fixed inset-y-0 left-0 z-50 flex w-[80%] max-w-[19rem] flex-col bg-ink-900 shadow-2xl transition-transform duration-panel ease-settle lg:hidden", drawer ? "translate-x-0" : "-translate-x-full")}
        role="dialog"
        aria-modal={drawer}
        aria-label="Main menu"
      >
        <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <Logo dark />
          <button onClick={() => setDrawer(false)} className="rounded-lg p-2 text-brand-100 hover:bg-white/10" aria-label="Close menu"><X className="h-5 w-5" /></button>
        </div>
        <nav className="flex-1 overflow-y-auto">
          <NavList groups={groups} activeHref={activeHref} onNavigate={() => setDrawer(false)} withRail={false} />
        </nav>
        {footer}
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-paper-200 bg-paper-50/90 px-4 py-2.5 backdrop-blur lg:hidden">
          <button onClick={() => setDrawer(true)} className="rounded-lg p-2 text-navy-800 hover:bg-paper-100" aria-label="Open menu" aria-expanded={drawer}>
            <Menu className="h-5 w-5" />
          </button>
          <span className="min-w-0 flex-1 truncate font-display text-base font-bold text-navy-800">{activeLabel}</span>
          <Link href="/app/notifications" className="rounded-lg p-2 text-navy-800 hover:bg-paper-100" aria-label="Notifications"><Bell className="h-5 w-5" /></Link>
          <Link href="/app/profile" className="rounded-lg p-2 text-navy-800 hover:bg-paper-100" aria-label="Profile"><User className="h-5 w-5" /></Link>
        </header>

        <main id="main" key={pathname} className={clsx("min-w-0 flex-1 p-4 sm:p-6 lg:p-8", !reduced && "animate-settle-up")}>
          {children}
        </main>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b border-paper-200 pb-4">
      <div className="min-w-0">
        <h1 className="font-display text-2xl font-bold tracking-tight text-navy-800 md:text-display-sm">{title}</h1>
        {subtitle && <p className="prose-body mt-1.5 text-sm">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}
