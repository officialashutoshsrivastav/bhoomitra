"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Loading, Pagination, StatusBadge, Tabs } from "@/components/ui";
import { fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi, useDebounce } from "@/lib/hooks";

function DatasetsInner() {
  const sp = useSearchParams();
  const { can } = useAuth();
  const [tab, setTab] = useState(sp.get("tab") || "all");
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [page, setPage] = useState(1);
  const path = tab === "pending" ? "/datasets/pending-approval" : "/datasets";
  const params = useMemo(() => ({ q: dq, page, page_size: 15, mine: tab === "mine" ? true : undefined }), [dq, page, tab]);
  const { data, loading } = useApi<any>(path, params);
  return (
    <>
      <PageHeader title="Dataset catalogue" subtitle="Versioned tabular and geospatial datasets with profiling, observation ingestion and approval." action={can("dataset.upload") ? <Link href="/app/datasets/new" className="btn-primary"><Plus className="h-4 w-4" /> Register dataset</Link> : null} />
      <SearchBar value={q} onChange={setQ} placeholder="Search datasets…" />
      <div className="mt-3"><Tabs tabs={[{ id: "all", label: "All accessible" }, { id: "mine", label: "Mine" }, ...(can("dataset.approve") ? [{ id: "pending", label: "Pending approval" }] : [])]} value={tab} onChange={(v) => { setTab(v); setPage(1); }} /></div>
      {loading ? <Loading /> : data?.items?.length ? (
        <div className="card mt-4 overflow-x-auto"><table className="table"><thead><tr><th>Name</th><th>Category</th><th>Status</th><th>Coverage</th><th>Period</th><th>Rows</th><th>Updated</th></tr></thead><tbody>{data.items.map((d: any) => <tr key={d.id}><td><Link href={`/app/datasets/${d.id}`} className="font-medium text-navy-800 hover:text-brand-700">{d.name}</Link> <DemoBadge show={d.is_demo} /></td><td>{titleCase(d.category)}</td><td><StatusBadge status={d.status} /></td><td>{d.geography || "—"}</td><td className="whitespace-nowrap">{d.temporal_start?.slice(0, 4)}–{d.temporal_end?.slice(0, 4)}</td><td>{fmtNum(d.row_count)}</td><td>{fmtDate(d.updated_at)}</td></tr>)}</tbody></table></div>
      ) : <div className="mt-4"><Empty title="No datasets" /></div>}
      <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
    </>
  );
}

export default function AppDatasetsPage() {
  return <Suspense fallback={<Loading />}><DatasetsInner /></Suspense>;
}
