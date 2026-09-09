"use client";

import { Download, FileText, Link2 } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Alert, DemoBadge, Hero, KV, Loading, Section, StatusBadge, Tabs } from "@/components/ui";
import { downloadUrl, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { data: doc, loading, error } = useApi<any>(`/documents/${id}`);
  const [tab, setTab] = useState("overview");
  const { data: chunks } = useApi<any>(user && tab === "text" ? `/documents/${id}/chunks` : null, { page_size: 50 }, [tab]);
  if (loading) return <Loading />;
  if (error || !doc) return <Section><Alert kind="error">Document not found or not published.</Alert></Section>;
  const current = doc.versions?.find((v: any) => v.id === doc.current_version_id) || doc.versions?.[0];
  return (
    <>
      <Hero title={doc.title} crumbs={[{ label: "Home", href: "/" }, { label: "Research", href: "/research" }, { label: doc.title.slice(0, 40) + (doc.title.length > 40 ? "…" : "") }]} />
      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <div className="mb-3 flex flex-wrap items-center gap-2"><span className="badge bg-blue-100 text-blue-800">{titleCase(doc.document_type)}</span><StatusBadge status={doc.status} /><DemoBadge show={doc.is_demo} />{doc.policy_area && <span className="badge bg-slate-100 text-slate-700">{doc.policy_area}</span>}</div>
            <Tabs tabs={[{ id: "overview", label: "Overview" }, { id: "versions", label: "Versions", count: doc.versions?.length }, { id: "related", label: "Related", count: doc.related?.length }, ...(user ? [{ id: "text", label: "Extracted text" }] : [])]} value={tab} onChange={setTab} />
            {tab === "overview" && (
              <div className="card mt-4 p-5">
                <p className="text-slate-700">{doc.description || "No description provided."}</p>
                {doc.abstract && <><h3 className="mt-4 font-bold text-navy-800">Abstract</h3><p className="mt-1 text-slate-700">{doc.abstract}</p></>}
                {doc.keywords?.length > 0 && <div className="mt-4 flex flex-wrap gap-1">{doc.keywords.map((k: string) => <span key={k} className="badge bg-brand-50 text-brand-800">{k}</span>)}</div>}
                {doc.reviews?.length > 0 && <><h3 className="mt-5 font-bold text-navy-800">Review history</h3><ul className="mt-2 space-y-1 text-sm">{doc.reviews.map((r: any) => <li key={r.id} className="flex flex-wrap gap-2 rounded border border-slate-100 px-2 py-1"><StatusBadge status={r.decision} /><span className="text-slate-500">{fmtDate(r.created_at)}</span><span className="text-slate-700">{r.comments || "—"}</span></li>)}</ul></>}
              </div>
            )}
            {tab === "versions" && (
              <div className="card mt-4 overflow-x-auto">
                <table className="table"><thead><tr><th>Version</th><th>File</th><th>Size</th><th>Processing</th><th>Pages</th><th>Change note</th><th>Date</th></tr></thead>
                  <tbody>{doc.versions?.map((v: any) => <tr key={v.id}><td>v{v.version_number}{v.version_label && <span className="text-xs text-slate-500"> ({v.version_label})</span>}</td><td className="max-w-[200px] truncate" title={v.file_name}>{v.file_name}</td><td>{fmtNum(v.file_size / 1024)} KB</td><td><StatusBadge status={v.processing_status} /></td><td>{v.page_count ?? "—"}</td><td>{v.change_note || "—"}</td><td>{fmtDate(v.created_at)}</td></tr>)}</tbody></table>
              </div>
            )}
            {tab === "related" && (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                {doc.related?.length ? doc.related.map((r: any) => <Link key={r.id} href={`/documents/${r.id}`} className="card flex items-start gap-3 p-4 hover:shadow-lg"><Link2 className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" /><div><div className="text-xs uppercase text-slate-500">{r.relation_type}</div><div className="font-semibold text-navy-800">{r.title}</div><div className="text-xs text-slate-500">{titleCase(r.document_type)}</div></div></Link>) : <p className="text-sm text-slate-500">No related documents linked.</p>}
              </div>
            )}
            {tab === "text" && (
              <div className="card mt-4 divide-y divide-slate-100">
                {chunks?.items?.length ? chunks.items.map((c: any) => <div key={c.id} className="p-4 text-sm"><div className="mb-1 text-xs text-slate-500">Chunk {c.chunk_index + 1}{c.page_start ? ` · page ${c.page_start}` : ""}{c.section_title ? ` · ${c.section_title}` : ""}</div><p className="whitespace-pre-wrap text-slate-700">{c.content}</p></div>) : <p className="p-4 text-sm text-slate-500">No extracted text available.</p>}
              </div>
            )}
          </div>
          <aside className="space-y-4">
            <div className="card p-5">
              {current ? <a href={downloadUrl(`/documents/${doc.id}/download`)} className="btn-primary w-full"><Download className="h-4 w-4" /> Download {current.file_name?.split(".").pop()?.toUpperCase()}</a> : <span className="btn-ghost w-full text-slate-400"><FileText className="h-4 w-4" /> No file uploaded</span>}
              <div className="mt-4"><KV items={[["Authors", doc.authors?.join(", ")], ["Publisher", doc.publisher], ["Published", fmtDate(doc.publication_date)], ["Topic", doc.topic], ["Research area", doc.research_area], ["Geography", doc.geography], ["Language", doc.language], ["Source", doc.source], ["Licence", doc.license], ["DOI", doc.doi], ["Views", fmtNum(doc.view_count)], ["Downloads", fmtNum(doc.download_count)]]} /></div>
              {current?.checksum_sha256 && <p className="mt-3 break-all font-mono text-[10px] text-slate-400">sha256 {current.checksum_sha256}</p>}
            </div>
            {user && <Link href={`/app/repository/${doc.id}`} className="btn-secondary w-full">Open in repository workspace</Link>}
          </aside>
        </div>
      </Section>
    </>
  );
}
