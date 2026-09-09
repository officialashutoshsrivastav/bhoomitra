"use client";

import { Download, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorText, Field, Loading, StatusBadge } from "@/components/ui";
import { api, downloadWithAuth, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function ReportsPage() {
  const { data: types } = useApi<any>("/reports/types");
  const { data: reports, reload, loading } = useApi<any>("/reports", { page_size: 30 });
  const { data: datasets } = useApi<any>("/datasets", { page_size: 100 });
  const { data: layers } = useApi<any>("/gis/layers", { page_size: 100 });
  const { data: scenarios } = useApi<any>("/simulations/scenarios", { page_size: 50 });
  const { data: recs } = useApi<any>("/evidence/recommendations", { limit: 50 });
  const [f, setF] = useState<any>({ title: "", report_type: "repository_summary", format: "pdf", methodology: "", param: "" });
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { const t = setInterval(() => { if (reports?.items?.some((r: any) => ["queued", "running"].includes(r.status))) reload(); }, 2500); return () => clearInterval(t); }, [reports]);
  const paramKey: Record<string, string> = { dataset_export: "dataset_id", simulation_run: "run_id", analytics_run: "run_id", gis_layer_summary: "layer_id", evidence_trace: "recommendation_id", policy_indicators: "policy_id" };
  const create = async () => {
    setBusy(true); setErr(null);
    try { const parameters: any = {}; if (paramKey[f.report_type] && f.param) parameters[paramKey[f.report_type]] = f.param; await api("/reports", { body: { title: f.title || `${titleCase(f.report_type)} ${new Date().toISOString().slice(0, 10)}`, report_type: f.report_type, format: f.format, parameters, methodology: f.methodology || undefined, background: true } }); reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  const options = () => {
    if (f.report_type === "dataset_export") return (datasets?.items || []).map((d: any) => ({ id: d.id, label: d.name }));
    if (f.report_type === "gis_layer_summary") return (layers?.items || []).map((l: any) => ({ id: l.id, label: l.name }));
    if (f.report_type === "simulation_run") return (scenarios?.items || []).flatMap((s: any) => (s.runs || []).map((r: any) => ({ id: r.id, label: `${s.name} · run ${r.id.slice(0, 8)}` })));
    if (f.report_type === "evidence_trace") return (recs?.items || []).map((r: any) => ({ id: r.id, label: `${titleCase(r.kind)}: ${r.title}` }));
    return [];
  };
  return (
    <>
      <PageHeader title="Reports" subtitle="Generate PDF, CSV and XLSX reports with methodology, sources and disclaimers. Generation runs in the background." />
      <div className="grid gap-4 lg:grid-cols-[360px_1fr]">
        <div className="card space-y-3 p-4">
          <Field label="Report type"><select className="input" value={f.report_type} onChange={(e) => setF({ ...f, report_type: e.target.value, param: "" })}>{(types?.types || []).map((t: string) => <option key={t} value={t}>{titleCase(t)}</option>)}</select></Field>
          {paramKey[f.report_type] && (options().length ? <Field label={titleCase(paramKey[f.report_type])}><select className="input" value={f.param} onChange={(e) => setF({ ...f, param: e.target.value })}><option value="">— choose —</option>{options().map((o: any) => <option key={o.id} value={o.id}>{o.label}</option>)}</select></Field> : <Field label={titleCase(paramKey[f.report_type])}><input className="input font-mono text-xs" value={f.param} onChange={(e) => setF({ ...f, param: e.target.value })} placeholder="UUID" /></Field>)}
          <Field label="Format"><select className="input" value={f.format} onChange={(e) => setF({ ...f, format: e.target.value })}>{(types?.formats || ["pdf", "csv", "xlsx"]).map((x: string) => <option key={x} value={x}>{x.toUpperCase()}</option>)}</select></Field>
          <Field label="Title"><input className="input" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label="Methodology note"><textarea className="input" rows={3} value={f.methodology} onChange={(e) => setF({ ...f, methodology: e.target.value })} /></Field>
          <ErrorText error={err} />
          <button className="btn-primary w-full" disabled={busy || (!!paramKey[f.report_type] && !f.param)} onClick={create}>{busy ? "Queuing…" : "Generate report"}</button>
        </div>
        <div className="card overflow-x-auto">
          <div className="flex items-center justify-between p-3"><h3 className="font-bold text-navy-800">My reports</h3><button className="btn-ghost" onClick={reload}><RefreshCw className="h-4 w-4" /></button></div>
          {loading ? <Loading /> : <table className="table"><thead><tr><th>Title</th><th>Type</th><th>Format</th><th>Status</th><th>Size</th><th>Created</th><th></th></tr></thead><tbody>{(reports?.items || []).map((r: any) => <tr key={r.id}><td>{r.title}</td><td>{titleCase(r.report_type)}</td><td>{r.format.toUpperCase()}</td><td><StatusBadge status={r.status} />{r.error && <div className="text-xs text-red-600">{r.error}</div>}</td><td>{r.file_size ? `${fmtNum(r.file_size / 1024)} KB` : "—"}</td><td>{fmtDate(r.created_at)}</td><td>{r.status === "ready" && <button className="btn-secondary" onClick={() => downloadWithAuth(`/reports/${r.id}/download`, `${r.report_type}.${r.format}`)}><Download className="h-4 w-4" /></button>}</td></tr>)}</tbody></table>}
          {!reports?.items?.length && !loading && <p className="p-4 text-sm text-slate-500">No reports yet.</p>}
        </div>
      </div>
    </>
  );
}
