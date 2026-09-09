"use client";

import { Database, Download, Layers, Map, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { FilterSidebar, SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Hero, Loading, Pagination, Section, StatCard, StatusBadge } from "@/components/ui";
import { downloadUrl, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks";

export default function DatasetsPage() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({ q: dq, page, page_size: 12, ...filters }), [dq, page, filters]);
  const { data, loading } = useApi<any>("/datasets", params);
  const { data: facets } = useApi<any>("/datasets/facets");
  const groups = [
    { key: "category", label: "Category", options: facets?.category || [] },
    { key: "format", label: "Format", options: facets?.format || [] },
    { key: "access_level", label: "Access", options: facets?.access_level || [] },
    { key: "source_id", label: "Source", options: (facets?.sources || []).map((s: any) => ({ value: s.id, label: s.name })) },
  ];
  const set = (k: string, v: string) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };
  return (
    <>
      <Hero title="Data" accent="Catalogue" subtitle="Versioned, profiled datasets with provenance, licensing and administrative-unit linkage." crumbs={[{ label: "Home", href: "/" }, { label: "Datasets" }]} tag="Data for People-Centric Governance" />
      <Section>
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <FilterSidebar groups={groups} values={filters} onChange={set} onReset={() => { setFilters({}); setPage(1); }} />
          <div>
            <SearchBar value={q} onChange={setQ} placeholder="Search datasets, variables, keywords…" />
            <div className="my-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label="Datasets" value={fmtNum(data?.total)} sub="matching filters" color="brand" icon={<Database />} />
              <StatCard label="Categories" value={fmtNum(facets?.category?.length)} color="blue" icon={<Layers />} />
              <StatCard label="Formats" value={fmtNum(facets?.format?.length)} color="orange" icon={<Map />} />
              <StatCard label="Sources" value={fmtNum(facets?.sources?.length)} color="purple" icon={<ShieldCheck />} />
            </div>
            {loading ? <Loading /> : data?.items?.length ? (
              <div className="grid gap-4 md:grid-cols-2">
                {data.items.map((d: any) => (
                  <div key={d.id} className="card flex flex-col p-4">
                    <div className="flex flex-wrap items-center gap-2"><span className="badge bg-brand-100 text-brand-800">{titleCase(d.category)}</span><StatusBadge status={d.status} /><DemoBadge show={d.is_demo} /></div>
                    <Link href={`/datasets/${d.id}`} className="mt-2 font-semibold text-navy-800 hover:text-brand-700">{d.name}</Link>
                    <p className="mt-1 line-clamp-2 flex-1 text-sm text-slate-600">{d.description || "—"}</p>
                    <dl className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-slate-500">
                      <dt>Coverage</dt><dd className="text-slate-700">{d.geography || "—"}</dd>
                      <dt>Period</dt><dd className="text-slate-700">{fmtDate(d.temporal_start)} – {fmtDate(d.temporal_end)}</dd>
                      <dt>Format / licence</dt><dd className="text-slate-700">{d.format || "—"} · {d.license || "—"}</dd>
                      <dt>Quality</dt><dd className="text-slate-700">{d.quality_score !== null && d.quality_score !== undefined ? `${Math.round(d.quality_score * 100)}%` : "—"}</dd>
                    </dl>
                    <div className="mt-3 grid grid-cols-2 gap-2">
                      <Link href={`/datasets/${d.id}`} className="btn-secondary">Details</Link>
                      {d.current_version_id ? <a href={downloadUrl(`/datasets/${d.id}/download`)} className="btn-primary"><Download className="h-4 w-4" /> Download</a> : <span className="btn-ghost text-slate-400">No file</span>}
                    </div>
                  </div>
                ))}
              </div>
            ) : <Empty title="No datasets match" />}
            <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
          </div>
        </div>
      </Section>
    </>
  );
}
