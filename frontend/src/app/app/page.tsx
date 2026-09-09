"use client";

import { Activity, BarChart3, Bell, BookOpen, CheckSquare, Database, FlaskConical, Lightbulb, Map, Users, ArrowRight } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, Loading, StatCard, StatusBadge } from "@/components/ui";
import { Counter, Reveal, Stagger } from "@/components/motion";
import { PanelLoader } from "@/components/Loader";
import { fmtDate, fmtNum, titleCase } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";
import { usePrefersReducedMotion } from "@/lib/motion";

/** A panel is a section of the record, so it gets a titled head rule rather
 *  than a floating heading. */
function Panel({ title, hint, action, children, className }: { title: string; hint?: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={`card flex flex-col p-5 ${className || ""}`}>
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2 border-b border-paper-200 pb-2.5">
        <div className="min-w-0">
          <h2 className="font-display text-base font-bold text-navy-800">{title}</h2>
          {hint && <p className="meta mt-0.5">{hint}</p>}
        </div>
        {action}
      </div>
      <div className="min-w-0 flex-1">{children}</div>
    </section>
  );
}

/** A count that reads as a link when it points somewhere actionable. */
function CountRow({ label, value, href }: { label: string; value: number; href?: string }) {
  const inner = (
    <>
      <span className="text-slate-600">{label}</span>
      <span className="font-display text-lg font-bold tabular-nums text-navy-800 group-hover:text-brand-700">
        <Counter value={value ?? 0} duration={700} />
      </span>
    </>
  );
  const cls = "group flex items-center justify-between gap-3 rounded-lg px-2 py-2 -mx-2 transition-colors duration-tap";
  return href ? <Link href={href} className={`${cls} hover:bg-brand-50`}>{inner}</Link> : <div className={cls}>{inner}</div>;
}

const CHART_TIP = {
  contentStyle: { borderRadius: 10, border: "1px solid #eae5da", boxShadow: "0 8px 24px rgba(8,24,16,0.1)", fontSize: 12, fontFamily: "var(--font-inter)" },
  cursor: { fill: "rgba(15,95,58,0.05)" },
};

