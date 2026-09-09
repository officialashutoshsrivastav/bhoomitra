"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { FilterSidebar, SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Hero, Loading, Pagination, Section, Tabs } from "@/components/ui";
import { fmtNum, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TYPE_HREF: Record<string, (id: string) => string> = { document: (id) => `/documents/${id}`, dataset: (id) => `/datasets/${id}`, policy: () => `/policy`, challenge: (id) => `/innovation/${id}`, gis_layer: (id) => `/map?layer=${id}`, research_project: () => `/research`, admin_unit: (id) => `/map?unit=${id}` };

function SearchInner() {
  const sp = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState(sp.get("q") || "");
  const [submitted, setSubmitted] = useState(sp.get("q") || "");
  const [types, setTypes] = useState("");
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  useEffect(() => { setQ(sp.get("q") || ""); setSubmitted(sp.get("q") || ""); }, [sp]);
  const params = useMemo(() => ({ q: submitted, types: types || undefined, page, page_size: 15, ...filters }), [submitted, types, page, filters]);
  const { data, loading } = useApi<any>(submitted ? "/search" : null, params);
  const { data: facets } = useApi<any>("/search/facets");
  const submit = () => { setSubmitted(q); setPage(1); router.replace(`/search?q=${encodeURIComponent(q)}`); };
  const groups = [
    { key: "document_type", label: "Document type", options: facets?.document_type || [] },
    { key: "year", label: "Year", options: facets?.year || [] },
    { key: "geography", label: "Geography", options: facets?.geography || [] },
    { key: "policy_area", label: "Policy area", options: facets?.policy_area || [] },
  ];
  return (
    <>
      <Hero title="Search the" accent="Knowledge Base" subtitle="Hybrid keyword + semantic search across documents, datasets, policies, layers and challenges." crumbs={[{ label: "Home", href: "/" }, { label: "Search" }]} />
      <Section>
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <FilterSidebar groups={groups} values={filters} onChange={(k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); }} onReset={() => setFilters({})} />
          <div>
            <SearchBar value={q} onChange={setQ} onSubmit={submit} placeholder="Search policies, datasets, reports, places…" />
            <div className="mt-3"><Tabs tabs={[{ id: "", label: "All" }, { id: "document", label: "Documents" }, { id: "dataset", label: "Datasets" }, { id: "policy", label: "Policies" }, { id: "gis_layer", label: "Map layers" }, { id: "challenge", label: "Challenges" }, { id: "admin_unit", label: "Places" }]} value={types} onChange={(v) => { setTypes(v); setPage(1); }} /></div>
            {!submitted ? <div className="mt-4"><Empty title="Enter a query to search" hint="Try “drone survey boundary disputes” or “watershed groundwater”." /></div> : loading ? <Loading label="Searching…" /> : data?.items?.length ? (
              <>
                <p className="mt-3 text-xs text-slate-500">{fmtNum(data.total)} results · {data.relevance?.keyword_backend} + {data.relevance?.vector_backend} fused with {data.relevance?.fusion?.toUpperCase()} · {data.took_ms} ms</p>
                <ul className="mt-2 space-y-3">
                  {data.items.map((h: any) => (
                    <li key={`${h.entity_type}-${h.id}`} className="card p-4">
                      <div className="flex flex-wrap items-center gap-2"><span className="badge bg-navy-800 text-white">{titleCase(h.entity_type)}</span>{h.metadata?.document_type && <span className="badge bg-blue-100 text-blue-800">{titleCase(h.metadata.document_type)}</span>}<DemoBadge show={h.is_demo} />{h.matched_by?.map((m: string) => <span key={m} className={`badge ${m === "keyword" ? "bg-emerald-50 text-emerald-700" : "bg-purple-50 text-purple-700"}`}>{m}</span>)}</div>
                      <Link href={TYPE_HREF[h.entity_type]?.(h.id) || "#"} className="mt-1 block font-semibold text-navy-800 hover:text-brand-700">{h.title}</Link>
                      <p className="mt-1 text-sm text-slate-600" dangerouslySetInnerHTML={{ __html: (h.snippet || "").replace(/<(?!\/?b>)[^>]*>/g, "") }} />
                      <div className="mt-1 text-xs text-slate-400">score {h.score?.toFixed(4)}{h.keyword_score !== null && h.keyword_score !== undefined ? ` · keyword ${h.keyword_score.toFixed(3)}` : ""}{h.vector_score !== null && h.vector_score !== undefined ? ` · semantic ${h.vector_score.toFixed(3)}` : ""}{h.metadata?.geography ? ` · ${h.metadata.geography}` : ""}</div>
                    </li>
                  ))}
                </ul>
                <Pagination page={page} pages={data.pages || 1} onChange={setPage} />
              </>
            ) : <div className="mt-4"><Empty title="No results" hint="Try different terms or remove filters." /></div>}
          </div>
        </div>
      </Section>
    </>
  );
}

export default function SearchPage() {
  return <Suspense fallback={<Loading />}><SearchInner /></Suspense>;
}
