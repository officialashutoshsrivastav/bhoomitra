"use client";

import { BookOpen, Building2, Tags, Users } from "lucide-react";
import { useMemo, useState } from "react";
import { DocumentCard, FilterSidebar, SearchBar } from "@/components/catalogue";
import { Empty, Hero, Loading, Pagination, Section, StatCard, Tabs } from "@/components/ui";
import { fmtNum } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks";

const TABS = [{ id: "", label: "All publications" }, { id: "research_paper", label: "Research papers" }, { id: "policy_paper", label: "Policy papers" }, { id: "case_study", label: "Case studies" }, { id: "working_paper", label: "Working papers" }, { id: "technical_report", label: "Technical reports" }, { id: "government_report", label: "Government reports" }];

export default function ResearchPage() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState("-publication_date");
  const params = useMemo(() => ({ q: dq, page, page_size: 12, sort, ...filters }), [dq, page, sort, filters]);
  const { data, loading } = useApi<any>("/documents", params);
  const { data: facets } = useApi<any>("/search/facets");
  const groups = [
    { key: "document_type", label: "Content type", options: facets?.document_type || [] },
    { key: "year", label: "Year", options: facets?.year || [] },
    { key: "policy_area", label: "Focus area", options: facets?.policy_area || [] },
    { key: "geography", label: "Geography", options: facets?.geography || [] },
    { key: "language", label: "Language", options: facets?.language || [] },
  ];
  const set = (k: string, v: string) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1); };
  return (
    <>
      <Hero title="Research &" accent="Publications" subtitle="Explore research papers, reports, case studies and policy documents on land and environment." crumbs={[{ label: "Home", href: "/" }, { label: "Research & Publications" }]} tag="Knowledge for a Sustainable India" />
      <Section>
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <FilterSidebar groups={groups} values={filters} onChange={set} onReset={() => { setFilters({}); setPage(1); }} />
          <div>
            <SearchBar value={q} onChange={setQ} placeholder="Search research papers, reports, topics…" />
            <div className="my-4 grid grid-cols-2 gap-3 md:grid-cols-4">
              <StatCard label="Publications" value={fmtNum(data?.total)} sub="matching filters" color="blue" icon={<BookOpen />} />
              <StatCard label="Content types" value={fmtNum(facets?.document_type?.length)} sub="in repository" color="brand" icon={<Tags />} />
              <StatCard label="Focus areas" value={fmtNum(facets?.policy_area?.length)} color="orange" icon={<Users />} />
              <StatCard label="Sources" value={fmtNum(facets?.source?.length)} color="purple" icon={<Building2 />} />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Tabs tabs={TABS} value={filters.document_type || ""} onChange={(v) => set("document_type", v)} />
              <select value={sort} onChange={(e) => setSort(e.target.value)} className="input w-auto"><option value="-publication_date">Latest first</option><option value="publication_date">Oldest first</option><option value="title">Title A–Z</option><option value="-downloads">Most downloaded</option></select>
            </div>
            {loading ? <Loading /> : data?.items?.length ? (
              <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.items.map((d: any) => <DocumentCard key={d.id} d={d} />)}</div>
            ) : <div className="mt-4"><Empty title="No publications match" hint="Try clearing filters or a broader search." /></div>}
            <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
          </div>
        </div>
      </Section>
    </>
  );
}