function CountBars({ data, tone }: { data: any[]; tone: string }) {
  const reduced = usePrefersReducedMotion();
  if (!data?.length) return <p className="py-8 text-center text-sm text-slate-400">No data yet</p>;
  return (
    <div className="h-52">
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#eae5da" vertical={false} />
          <XAxis dataKey="value" tick={{ fontSize: 10, fill: "#64748b" }} tickLine={false} axisLine={{ stroke: "#eae5da" }} interval={0} angle={-18} textAnchor="end" height={48} />
          <YAxis allowDecimals={false} tick={{ fontSize: 10, fill: "#94a3b8" }} tickLine={false} axisLine={false} width={38} />
          <Tooltip {...CHART_TIP} />
          <Bar dataKey="count" radius={[5, 5, 0, 0]} isAnimationActive={!reduced} animationDuration={900} animationEasing="ease-out">
            {data.map((_, i) => <Cell key={i} fill={tone} fillOpacity={1 - (i % 4) * 0.13} />)}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function DashboardPage() {
  const { user } = useAuth();
  const { data, loading } = useApi<any>("/dashboards/me");

  if (loading || !data) return <PanelLoader label="Preparing your dashboard…" />;

  const w = data.widgets || {};
  const my = w.my_activity || {};

  return (
    <>
      <PageHeader
        title={`Welcome, ${user?.full_name?.split(" ")[0] ?? ""}`}
        subtitle={`${user?.roles.map((r) => ROLE_LABELS[r] || r).join(", ")}${user?.organization_name ? ` · ${user.organization_name}` : ""}`}
        action={
          data.notifications_unread > 0 ? (
            <Link href="/app/notifications" className="btn-secondary btn-sm">
              <Bell className="h-4 w-4" aria-hidden /> {data.notifications_unread} unread
            </Link>
          ) : null
        }
      />

      {/* Was xl:grid-cols-7, which squeezed seven cards into a strip nobody
          could read. Now it steps 1 → 2 → 3 → 4. */}
      <Stagger className="grid grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4 lg:grid-cols-3 xl:grid-cols-4" step={55}>
        <StatCard label="My documents" value={fmtNum(my.documents)} color="blue" icon={<BookOpen />} />
        <StatCard label="My datasets" value={fmtNum(my.datasets)} color="brand" icon={<Database />} />
        <StatCard label="Workspaces" value={fmtNum(my.workspaces)} color="purple" icon={<Users />} />
        <StatCard label="Open tasks" value={fmtNum(my.tasks_open)} color="orange" icon={<CheckSquare />} />
        <StatCard label="AI questions" value={fmtNum(my.ai_questions)} color="blue" icon={<Activity />} />
        <StatCard label="Analytics runs" value={fmtNum(my.analytics_runs)} color="brand" icon={<BarChart3 />} />
        <StatCard label="Scenarios" value={fmtNum(my.scenarios)} color="purple" icon={<FlaskConical />} />
      </Stagger>

      <div className="mt-6 grid gap-4 sm:gap-5 xl:grid-cols-3">
        {w.review_queue && (
          <Reveal>
            <Panel title="Review queue" hint="Items waiting on you" className="h-full">
              <div className="divide-y divide-paper-200">
                <CountRow label="Documents in review" value={w.review_queue.documents_in_review} href="/app/repository?tab=review" />
                <CountRow label="Datasets pending approval" value={w.review_queue.datasets_pending} href="/app/datasets?tab=pending" />
                <CountRow label="Approvals pending" value={w.review_queue.approvals_pending} href="/app/admin/approvals" />
              </div>
            </Panel>
          </Reveal>
        )}

        {w.policy && (
          <Reveal delay={60} className="xl:col-span-2">
            <Panel
              title="Policy desk"
              hint={`${w.policy.active_policies} active policies · ${w.policy.scenarios_under_review} scenarios awaiting review`}
              className="h-full"
            >
              <ul className="divide-y divide-paper-200 text-sm">
                {(w.policy.recent_recommendations || []).map((r: any) => (
                  <li key={r.id} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <Link href={`/app/evidence/${r.id}`} className="block truncate font-medium text-navy-800 transition-colors duration-state hover:text-brand-700">{r.title}</Link>
                      <div className="meta mt-0.5">
                        {titleCase(r.kind)} · confidence {Math.round((r.confidence || 0) * 100)}% · {fmtDate(r.created_at)}
                      </div>
                    </div>
                    <DemoBadge show={r.is_demo} />
                  </li>
                ))}
                {!w.policy.recent_recommendations?.length && <li className="py-6 text-center text-slate-400">No recommendations yet.</li>}
              </ul>
            </Panel>
          </Reveal>
        )}

        {w.research && (
          <Reveal delay={60} className="xl:col-span-2">
            <Panel title="Research desk" hint={`${w.research.my_projects} projects led by you`} className="h-full">
              <ul className="divide-y divide-paper-200 text-sm">
                {(w.research.recent_publications || []).map((d: any) => (
                  <li key={d.id} className="flex items-center justify-between gap-3 py-2.5">
                    <Link href={`/app/repository/${d.id}`} className="min-w-0 truncate font-medium text-navy-800 transition-colors duration-state hover:text-brand-700">{d.title}</Link>
                    <span className="badge shrink-0 border border-blue-200 bg-blue-50 text-blue-800">{titleCase(d.document_type)}</span>
                  </li>
                ))}
                {!w.research.recent_publications?.length && <li className="py-6 text-center text-slate-400">No publications yet.</li>}
              </ul>
            </Panel>
          </Reveal>
        )}

        {w.gis && (
          <Reveal delay={90}>
            <Panel title="Geospatial" className="h-full" action={<Link href="/app/gis" className="text-xs font-semibold text-brand-700 hover:text-brand-800">Open</Link>}>
              <div className="divide-y divide-paper-200">
                <CountRow label="Layers" value={w.gis.layers} />
                <CountRow label="Features" value={w.gis.features} />
                <CountRow label="Spatial runs" value={w.gis.spatial_runs} />
                <CountRow label="RS scenes" value={w.gis.rs_scenes} />
              </div>
              <Link href="/app/gis" className="btn-secondary btn-sm mt-4 w-full"><Map className="h-4 w-4" aria-hidden /> Open workbench</Link>
            </Panel>
          </Reveal>
        )}

        {w.innovation && (
          <Reveal delay={90}>
            <Panel title="Innovation" className="h-full">
              <div className="divide-y divide-paper-200">
                <CountRow label="Open challenges" value={w.innovation.open_challenges} />
                <CountRow label="Awaiting evaluation" value={w.innovation.submissions_awaiting_evaluation} />
                <CountRow label="Active pilots" value={w.innovation.pilots_active} />
              </div>
              <Link href="/app/innovation" className="btn-secondary btn-sm mt-4 w-full"><Lightbulb className="h-4 w-4" aria-hidden /> Evaluate</Link>
            </Panel>
          </Reveal>
        )}

        {w.national && (
          <Reveal delay={120} className="xl:col-span-3">
            <Panel
              title="National overview"
              action={<Link href="/app/admin" className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-800">Details <ArrowRight className="h-3 w-3" aria-hidden /></Link>}
            >
              <div className="grid gap-6 lg:grid-cols-2">
                <div>
                  <div className="mb-2 text-xs font-semibold tracking-wide text-slate-500">Documents by type</div>
                  <CountBars data={w.national.documents_by_type} tone="#0f5f3a" />
                </div>
                <div>
                  <div className="mb-2 text-xs font-semibold tracking-wide text-slate-500">Policies by area</div>
                  <CountBars data={w.national.policies_by_area} tone="#f28c28" />
                </div>
              </div>
              <div className="mt-4 flex flex-wrap gap-1.5 border-t border-paper-200 pt-3">
                {(w.national.states || []).map((s: any) => (
                  <span key={s.id} className="badge border border-paper-200 bg-paper-100 text-slate-700">
                    {s.name} <span className="tabular-nums text-slate-400">{s.districts}</span>
                    {s.is_demo && <span className="text-amber-600">·demo</span>}
                  </span>
                ))}
              </div>
            </Panel>
          </Reveal>
        )}

        {w.admin && (
          <Reveal delay={120} className="xl:col-span-3">
            <Panel title="Platform health">
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
                {[
                  { label: "Users", value: w.admin.users.total, sub: `${w.admin.users.pending} pending` },
                  { label: "Approvals pending", value: w.admin.approvals_pending },
                  { label: "Processing", value: w.admin.processing.versions_in_progress, sub: `${w.admin.processing.versions_failed} failed` },
                  { label: "Jobs queued", value: w.admin.processing.jobs_queued },
                  { label: "Failed logins (24h)", value: w.admin.failed_logins_24h },
                ].map((m) => (
                  <div key={m.label} className="rounded-lg border border-paper-200 bg-paper-50 p-3">
                    <div className="meta">{m.label}</div>
                    <div className="mt-1 font-display text-xl font-bold tabular-nums text-navy-800">
                      <Counter value={m.value ?? 0} duration={700} />
                    </div>
                    {m.sub && <div className="meta mt-0.5">{m.sub}</div>}
                  </div>
                ))}
              </div>
              {w.admin.processing.jobs_failed > 0 && (
                <Alert kind="warn" className="mt-4">
                  {w.admin.processing.jobs_failed} background job(s) failed — see <Link href="/app/admin/jobs" className="underline">jobs</Link>.
                </Alert>
              )}
            </Panel>
          </Reveal>
        )}
      </div>
    </>
  );
}
