"use client";

import { Bookmark, Trash2 } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { FilterSidebar, SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Loading, Pagination, Tabs } from "@/components/ui";
import { api, fmtNum, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const HREF: Record<string, (id: string) => string> = { document: (id) => `/app/repository/${id}`, dataset: (id) => `/app/datasets/${id}`, policy: () => `/policy`, challenge: (id) => `/innovation/${id}`, gis_layer: (id) => `/app/gis?layer=${id}`, research_project: () => `/research`, admin_unit: (id) => `/app/gis?unit=${id}` };

export default function AppSearchPage() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [types, setTypes] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({ q: submitted, types: types || undefined, page, page_size: 15, ...filters }), [submitted, types, page, filters]);
  const { data, loading } = useApi<any>(submitted ? "/search" : null, params);
  const { data: facets } = useApi<any>("/search/facets");
  const { data: saved, reload: reloadSaved } = useApi<any>("/search/saved");
  const { data: recent } = useApi<any>("/search/recent", {}, [submitted]);
  const save = async () => { await api("/search/saved", { body: { name: submitted.slice(0, 60), query: submitted, filters: { ...filters, types } } }); reloadSaved(); };
  const groups = [{ key: "document_type", label: "Document type", options: facets?.document_type || [] }, { key: "year", label: "Year", options: facets?.year || [] }, { key: "geography", label: "Geography", options: facets?.geography || [] }, { key: "policy_area", label: "Policy area", options: facets?.policy_area || [] }, { key: "topic", label: "Topic", options: facets?.topic || [] }];
  return (
    <>
      <PageHeader title="Search" subtitle="Hybrid keyword + semantic search across the whole repository, including internal documents you can access." />
      <div className="grid gap-6 lg:grid-cols-[260px_1fr_240px]">
        <FilterSidebar groups={groups} values={filters} onChange={(k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); }} onReset={() => setFilters({})} />
        <div>
          <SearchBar value={q} onChange={setQ} onSubmit={() => { setSubmitted(q); setPage(1); }} placeholder="e.g. groundwater recharge watershed" />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2"><Tabs tabs={[{ id: "", label: "All" }, { id: "document", label: "Documents" }, { id: "dataset", label: "Datasets" }, { id: "policy", label: "Policies" }, { id: "gis_layer", label: "Layers" }, { id: "challenge", label: "Challenges" }, { id: "admin_unit", label: "Places" }]} value={types} onChange={(v) => { setTypes(v); setPage(1); }} />{submitted && <button className="btn-ghost" onClick={save}><Bookmark className="h-4 w-4" /> Save search</button>}</div>
          {!submitted ? <div className="mt-4"><Empty title="Type a query" /></div> : loading ? <Loading label="Searching…" /> : data?.items?.length ? (
            <>
              <p className="mt-3 text-xs text-slate-500">{fmtNum(data.total)} results · {data.relevance?.keyword_backend} + {data.relevance?.vector_backend} · RRF · {data.took_ms} ms · {data.relevance?.embedding_model}</p>
              <ul className="mt-2 space-y-3">{data.items.map((h: any) => <li key={`${h.entity_type}-${h.id}`} className="card p-4"><div className="flex flex-wrap items-center gap-2"><span className="badge bg-navy-800 text-white">{titleCase(h.entity_type)}</span>{h.metadata?.status && <span className="badge bg-slate-100 text-slate-700">{h.metadata.status}</span>}<DemoBadge show={h.is_demo} />{h.matched_by?.map((m: string) => <span key={m} className={`badge ${m === "keyword" ? "bg-emerald-50 text-emerald-700" : "bg-purple-50 text-purple-700"}`}>{m}</span>)}</div><Link href={HREF[h.entity_type]?.(h.id) || "#"} className="mt-1 block font-semibold text-navy-800 hover:text-brand-700">{h.title}</Link><p className="mt-1 text-sm text-slate-600" dangerouslySetInnerHTML={{ __html: (h.snippet || "").replace(/<(?!\/?b>)[^>]*>/g, "") }} /><div className="mt-1 text-xs text-slate-400">fused {h.score?.toFixed(4)}{h.keyword_score != null ? ` · keyword ${h.keyword_score.toFixed(3)}` : ""}{h.vector_score != null ? ` · semantic ${h.vector_score.toFixed(3)}` : ""}</div></li>)}</ul>
              <Pagination page={page} pages={data.pages || 1} onChange={setPage} />
            </>
          ) : <div className="mt-4"><Empty title="No results" /></div>}
        </div>
        <aside className="space-y-4">
          <div className="card p-4"><h3 className="font-bold text-navy-800">Saved searches</h3><ul className="mt-2 space-y-1 text-sm">{(saved?.items || []).map((s: any) => <li key={s.id} className="flex items-center justify-between gap-2"><button className="truncate text-left text-brand-700 hover:underline" onClick={() => { setQ(s.query); setSubmitted(s.query); setFilters(s.filters || {}); }}>{s.name}</button><button className="text-slate-400 hover:text-red-600" onClick={async () => { await api(`/search/saved/${s.id}`, { method: "DELETE" }); reloadSaved(); }}><Trash2 className="h-3.5 w-3.5" /></button></li>)}{!saved?.items?.length && <li className="text-xs text-slate-500">None yet.</li>}</ul></div>
          <div className="card p-4"><h3 className="font-bold text-navy-800">Recent</h3><ul className="mt-2 space-y-1 text-sm">{(recent?.items || []).slice(0, 10).map((r: any, i: number) => <li key={i}><button className="truncate text-left text-slate-700 hover:text-brand-700" onClick={() => { setQ(r.query); setSubmitted(r.query); }}>{r.query} <span className="text-xs text-slate-400">({r.result_count})</span></button></li>)}{!recent?.items?.length && <li className="text-xs text-slate-500">No searches yet.</li>}</ul></div>
        </aside>
      </div>
    </>
  );
}
