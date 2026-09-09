"use client";

import { Building2, FileText, Landmark, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { FilterSidebar, SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Hero, Loading, Pagination, Section, StatCard, StatusBadge, Tabs, ValueKind } from "@/components/ui";
import { fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks";

export default function PolicyPage() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<any>(null);
  const params = useMemo(() => ({ q: dq, page, page_size: 12, ...filters }), [dq, page, filters]);
  const { data, loading } = useApi<any>("/policies", params);
  const { data: facets } = useApi<any>("/policies/facets");
  const { data: detail } = useApi<any>(selected ? `/policies/${selected.id}` : null, {}, [selected?.id]);
  const stats = useMemo(() => {
    if (!facets) return null;
    const total = (facets.status || []).reduce((a: number, s: any) => a + s.count, 0);
    return { total, by_area: facets.policy_area || [], by_level: facets.level || [], by_status: facets.status || [] };
  }, [facets]);
  const series = useMemo(() => ({ items: detail?.indicators || [] }), [detail]);
  const set = (k: string, v: string) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };
  const groups = [
    { key: "policy_area", label: "Policy area", options: stats?.by_area || [] },
    { key: "level", label: "Level", options: stats?.by_level || [] },
    { key: "status", label: "Status", options: stats?.by_status || [] },
  ];
  const chart = useMemo(() => {
    const byCode: Record<string, any[]> = {};
    (series?.items || []).forEach((i: any) => { (byCode[i.code] ||= []).push({ year: i.period_start?.slice(0, 4), value: i.value, kind: i.value_kind }); });
    return byCode;
  }, [series]);
  return (
    <>
      <Hero title="Policy" accent="Insights" subtitle="Evidence-based insights for informed policy decisions." crumbs={[{ label: "Home", href: "/" }, { label: "Policy Insights" }]} tag="Data for People-Centric Governance" />
      <Section>
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Policies tracked" value={fmtNum(stats?.total)} sub="Acts, rules, guidelines, schemes" color="orange" icon={<FileText />} />
          <StatCard label="Active" value={fmtNum(stats?.by_status?.find((s: any) => s.value === "active")?.count)} sub="Currently in force" color="brand" icon={<Landmark />} />
          <StatCard label="Policy areas" value={fmtNum(stats?.by_area?.length)} sub="Thematic coverage" color="blue" icon={<Building2 />} />
          <StatCard label="Ministries / departments" value={fmtNum(facets?.ministry?.length)} sub="Issuing bodies" color="purple" icon={<Users />} />
        </div>
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <FilterSidebar groups={groups} values={filters} onChange={set} onReset={() => { setFilters({}); setPage(1); }} />
          <div>
            <SearchBar value={q} onChange={setQ} placeholder="Search policies, schemes, guidelines…" />
            <div className="mt-3"><Tabs tabs={[{ id: "", label: "All" }, { id: "national", label: "National" }, { id: "state", label: "State" }]} value={filters.level || ""} onChange={(v) => set("level", v)} /></div>
            {loading ? <Loading /> : data?.items?.length ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2">
                {data.items.map((p: any) => (
                  <div key={p.id} className={`card flex flex-col p-4 ${selected?.id === p.id ? "ring-2 ring-brand-400" : ""}`}>
                    <div className="flex flex-wrap items-center gap-2"><span className="badge bg-orange-100 text-orange-800">{titleCase(p.level)}</span><StatusBadge status={p.status} /><DemoBadge show={p.is_demo} /></div>
                    <h3 className="mt-2 font-semibold text-navy-800">{p.title}</h3>
                    <p className="mt-1 line-clamp-3 flex-1 text-sm text-slate-600">{p.summary || "—"}</p>
                    <div className="mt-3 text-xs text-slate-500">{p.ministry || "—"} · Effective {fmtDate(p.effective_date)} · {p.policy_area}</div>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <button onClick={() => setSelected(p)} className="btn-secondary">Indicators</button>
                      {p.document_id ? <Link href={`/documents/${p.document_id}`} className="btn-primary">View document</Link> : <span className="btn-ghost text-slate-400">No document</span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <div className="mt-4"><Empty title="No policies match" /></div>}
            <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
            {selected && (
              <div className="card mt-6 p-5">
                <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold text-navy-800">Indicators — {selected.title}</h3><button className="btn-ghost" onClick={() => setSelected(null)}>Close</button></div>
                {Object.keys(chart).length ? Object.entries(chart).map(([code, pts]) => (
                  <div key={code} className="mt-4">
                    <div className="mb-1 flex items-center gap-2 text-sm font-semibold text-slate-700">{series?.items?.find((i: any) => i.code === code)?.name || code} <ValueKind kind={pts[0]?.kind} /><DemoBadge show={selected.is_demo} /></div>
                    <div className="h-52"><ResponsiveContainer><LineChart data={pts}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip /><Line type="monotone" dataKey="value" stroke="#0f5f3a" strokeWidth={2} /></LineChart></ResponsiveContainer></div>
                  </div>
                )) : <p className="mt-3 text-sm text-slate-500">No indicator series recorded for this policy.</p>}
              </div>
            )}
          </div>
        </div>
      </Section>
    </>
  );
}
