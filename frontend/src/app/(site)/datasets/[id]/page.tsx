"use client";

import { Download } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Alert, DemoBadge, Hero, KV, Loading, Section, StatusBadge, ValueKind } from "@/components/ui";
import { downloadUrl, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function DatasetDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: ds, loading, error } = useApi<any>(`/datasets/${id}`);
  const [variable, setVariable] = useState<string>("");
  const { data: obs } = useApi<any>(ds ? `/datasets/${id}/observations` : null, { variable_code: variable || undefined, page_size: 500 }, [ds?.id]);
  if (loading) return <Loading />;
  if (error || !ds) return <Section><Alert kind="error">Dataset not found or not public.</Alert></Section>;
  const series: Record<string, any[]> = {};
  (obs?.items || []).forEach((o: any) => { const k = o.geography_label || "all"; (series[k] ||= []).push({ year: o.period_start?.slice(0, 4), value: o.value }); });
  const geos = Object.keys(series).slice(0, 6);
  const chartData = Array.from(new Set((obs?.items || []).map((o: any) => o.period_start?.slice(0, 4)))).sort().map((y) => { const row: any = { year: y }; geos.forEach((g) => { row[g] = series[g].find((p) => p.year === y)?.value; }); return row; });
  return (
    <>
      <Hero title={ds.name} crumbs={[{ label: "Home", href: "/" }, { label: "Datasets", href: "/datasets" }, { label: ds.name }]} />
      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <div className="card p-5">
              <div className="flex flex-wrap items-center gap-2"><span className="badge bg-brand-100 text-brand-800">{titleCase(ds.category)}</span><StatusBadge status={ds.status} /><DemoBadge show={ds.is_demo} /></div>
              <p className="mt-3 text-slate-700">{ds.description}</p>
              {ds.provenance && <p className="mt-2 text-sm text-slate-600"><b>Provenance:</b> {ds.provenance}</p>}
              {ds.quality_notes && <p className="mt-1 text-sm text-slate-600"><b>Quality notes:</b> {ds.quality_notes}</p>}
            </div>
            {ds.variables?.length > 0 && (
              <div className="card p-5">
                <div className="flex items-center justify-between"><h2 className="font-bold text-navy-800">Observations</h2><select className="input w-auto" value={variable} onChange={(e) => setVariable(e.target.value)}><option value="">All variables</option>{ds.variables.map((v: any) => <option key={v.code} value={v.code}>{v.name} ({v.unit || "—"})</option>)}</select></div>
                {chartData.length > 1 ? (
                  <div className="mt-3 h-72">
                    <ResponsiveContainer><LineChart data={chartData}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip />{geos.map((g, i) => <Line key={g} type="monotone" dataKey={g} stroke={["#0f5f3a", "#3b82c4", "#f28c28", "#7c3aed", "#c9a36b", "#b0413e"][i]} dot={false} />)}</LineChart></ResponsiveContainer>
                  </div>
                ) : <p className="mt-3 text-sm text-slate-500">No observation series available.</p>}
                <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">Value kinds: {Array.from(new Set((obs?.items || []).map((o: any) => o.value_kind))).map((k: any) => <ValueKind key={k} kind={k} />)} · {fmtNum(ds.observation_count)} observations</div>
              </div>
            )}
          </div>
          <aside className="space-y-4">
            <div className="card p-5">
              <KV items={[["Publisher", ds.publisher], ["Source", ds.source?.name], ["Coverage", ds.geography], ["Period", `${fmtDate(ds.temporal_start)} – ${fmtDate(ds.temporal_end)}`], ["Spatial resolution", ds.spatial_resolution], ["Temporal resolution", ds.temporal_resolution], ["Format", ds.format], ["Licence", ds.license], ["Update frequency", ds.update_frequency], ["Access", ds.access_level], ["Downloads", fmtNum(ds.download_count)]]} />
              {ds.current_version_id && <a href={downloadUrl(`/datasets/${ds.id}/download`)} className="btn-primary mt-4 w-full"><Download className="h-4 w-4" /> Download current version</a>}
            </div>
            <div className="card p-5">
              <h3 className="font-bold text-navy-800">Versions</h3>
              <ul className="mt-2 space-y-2 text-sm">{ds.versions.map((v: any) => <li key={v.id} className="rounded border border-slate-100 p-2"><div className="flex justify-between"><b>v{v.version_number}</b><StatusBadge status={v.processing_status} /></div><div className="text-xs text-slate-500">{v.file_name} · {fmtNum(v.row_count)} rows · {fmtDate(v.created_at)}</div>{v.checksum_sha256 && <div className="truncate font-mono text-[10px] text-slate-400" title={v.checksum_sha256}>sha256 {v.checksum_sha256}</div>}</li>)}</ul>
            </div>
          </aside>
        </div>
      </Section>
    </>
  );
}
