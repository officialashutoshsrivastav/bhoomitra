"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/AppShell";
import { DemoBadge, ErrorText, Loading, Tabs, ValueKind } from "@/components/ui";
import { api, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TYPES = ["descriptive", "trend", "compare", "timeseries", "forecast", "anomaly", "correlation", "risk_score", "spatial_aggregate"];

function AnalyticsInner() {
  const sp = useSearchParams();
  const { data: datasets } = useApi<any>("/datasets", { page_size: 100 });
  const { data: models } = useApi<any>("/analytics/models");
  const { data: runs, reload } = useApi<any>("/analytics/runs", { page_size: 20 });
  const [dsId, setDsId] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const [f, setF] = useState<any>({ analysis_type: "trend", variable_code: sp.get("variable_code") || "", admin_unit_id: "", horizon: 5, level: "state", year: "" });
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [tab, setTab] = useState("run");
  useEffect(() => { const pre = sp.get("dataset_version_id"); if (pre && datasets?.items) { const d = datasets.items.find((x: any) => x.current_version_id === pre); if (d) setDsId(d.id); } }, [datasets]);
  useEffect(() => { if (!dsId) return setDetail(null); api(`/datasets/${dsId}`).then((d) => { setDetail(d); if (!f.variable_code && d.variables?.[0]) setF((s: any) => ({ ...s, variable_code: d.variables[0].code })); }).catch(() => {}); }, [dsId]);
  const run = async () => {
    setBusy(true); setErr(null); setResult(null);
    try {
      const body: any = { analysis_type: f.analysis_type, dataset_version_id: detail?.current_version_id, variable_code: f.variable_code || undefined, admin_unit_id: f.admin_unit_id || undefined, horizon: Number(f.horizon), level: f.level, year: f.year ? Number(f.year) : undefined };
      const r = await api("/analytics/run", { body });
      setResult(r); reload();
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  // /analytics/runs returns model_version_id; resolve it to a readable label
  const versionLabel = (id?: string) => {
    if (!id) return "—";
    for (const m of models?.items || []) {
      const v = (m.versions || []).find((x: any) => x.id === id);
      if (v) return `${m.name} v${v.version}`;
    }
    return id.slice(0, 8);
  };

  const res = result?.result;
  const seriesData = res?.series || res?.points || res?.observations || null;
  const forecastData = res?.forecast ? [...(res.history || res.series || []).map((p: any) => ({ year: p.year, value: p.value })), ...res.forecast.map((p: any) => ({ year: p.year, forecast: p.value, low: p.low, high: p.high }))] : null;
  return (
    <>
      <PageHeader title="Analytics engine" subtitle="Statistical procedures over dataset observations. Every run is registered with its model version and produces an evidence-linked recommendation." />
      <Tabs tabs={[{ id: "run", label: "Run analysis" }, { id: "history", label: "Run history", count: runs?.total }, { id: "models", label: "Model registry", count: models?.items?.length }]} value={tab} onChange={setTab} />
      {tab === "run" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[320px_1fr]">
          <div className="card space-y-3 p-4">
            <div><label className="label">Analysis</label><select className="input" value={f.analysis_type} onChange={(e) => setF({ ...f, analysis_type: e.target.value })}>{TYPES.map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</select><p className="mt-1 text-xs text-slate-500">{models?.items?.find((m: any) => m.slug === `analytics-${f.analysis_type.replace("_", "-")}`)?.versions?.[0]?.limitations?.slice(0, 160)}</p></div>
            <div><label className="label">Dataset</label><select className="input" value={dsId} onChange={(e) => setDsId(e.target.value)}><option value="">— choose —</option>{(datasets?.items || []).filter((d: any) => d.current_version_id).map((d: any) => <option key={d.id} value={d.id}>{d.name}</option>)}</select></div>
            <div><label className="label">Variable</label><select className="input" value={f.variable_code} onChange={(e) => setF({ ...f, variable_code: e.target.value })}><option value="">—</option>{(detail?.variables || []).map((v: any) => <option key={v.code} value={v.code}>{v.name} ({v.unit || "—"})</option>)}</select></div>
            {["trend", "forecast", "timeseries", "descriptive", "anomaly"].includes(f.analysis_type) && <UnitPicker value={f.admin_unit_id} onChange={(v) => setF({ ...f, admin_unit_id: v })} />}
            {f.analysis_type === "forecast" && <div><label className="label">Horizon (years)</label><input className="input" type="number" min={1} max={20} value={f.horizon} onChange={(e) => setF({ ...f, horizon: e.target.value })} /></div>}
            {f.analysis_type === "spatial_aggregate" && <><div><label className="label">Level</label><select className="input" value={f.level} onChange={(e) => setF({ ...f, level: e.target.value })}><option value="state">State</option><option value="district">District</option></select></div><div><label className="label">Year (optional)</label><input className="input" type="number" value={f.year} onChange={(e) => setF({ ...f, year: e.target.value })} /></div></>}
            {(f.analysis_type === "correlation" || f.analysis_type === "risk_score") && <p className="text-xs text-slate-500">Correlation and risk scoring accept inline series via the API (see docs/api.md); this form runs them on the selected variable where applicable.</p>}
            <button className="btn-primary w-full" disabled={busy || !detail?.current_version_id} onClick={run}>{busy ? "Running…" : "Run"}</button>
            <ErrorText error={err} />
          </div>
          <div className="card p-4">
            {!result ? <p className="text-sm text-slate-500">Results appear here with charts, summary statistics and a link to the evidence trace.</p> : (
              <div className="space-y-3 text-sm">
                <div className="flex flex-wrap items-center gap-2"><span className="badge bg-brand-100 text-brand-800">{titleCase(result.analysis_type)}</span><ValueKind kind={res?.output_value_kind || res?.value_kind} />{res?.input_value_kinds?.map((k: string) => <ValueKind key={k} kind={k} />)}{result.is_demo && <DemoBadge />}{result.recommendation_id && <Link href={`/app/evidence/${result.recommendation_id}`} className="badge bg-navy-800 text-white">Evidence trace</Link>}<span className="text-xs text-slate-500" title={result.model_version?.limitations || ""}>{result.model_version?.algorithm || "—"} · v{result.model_version?.version || "?"}</span></div>
                {result.summary && <p className="rounded bg-slate-50 p-3 text-slate-700">{result.summary}</p>}
                <div className="grid grid-cols-2 gap-2 md:grid-cols-4">{Object.entries(res || {}).filter(([, v]) => typeof v === "number" || typeof v === "string").slice(0, 12).map(([k, v]) => <div key={k} className="rounded border border-slate-100 p-2"><div className="text-[10px] uppercase text-slate-500">{titleCase(k)}</div><div className="font-semibold text-navy-800">{typeof v === "number" ? fmtNum(v as number, 3) : String(v)}</div></div>)}</div>
                {forecastData && <div className="h-64"><ResponsiveContainer><ComposedChart data={forecastData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip /><Area dataKey="high" stroke="none" fill="#dbeafe" /><Area dataKey="low" stroke="none" fill="#ffffff" /><Line dataKey="value" stroke="#0f5f3a" strokeWidth={2} dot /><Line dataKey="forecast" stroke="#3b82c4" strokeWidth={2} strokeDasharray="5 3" dot /></ComposedChart></ResponsiveContainer><p className="text-xs text-slate-500">Dashed = MODELLED forecast; band = interval (UNCERTAINTY).</p></div>}
                {!forecastData && Array.isArray(seriesData) && seriesData.length > 1 && seriesData[0]?.year !== undefined && <div className="h-64"><ResponsiveContainer><ComposedChart data={seriesData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip /><Line dataKey="value" stroke="#0f5f3a" strokeWidth={2} />{seriesData[0]?.fitted !== undefined && <Line dataKey="fitted" stroke="#f28c28" strokeDasharray="4 2" dot={false} />}</ComposedChart></ResponsiveContainer></div>}
                {Array.isArray(res?.items) && res.items[0]?.label !== undefined && <div className="h-64"><ResponsiveContainer><BarChart data={res.items.slice(0, 20)}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey={res.items[0].name ? "name" : "label"} tick={{ fontSize: 10 }} /><YAxis /><Tooltip /><Bar dataKey={res.items[0].risk_score !== undefined ? "risk_score" : res.items[0].value !== undefined ? "value" : "sum"} fill="#0f5f3a" /></BarChart></ResponsiveContainer></div>}
                {Array.isArray(res?.anomalies) && <div><b>{res.anomalies.length} anomalies</b><ul className="text-xs">{res.anomalies.map((a: any, i: number) => <li key={i}>{a.label} {a.year}: value {a.value} (z {a.z_score?.toFixed?.(2)}, rules {Array.isArray(a.rules) ? a.rules.join("/") : a.rules ?? "—"})</li>)}</ul></div>}
                <details className="text-xs"><summary className="cursor-pointer text-slate-500">Raw result</summary><pre className="max-h-72 overflow-auto rounded bg-slate-50 p-2">{JSON.stringify(res, null, 1).slice(0, 6000)}</pre></details>
              </div>
            )}
          </div>
        </div>
      )}
      {tab === "history" && <div className="card mt-4 overflow-x-auto"><table className="table"><thead><tr><th>Title</th><th>Type</th><th>Status</th><th>Model</th><th>When</th><th></th></tr></thead><tbody>{(runs?.items || []).map((r: any) => <tr key={r.id}><td>{r.title}</td><td>{titleCase(r.analysis_type)}</td><td>{r.status}</td><td className="text-xs">{versionLabel(r.model_version_id)}</td><td>{fmtDate(r.created_at)}</td><td>{r.recommendation_id && <Link className="text-brand-700 underline" href={`/app/evidence/${r.recommendation_id}`}>evidence</Link>}</td></tr>)}</tbody></table></div>}
      {tab === "models" && <div className="mt-4 grid gap-3 md:grid-cols-2">{(models?.items || []).map((m: any) => <div key={m.id} className="card p-4 text-sm"><div className="font-bold text-navy-800">{m.name}</div><div className="text-xs text-slate-500">{m.type || m.model_type} · {m.versions?.[0]?.version} · {m.versions?.[0]?.algorithm}</div><p className="mt-1 text-slate-700">{m.description}</p><p className="mt-1 text-xs text-slate-500"><b>Limitations:</b> {m.versions?.[0]?.limitations}</p></div>)}</div>}
    </>
  );
}

function UnitPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const { data } = useApi<any>("/gis/admin-units", { level: "district", limit: 500 });
  return <div><label className="label">Administrative unit (optional)</label><select className="input" value={value} onChange={(e) => onChange(e.target.value)}><option value="">All units</option>{(data?.items || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div>;
}

export default function AnalyticsPage() {
  return <Suspense fallback={<Loading />}><AnalyticsInner /></Suspense>;
}
