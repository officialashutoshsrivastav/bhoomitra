"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { DocumentCard, SearchBar } from "@/components/catalogue";
import { Empty, Loading, Pagination, Tabs } from "@/components/ui";
import { useAuth } from "@/lib/auth";
import { useApi, useDebounce } from "@/lib/hooks";

function RepoInner() {
  const sp = useSearchParams();
  const { can } = useAuth();
  const [tab, setTab] = useState(sp.get("tab") || "mine");
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [page, setPage] = useState(1);
  const path = tab === "review" ? "/documents/pending-review" : "/documents";
  const params = useMemo(() => ({ q: dq, page, page_size: 12, mine: tab === "mine" ? true : undefined, status: tab === "drafts" ? "draft" : tab === "published" ? "published" : undefined }), [dq, page, tab]);
  const { data, loading } = useApi<any>(path, params);
  const tabs = [{ id: "mine", label: "My documents" }, { id: "all", label: "All accessible" }, { id: "published", label: "Published" }, ...(can("document.review") ? [{ id: "review", label: "Awaiting review" }] : [])];
  return (
    <>
      <PageHeader title="Research repository" subtitle="Upload, process, review and publish documents. Every version is checksummed and processed through extraction, OCR, chunking and indexing." action={can("document.create") ? <Link href="/app/repository/new" className="btn-primary"><Plus className="h-4 w-4" /> New document</Link> : null} />
      <SearchBar value={q} onChange={setQ} placeholder="Search titles, keywords…" />
      <div className="mt-3"><Tabs tabs={tabs} value={tab} onChange={(v) => { setTab(v); setPage(1); }} /></div>
      {loading ? <Loading /> : data?.items?.length ? <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.items.map((d: any) => <DocumentCard key={d.id} d={d} href={`/app/repository/${d.id}`} />)}</div> : <div className="mt-4"><Empty title="No documents" hint={tab === "mine" ? "Create your first document to get started." : undefined} /></div>}
      <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
    </>
  );
}

export default function RepositoryPage() {
  return <Suspense fallback={<Loading />}><RepoInner /></Suspense>;
}
