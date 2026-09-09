"use client";

import { ArrowRight, BarChart3, BookOpen, Brain, Database, FileText, Globe2, Lightbulb, Map, Scale, ShieldCheck, Workflow } from "lucide-react";
import Link from "next/link";
import { DemoBadge, Loading, Section, StatCard, StatusBadge } from "@/components/ui";
import { Reveal, Stagger } from "@/components/motion";
import { fmtDate, fmtNum, titleCase } from "@/lib/api";
import { usePrefersReducedMotion, useSequence } from "@/lib/motion";
import { useApi } from "@/lib/hooks";

const FEATURES = [
  { icon: BookOpen, title: "Research repository", text: "Versioned documents with OCR, metadata, peer review and provenance-linked citations.", href: "/research" },
  { icon: Database, title: "Dataset catalogue", text: "Profiled, versioned datasets with observations linked to administrative units.", href: "/datasets" },
  { icon: Map, title: "Interactive GIS", text: "PostGIS-backed layers, spatial statistics, hotspots and affected-area analysis.", href: "/map" },
  { icon: Brain, title: "Evidence-based AI", text: "Hybrid retrieval with citations, confidence and a full evidence trace for every answer.", href: "/features#ai" },
  { icon: BarChart3, title: "Analytics engine", text: "Trends, comparisons, anomalies, forecasts and composite risk scores with model cards.", href: "/features#analytics" },
  { icon: Workflow, title: "Policy simulation lab", text: "Transparent land-use scenarios with explicit assumptions and uncertainty bands.", href: "/features#simulation" },
  { icon: Lightbulb, title: "Innovation portal", text: "Challenges, submissions, structured evaluation and pilot tracking.", href: "/innovation" },
  { icon: ShieldCheck, title: "Governance & audit", text: "Thirteen roles, granular permissions, approvals and an append-only audit log.", href: "/features#security" },
];

/** The one orchestrated moment on the site: the map is fixed on the sheet, then
 *  the survey ring closes around it. Runs on mount only, never on scroll. */
function IndiaPlate() {
  const reduced = usePrefersReducedMotion();
  const step = useSequence(3, 320);
  const on = (n: number) => reduced || step >= n;

  return (
    <div className="relative mx-auto w-full max-w-[34rem] lg:max-w-none">
      <svg viewBox="0 0 100 100" className="absolute inset-0 h-full w-full" aria-hidden>
        <circle
          cx="50" cy="50" r="43" fill="none" stroke="#0f5f3a" strokeWidth="0.3" strokeDasharray="1.6 1.6" opacity="0.3"
          pathLength={1}
          style={{ strokeDasharray: 1, strokeDashoffset: on(3) ? 0 : 1, transition: reduced ? "none" : "stroke-dashoffset 1400ms var(--ease-survey)" }}
        />
        <circle cx="50" cy="50" r="47" fill="none" stroke="#0f5f3a" strokeWidth="0.2" opacity={on(3) ? 0.15 : 0} style={{ transition: "opacity 800ms var(--ease-settle)" }} />
      </svg>

      <img
        src="/hero-india.png"
        alt="Map of India composed of its landscapes, with an observation satellite overhead"
        className="relative w-full drop-shadow-2xl"
        style={{
          opacity: on(2) ? 1 : 0,
          transform: on(2) ? "none" : "translateY(14px) scale(0.98)",
          transition: reduced ? "none" : "opacity 900ms var(--ease-settle), transform 1100ms var(--ease-settle)",
        }}
      />
    </div>
  );
}

