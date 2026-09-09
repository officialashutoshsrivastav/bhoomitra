"use client";

import { Download, RefreshCw, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, KV, Loading, StatusBadge, Tabs } from "@/components/ui";
import { api, downloadWithAuth, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

const STAGES = ["UPLOADED", "VALIDATING", "PROCESSING", "OCR_RUNNING", "INDEXING", "READY"];

export default function RepoDocumentPage() {
  const { id } = useParams<{ id: string }>();
  const { user, can } = useAuth();
  const { data: doc, loading, error, reload } = useApi<any>(`/documents/${id}`);
  const [tab, setTab] = useState("overview");
  const [status, setStatus] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [comment, setComment] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const { data: chunks } = useApi<any>(tab === "text" ? `/documents/${id}/chunks` : null, { page_size: 100 }, [tab, doc?.current_version_id]);
  const current = doc?.versions?.find((v: any) => v.id === doc.current_version_id) || doc?.versions?.[doc?.versions?.length - 1];
  const processing = current && !["READY", "FAILED"].includes(current.processing_status);

  useEffect(() => {
    if (!current) return;
    let stop = false;
    const tick = async () => {
      try {
        const s = await api(`/documents/${id}/versions/${current.id}/status`);
        if (stop) return;
        setStatus(s);
        if (["READY", "FAILED"].includes(s.processing_status)) { reload(); return; }
        setTimeout(tick, 1500);
      } catch {}
    };
    tick();
    return () => { stop = true; };
  }, [current?.id, current?.processing_status]);

  const act = async (path: string, body?: any) => {
    setBusy(true); setErr(null);
    try { await api(path, { body: body ?? {} }); await reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  const upload = async () => {
    if (!file) return;
    setBusy(true); setErr(null);
    try { const form = new FormData(); form.append("file", file); form.append("change_note", "New version"); await api(`/documents/${id}/versions`, { form }); setFile(null); await reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  if (loading) return <Loading />;
  if (error || !doc) return <Alert kind="error">Document not found or you do not have access.</Alert>;
  const owner = doc.created_by === user?.id;
  const stageIdx = STAGES.indexOf(status?.processing_status || current?.processing_status || "");
  return (
    <>
      <PageHeader title={doc.title} subtitle={`${titleCase(doc.document_type)} · created ${fmtDate(doc.created_at)}`} action={<div className="flex flex-wrap gap-2">{current?.processing_status === "READY" && <button className="btn-secondary" onClick={() => downloadWithAuth(`/documents/${doc.id}/download`, current.file_name)}><Download className="h-4 w-4" /> Download</button>}{doc.status === "draft" && (owner || can("document.update")) && current && <button className="btn-primary" disabled={busy} onClick={() => act(`/documents/${id}/submit`)}>Submit for review</button>}{doc.status === "in_review" && can("document.review") && <><button className="btn-primary" disabled={busy} onClick={() => act(`/documents/${id}/review`, { decision: "approve", comments: comment || undefined })}>Approve</button><button className="btn-secondary" disabled={busy} onClick={() => act(`/documents/${id}/review`, { decision: "request_changes", comments: comment || "Please revise" })}>Request changes</button><button className="btn-danger" disabled={busy} onClick={() => act(`/documents/${id}/review`, { decision: "reject", comments: comment || "Rejected" })}>Reject</button></>}{doc.status === "approved" && can("document.publish") && <button className="btn-primary" disabled={busy} onClick={() => act(`/documents/${id}/publish`)}>Publish</button>}{doc.status === "published" && can("document.publish", "document.delete") && <button className="btn-ghost" disabled={busy} onClick={() => act(`/documents/${id}/archive`)}>Archive</button>}</div>} />
      <div className="mb-3 flex flex-wrap items-center gap-2"><StatusBadge status={doc.status} /><span className="badge bg-slate-100 text-slate-700">{doc.visibility}</span><DemoBadge show={doc.is_demo} />{doc.status === "in_review" && can("document.review") && <input className="input ml-2 max-w-sm" placeholder="Review comment (optional)" value={comment} onChange={(e) => setComment(e.target.value)} />}</div>
      <ErrorText error={err} />
      {current && (
        <div className="card mb-4 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><div className="text-sm font-semibold text-navy-800">Version {current.version_number} · {current.file_name} · {fmtNum(current.file_size / 1024)} KB</div><StatusBadge status={status?.processing_status || current.processing_status} /></div>
          <ol className="mt-3 flex flex-wrap gap-1 text-[11px]">{STAGES.map((s, i) => <li key={s} className={`rounded px-2 py-0.5 ${i < stageIdx ? "bg-brand-100 text-brand-800" : i === stageIdx ? (s === "READY" ? "bg-emerald-600 text-white" : "bg-brand-600 text-white") : "bg-slate-100 text-slate-500"}`}>{s.replace("_", " ")}</li>)}{(status?.processing_status || current.processing_status) === "FAILED" && <li className="rounded bg-red-600 px-2 py-0.5 text-white">FAILED</li>}</ol>
          {status?.job && <div className="mt-2 h-1.5 w-full overflow-hidden rounded bg-slate-100"><div className="h-full bg-brand-500 transition-all" style={{ width: `${status.job.progress || (current.processing_status === "READY" ? 100 : 5)}%` }} /></div>}
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">{processing && <span className="flex items-center gap-1"><RefreshCw className="h-3 w-3 animate-spin" /> processing…</span>}<span>{status?.chunks ?? current.chunk_count ?? 0} chunks</span>{current.page_count ? <span>{current.page_count} pages</span> : null}{status?.embedding_model && <span>{status.embedding_model}</span>}{(status?.processing_error || current.processing_error) && <span className="text-red-600">{status?.processing_error || current.processing_error}</span>}{(status?.processing_status || current.processing_status) === "FAILED" && (owner || can("document.update")) && <button className="text-brand-700 underline" onClick={() => act(`/documents/${id}/versions/${current.id}/retry`)}>Retry</button>}</div>
        </div>
      )}
      <Tabs tabs={[{ id: "overview", label: "Overview" }, { id: "versions", label: "Versions", count: doc.versions?.length }, { id: "text", label: "Extracted text" }, { id: "reviews", label: "Reviews", count: doc.reviews?.length }]} value={tab} onChange={setTab} />
      {tab === "overview" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2"><p className="text-slate-700">{doc.description || "No description."}</p>{doc.abstract && <><h3 className="mt-3 font-bold text-navy-800">Abstract</h3><p className="mt-1 text-sm text-slate-700">{doc.abstract}</p></>}<div className="mt-3 flex flex-wrap gap-1">{doc.keywords?.map((k: string) => <span key={k} className="badge bg-brand-50 text-brand-800">{k}</span>)}</div>{doc.related?.length > 0 && <div className="mt-4"><h3 className="font-bold text-navy-800">Related</h3><ul className="mt-1 text-sm">{doc.related.map((r: any) => <li key={r.id}><Link href={`/app/repository/${r.id}`} className="text-brand-700 hover:underline">{r.title}</Link> <span className="text-xs text-slate-500">({r.relation_type})</span></li>)}</ul></div>}</div>
          <div className="card p-5"><KV items={[["Authors", doc.authors?.join(", ")], ["Publisher", doc.publisher], ["Published", fmtDate(doc.publication_date)], ["Topic", doc.topic], ["Policy area", doc.policy_area], ["Geography", doc.geography], ["Language", doc.language], ["Licence", doc.license], ["Views / downloads", `${doc.view_count} / ${doc.download_count}`]]} />{doc.status === "published" && doc.visibility === "public" && <Link href={`/documents/${doc.id}`} className="btn-secondary mt-4 w-full">View public page</Link>}</div>
        </div>
      )}
      {tab === "versions" && (
        <div className="mt-4 space-y-4">
          {(owner || can("document.update")) && doc.status !== "archived" && <div className="card flex flex-wrap items-center gap-3 p-4"><Upload className="h-5 w-5 text-brand-600" /><input type="file" className="input max-w-sm" onChange={(e) => setFile(e.target.files?.[0] || null)} /><button className="btn-primary" disabled={!file || busy} onClick={upload}>Upload new version</button><span className="text-xs text-slate-500">Uploading a new version re-runs processing; duplicates are rejected by checksum.</span></div>}
          <div className="card overflow-x-auto"><table className="table"><thead><tr><th>Version</th><th>File</th><th>Status</th><th>Chunks</th><th>Pages</th><th>Checksum</th><th>Uploaded</th><th></th></tr></thead><tbody>{doc.versions.map((v: any) => <tr key={v.id} className={v.id === doc.current_version_id ? "bg-brand-50/40" : ""}><td>v{v.version_number}{v.id === doc.current_version_id && <span className="ml-1 badge bg-brand-100 text-brand-800">current</span>}</td><td className="max-w-[220px] truncate" title={v.file_name}>{v.file_name}</td><td><StatusBadge status={v.processing_status} /></td><td>{v.chunk_count}</td><td>{v.page_count ?? "—"}</td><td className="font-mono text-[10px]" title={v.checksum_sha256}>{v.checksum_sha256?.slice(0, 12)}…</td><td>{fmtDate(v.created_at)}</td><td>{v.id !== doc.current_version_id && v.processing_status === "READY" && (owner || can("document.update")) && <button className="text-xs text-brand-700 underline" onClick={() => act(`/documents/${id}/versions/${v.id}/set-current`)}>Set current</button>}</td></tr>)}</tbody></table></div>
        </div>
      )}
      {tab === "text" && <div className="card mt-4 divide-y divide-slate-100">{chunks?.items?.length ? chunks.items.map((c: any) => <div key={c.id} className="p-4 text-sm"><div className="mb-1 text-xs text-slate-500">Chunk {c.chunk_index + 1}{c.page_start ? ` · page ${c.page_start}` : ""}{c.ocr_applied ? " · OCR" : ""}{c.section_title ? ` · ${c.section_title}` : ""}</div><p className="whitespace-pre-wrap text-slate-700">{c.content}</p></div>) : <p className="p-4 text-sm text-slate-500">{processing ? "Text will appear once processing completes." : "No extracted text."}</p>}</div>}
      {tab === "reviews" && <div className="card mt-4 divide-y divide-slate-100">{doc.reviews?.length ? doc.reviews.map((r: any) => <div key={r.id} className="flex flex-wrap items-center gap-3 p-3 text-sm"><StatusBadge status={r.decision} /><span className="text-slate-500">{fmtDate(r.created_at)}</span><span className="text-slate-700">{r.comments || "—"}</span></div>) : <p className="p-4 text-sm text-slate-500">No reviews yet.</p>}</div>}
    </>
  );
}
