"use client";

import { Download, Upload } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, KV, Loading, StatusBadge, Tabs, ValueKind } from "@/components/ui";
import { api, downloadWithAuth, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

export default function AppDatasetPage() {
  const { id } = useParams<{ id: string }>();
  const { user, can } = useAuth();
  const { data: ds, loading, error, reload } = useApi<any>(`/datasets/${id}`);
  const [tab, setTab] = useState("profile");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const { data: obs } = useApi<any>(tab === "observations" ? `/datasets/${id}/observations` : null, { page_size: 100 }, [tab]);
  const act = async (path: string, body?: any) => { setBusy(true); setErr(null); try { await api(path, { body: body ?? {} }); await reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const upload = async () => { if (!file) return; setBusy(true); setErr(null); try { const form = new FormData(); form.append("file", file); await api(`/datasets/${id}/versions`, { form }); setFile(null); await reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  if (loading) return <Loading />;
  if (error || !ds) return <Alert kind="error">Dataset not found or not accessible.</Alert>;
  const owner = ds.owner_id === user?.id;
  const current = ds.versions?.find((v: any) => v.id === ds.current_version_id) || ds.versions?.[ds.versions.length - 1];
  const profile = current?.schema_snapshot || {};
  return (
    <>
      <PageHeader title={ds.name} subtitle={`${titleCase(ds.category)} · ${ds.access_level} · owner ${owner ? "you" : "other"}`} action={<div className="flex flex-wrap gap-2">{current && <button className="btn-secondary" onClick={() => downloadWithAuth(`/datasets/${id}/download`, current.file_name)}><Download className="h-4 w-4" /> Download</button>}{ds.status === "draft" && (owner || can("dataset.approve")) && current && <button className="btn-primary" disabled={busy} onClick={() => act(`/datasets/${id}/submit`)}>Submit for approval</button>}{ds.status === "pending_approval" && can("dataset.approve") && <><button className="btn-primary" disabled={busy} onClick={() => act(`/datasets/${id}/approve`, { decision: "approve", note: note || undefined })}>Approve</button><button className="btn-danger" disabled={busy} onClick={() => act(`/datasets/${id}/approve`, { decision: "reject", note: note || "Rejected" })}>Reject</button></>}{ds.status === "approved" && can("dataset.approve") && <button className="btn-primary" disabled={busy} onClick={() => act(`/datasets/${id}/publish`)}>Publish</button>}{ds.status === "published" && (owner || can("dataset.delete")) && <button className="btn-ghost" disabled={busy} onClick={() => act(`/datasets/${id}/archive`)}>Archive</button>}</div>} />
      <div className="mb-3 flex flex-wrap items-center gap-2"><StatusBadge status={ds.status} /><DemoBadge show={ds.is_demo} />{ds.status === "pending_approval" && can("dataset.approve") && <input className="input ml-2 max-w-sm" placeholder="Decision note" value={note} onChange={(e) => setNote(e.target.value)} />}</div>
      <ErrorText error={err} />
      <Tabs tabs={[{ id: "profile", label: "Profile" }, { id: "observations", label: "Observations", count: ds.observation_count }, { id: "versions", label: "Versions", count: ds.versions?.length }, { id: "analyse", label: "Analyse" }]} value={tab} onChange={setTab} />
      {tab === "profile" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2">
            <p className="text-slate-700">{ds.description || "No description."}</p>
            {profile.columns ? (
              <div className="mt-4 overflow-x-auto"><h3 className="mb-2 font-bold text-navy-800">Schema profile (v{current?.version_number})</h3><table className="table"><thead><tr><th>Column</th><th>Type</th><th>Nulls</th><th>Distinct</th><th>Min</th><th>Max</th><th>Mean</th></tr></thead><tbody>{Object.entries(profile.columns).map(([name, c]: any) => <tr key={name}><td className="font-mono text-xs">{name}</td><td>{c.type}</td><td>{c.nulls}</td><td>{c.distinct}</td><td>{c.min ?? "—"}</td><td>{c.max ?? "—"}</td><td>{c.mean !== undefined && c.mean !== null ? fmtNum(c.mean, 2) : "—"}</td></tr>)}</tbody></table><p className="mt-2 text-xs text-slate-500">{profile.row_count} rows · {profile.column_count} columns · {profile.observations_ingested ?? 0} observations ingested</p></div>
            ) : <p className="mt-3 text-sm text-slate-500">No version uploaded yet.</p>}
            {ds.variables?.length > 0 && <div className="mt-4"><h3 className="font-bold text-navy-800">Variables</h3><ul className="mt-1 text-sm">{ds.variables.map((v: any) => <li key={v.code}><code className="text-xs">{v.code}</code> — {v.name} {v.unit ? `(${v.unit})` : ""}</li>)}</ul></div>}
          </div>
          <div className="card p-5"><KV items={[["Publisher", ds.publisher], ["Source", ds.source?.name], ["Coverage", ds.geography], ["Period", `${fmtDate(ds.temporal_start)} – ${fmtDate(ds.temporal_end)}`], ["Resolution", `${ds.spatial_resolution || "—"} / ${ds.temporal_resolution || "—"}`], ["Licence", ds.license], ["Quality", ds.quality_score != null ? `${Math.round(ds.quality_score * 100)}%` : "—"], ["Provenance", ds.provenance]]} />{ds.status === "published" && <Link href={`/datasets/${ds.id}`} className="btn-secondary mt-4 w-full">Public page</Link>}</div>
        </div>
      )}
      {tab === "observations" && <div className="card mt-4 overflow-x-auto"><table className="table"><thead><tr><th>Variable</th><th>Geography</th><th>Period</th><th>Value</th><th>Unit</th><th>Kind</th></tr></thead><tbody>{(obs?.items || []).map((o: any) => <tr key={o.id}><td className="font-mono text-xs">{o.variable_code}</td><td>{o.geography_label || "—"}{o.admin_unit_id ? "" : <span className="ml-1 text-[10px] text-amber-700">unlinked</span>}</td><td>{o.period_start?.slice(0, 10)}</td><td>{fmtNum(o.value, 3)}</td><td>{o.unit || ""}</td><td><ValueKind kind={o.value_kind} /></td></tr>)}</tbody></table>{!obs?.items?.length && <p className="p-4 text-sm text-slate-500">No observations ingested — upload a long or wide format table with a variable/year/value structure.</p>}{obs?.total > 100 && <p className="p-2 text-xs text-slate-500">Showing 100 of {obs.total}. Export via Reports → dataset export.</p>}</div>}
      {tab === "versions" && (
        <div className="mt-4 space-y-4">
          {(owner || can("dataset.update")) && ds.status !== "archived" && <div className="card flex flex-wrap items-center gap-3 p-4"><Upload className="h-5 w-5 text-brand-600" /><input type="file" className="input max-w-sm" onChange={(e) => setFile(e.target.files?.[0] || null)} /><button className="btn-primary" disabled={!file || busy} onClick={upload}>Upload new version</button></div>}
          <div className="card overflow-x-auto"><table className="table"><thead><tr><th>Version</th><th>File</th><th>Status</th><th>Rows</th><th>Columns</th><th>Checksum</th><th>Uploaded</th></tr></thead><tbody>{ds.versions.map((v: any) => <tr key={v.id}><td>v{v.version_number} {v.id === ds.current_version_id && <span className="badge bg-brand-100 text-brand-800">current</span>}</td><td>{v.file_name}</td><td><StatusBadge status={v.processing_status} />{v.processing_error && <div className="text-xs text-red-600">{v.processing_error}</div>}</td><td>{fmtNum(v.row_count)}</td><td>{v.column_count}</td><td className="font-mono text-[10px]">{v.checksum_sha256?.slice(0, 12)}…</td><td>{fmtDate(v.created_at)}</td></tr>)}</tbody></table></div>
        </div>
      )}
      {tab === "analyse" && <div className="card mt-4 p-5"><p className="text-sm text-slate-700">Run trend, comparison, anomaly, forecast or spatial roll-up on this dataset in the analytics engine.</p><Link href={`/app/analytics?dataset_version_id=${current?.id || ""}&variable_code=${ds.variables?.[0]?.code || ""}`} className="btn-primary mt-3">Open analytics with this version →</Link></div>}
    </>
  );
}