export default function HomePage() {
  const { data, loading } = useApi<any>("/dashboards/public-overview");
  const stat = (k: string) => data?.stats?.find((s: any) => s.key === k);

  return (
    <>
      {/* ---------------- Hero ---------------- */}
      <section className="relative isolate overflow-hidden">
        <div
          className="absolute inset-0 bg-cover bg-center motion-safe:animate-drift-slow"
          style={{ backgroundImage: "url('/hero-valley.png')" }}
          aria-hidden
        />
        <div className="absolute inset-0 bg-gradient-to-b from-paper-50 via-paper-50/85 to-paper-50 lg:bg-gradient-to-r lg:from-paper-50 lg:via-paper-50/90 lg:to-paper-50/40" aria-hidden />
        <div className="absolute inset-0 bg-survey opacity-40" style={{ backgroundSize: "28px 28px" }} aria-hidden />

        <div className="relative mx-auto grid max-w-7xl items-center gap-10 px-4 py-14 sm:px-6 lg:grid-cols-[1.05fr_0.95fr] lg:gap-14 lg:px-8 lg:py-24">
          <div>
            <Reveal from="none">
              <span className="badge border border-brand-200 bg-white/80 text-brand-800 backdrop-blur">
                <span className="h-1.5 w-1.5 rounded-full bg-brand-500" aria-hidden />
                Department of Land Resources · MoRD
              </span>
            </Reveal>

            <Reveal delay={90}>
              <h1 className="mt-5 font-display text-display-md font-bold leading-[1.03] tracking-tight text-navy-900 text-balance sm:text-display-lg lg:text-display-xl">
                Our land,<br />
                <span className="text-brand-600">our future</span>
              </h1>
            </Reveal>

            <Reveal delay={180}>
              <p className="prose-body mt-5 text-base sm:text-lg">
                A national platform for research, policy innovation and evidence-based land governance — bringing documents, datasets, maps, models and people into one accountable system.
              </p>
            </Reveal>

            <Reveal delay={270}>
              <div className="mt-7 flex flex-wrap gap-3">
                <Link href="/research" className="btn-primary">Explore research <ArrowRight className="h-4 w-4" aria-hidden /></Link>
                <Link href="/map" className="btn-secondary">Open the map</Link>
              </div>
            </Reveal>

            <Reveal delay={360}>
              <p className="mt-8 max-w-md border-l-2 border-brand-200 pl-3 text-xs leading-relaxed text-slate-500">
                Decision-support outputs carry evidence provenance and are not official government decisions. Records marked <DemoBadge /> are synthetic demonstration data.
              </p>
            </Reveal>
          </div>

          <IndiaPlate />
        </div>
      </section>

      {/* ---------------- Live counts ---------------- */}
      <section className="border-y border-paper-200 bg-white">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <h2 className="mb-5 text-xs font-semibold tracking-[0.12em] text-slate-500">PLATFORM AT A GLANCE</h2>
          {loading ? (
            <Loading variant="cards" rows={4} />
          ) : (
            <Stagger className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4" step={70}>
              <StatCard label="Research & policy documents" value={fmtNum(stat("documents")?.value)} sub="Published, public" color="blue" icon={<FileText />} demo={!!stat("documents")?.demo} />
              <StatCard label="Catalogued datasets" value={fmtNum(stat("datasets")?.value)} sub="Versioned, profiled" color="brand" icon={<Database />} demo={!!stat("datasets")?.demo} />
              <StatCard label="Policies tracked" value={fmtNum(stat("policies")?.value)} sub="With indicators" color="orange" icon={<Scale />} demo={!!stat("policies")?.demo} />
              <StatCard label="GIS layers" value={fmtNum(stat("gis_layers")?.value)} sub={`${fmtNum(stat("admin_units")?.value)} admin units`} color="purple" icon={<Globe2 />} demo={!!stat("gis_layers")?.demo} />
            </Stagger>
          )}
        </div>
      </section>

      {/* ---------------- Modules ---------------- */}
      <Section title="What the platform does" subtitle="Every module writes to the same evidence engine, so any output can be traced back to its sources." reveal>
        <Stagger className="grid gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-4" step={45}>
          {FEATURES.map((f) => (
            <Link key={f.title} href={f.href} className="card card-link group flex h-full flex-col p-5">
              <span className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-brand-100 bg-brand-50 text-brand-600 transition-colors duration-state group-hover:border-brand-300 group-hover:bg-brand-100" aria-hidden>
                <f.icon className="h-5 w-5" />
              </span>
              <h3 className="font-display text-base font-bold text-navy-800 transition-colors duration-state group-hover:text-brand-700">{f.title}</h3>
              <p className="mt-1.5 flex-1 text-sm leading-relaxed text-slate-600">{f.text}</p>
              <span className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-brand-600 opacity-0 transition-opacity duration-state group-hover:opacity-100">
                Open <ArrowRight className="h-3 w-3" aria-hidden />
              </span>
            </Link>
          ))}
        </Stagger>
      </Section>

      {/* ---------------- Recent + challenges ---------------- */}
      <div className="border-t border-paper-200 bg-paper-100">
        <Section title="Recently published" action={<Link href="/research" className="btn-secondary btn-sm">All publications</Link>} reveal>
          {loading ? (
            <Loading variant="grid" rows={3} />
          ) : (
            <Stagger className="grid gap-4 md:grid-cols-3" step={70}>
              {(data?.recent_documents || []).map((d: any) => (
                <Link key={d.id} href={`/documents/${d.id}`} className="card card-link flex h-full flex-col p-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="badge border border-blue-200 bg-blue-50 text-blue-800">{titleCase(d.document_type)}</span>
                    <DemoBadge show={d.is_demo} />
                  </div>
                  <h3 className="mt-3 line-clamp-3 flex-1 font-display text-base font-semibold leading-snug text-navy-800">{d.title}</h3>
                  <p className="meta mt-3 border-t border-paper-200 pt-2.5">{fmtDate(d.publication_date)}</p>
                </Link>
              ))}
              {!data?.recent_documents?.length && <p className="text-sm text-slate-500">No published documents yet.</p>}
            </Stagger>
          )}
        </Section>

        <Section title="Open innovation challenges" action={<Link href="/innovation" className="btn-secondary btn-sm">Innovation portal</Link>} reveal className="pt-0">
          <Stagger className="grid gap-4 md:grid-cols-2" step={70}>
            {(data?.open_challenges || []).map((c: any) => (
              <Link key={c.id} href={`/innovation/${c.id}`} className="card card-link flex h-full items-start gap-4 p-5">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 text-saffron" aria-hidden>
                  <Lightbulb className="h-5 w-5" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2"><StatusBadge status="open" /><DemoBadge show={c.is_demo} /></div>
                  <h3 className="mt-2 font-display text-base font-semibold text-navy-800">{c.title}</h3>
                  <p className="meta mt-1">Theme: {c.theme || "—"} · Closes {fmtDate(c.closes_at)}</p>
                </div>
              </Link>
            ))}
            {!data?.open_challenges?.length && <p className="text-sm text-slate-500">No open challenges at the moment.</p>}
          </Stagger>
        </Section>
      </div>

      {/* ---------------- Access ---------------- */}
      <section className="relative isolate overflow-hidden bg-ink-900 text-white">
        <div className="absolute inset-0 bg-survey-dark opacity-70" style={{ backgroundSize: "56px 56px" }} aria-hidden />
        <div className="absolute inset-y-0 right-0 hidden w-1/2 bg-cover bg-center opacity-20 lg:block" style={{ backgroundImage: "url('/banner-strip.png')" }} aria-hidden />
        <div className="relative mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-8 px-4 py-14 sm:px-6 lg:px-8">
          <div className="max-w-xl">
            <h2 className="font-display text-2xl font-bold leading-tight sm:text-display-sm">Built for researchers, officials, analysts and innovators</h2>
            <p className="mt-3 text-brand-100/70">
              Role-based workspaces, approvals and audit trails keep collaboration accountable — from a dataset upload to a policy simulation.
            </p>
          </div>
          <Link href="/signup" className="btn bg-white text-brand-800 hover:bg-brand-50">Request access <ArrowRight className="h-4 w-4" aria-hidden /></Link>
        </div>
      </section>
    </>
  );
}
