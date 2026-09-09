"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, Loading, ValueKind } from "@/components/ui";
import { fmtDate, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const NODE_COLORS: Record<string, string> = { recommendation: "#0f5f3a", evidence: "#3b82c4", document_chunk: "#7c3aed", document_version: "#a78bfa", document: "#6d28d9", dataset_version: "#0891b2", dataset: "#0e7490", observation: "#06b6d4", scenario: "#f28c28", simulation_run: "#ea580c", model_version: "#b0413e", model: "#991b1b", assumption: "#d97706", gis_layer: "#65a30d", gis_feature: "#84cc16", admin_unit: "#4d7c0f", rs_product: "#0d9488", rs_scene: "#14b8a6", analytics_run: "#2563eb", ai_message: "#64748b", spatial_run: "#16a34a", policy: "#be185d" };
const NODE_HREF: Record<string, (id: string) => string> = { document: (id) => `/app/repository/${id}`, dataset: (id) => `/app/datasets/${id}`, recommendation: (id) => `/app/evidence/${id}`, gis_layer: (id) => `/app/gis?layer=${id}`, admin_unit: (id) => `/app/gis?unit=${id}`, scenario: (id) => `/app/simulation?scenario=${id}` };

function TraceGraph({ nodes, edges }: { nodes: any[]; edges: any[] }) {
  const layout = useMemo(() => {
    const byDepth: Record<number, any[]> = {};
    nodes.forEach((n) => (byDepth[n.depth] ||= []).push(n));
    const depths = Object.keys(byDepth).map(Number).sort((a, b) => a - b);
    const colW = 230, rowH = 46;
    const pos: Record<string, { x: number; y: number }> = {};
    let maxRows = 1;
    depths.forEach((d, ci) => { byDepth[d].forEach((n, ri) => { pos[n.id] = { x: 20 + ci * colW, y: 20 + ri * rowH }; }); maxRows = Math.max(maxRows, byDepth[d].length); });
    return { pos, width: 40 + depths.length * colW, height: 40 + maxRows * rowH };
  }, [nodes, edges]);
  return (
    <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
      <svg width={layout.width} height={layout.height} className="min-w-full">
        <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#94a3b8" /></marker></defs>
        {edges.map((e, i) => { const a = layout.pos[e.from], b = layout.pos[e.to]; if (!a || !b) return null; return <g key={i}><path d={`M${a.x + 200},${a.y + 16} C${a.x + 230},${a.y + 16} ${b.x - 30},${b.y + 16} ${b.x},${b.y + 16}`} fill="none" stroke="#cbd5e1" strokeWidth="1.5" markerEnd="url(#arrow)" /><text x={(a.x + 200 + b.x) / 2} y={(a.y + b.y) / 2 + 12} fontSize="9" fill="#94a3b8" textAnchor="middle">{e.relation}</text></g>; })}
        {nodes.map((n) => { const p = layout.pos[n.id]; if (!p) return null; const href = NODE_HREF[n.type]?.(n.id); const g = <g key={n.id}><rect x={p.x} y={p.y} width="200" height="32" rx="6" fill="#fff" stroke={NODE_COLORS[n.type] || "#94a3b8"} strokeWidth="1.5" /><rect x={p.x} y={p.y} width="6" height="32" rx="3" fill={NODE_COLORS[n.type] || "#94a3b8"} /><text x={p.x + 12} y={p.y + 13} fontSize="9" fill="#64748b">{titleCase(n.type)}{n.value_kind ? ` · ${n.value_kind}` : ""}</text><text x={p.x + 12} y={p.y + 25} fontSize="10" fontWeight="600" fill="#17244a">{(n.label || "").slice(0, 34)}{n.label?.length > 34 ? "…" : ""}</text></g>; return href ? <a key={n.id} href={href}>{g}</a> : g; })}
      </svg>
    </div>
  );
}

export default function EvidencePage() {
  const { id } = useParams<{ id: string }>();
  const { data: ex, loading, error } = useApi<any>(`/evidence/${id}`);
  const { data: tr } = useApi<any>(`/evidence/${id}/trace`, { depth: 6 });
  if (loading) return <Loading />;
  if (error || !ex) return <Alert kind="error">Recommendation not found.</Alert>;
  const rec = ex.recommendation;
  return (
    <>
      <PageHeader title={rec.title} subtitle={`${titleCase(rec.kind)} · ${fmtDate(rec.created_at)}`} action={<div className="flex items-center gap-2"><span className="badge bg-blue-100 text-blue-800">Confidence {Math.round((rec.confidence || 0) * 100)}%</span><DemoBadge show={rec.is_demo} />{ex.value_kinds_present?.map((k: string) => <ValueKind key={k} kind={k} />)}</div>} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <div className="card p-5"><h2 className="font-bold text-navy-800">Statement</h2><p className="mt-2 whitespace-pre-wrap text-sm text-slate-700">{rec.statement}</p>{rec.confidence_basis && <p className="mt-2 text-xs text-slate-500"><b>Confidence basis:</b> {rec.confidence_basis}</p>}{rec.limitations && <p className="mt-1 text-xs text-slate-500"><b>Limitations:</b> {rec.limitations}</p>}</div>
          <div className="card p-5"><h2 className="font-bold text-navy-800">Why did the system produce this?</h2><ol className="mt-2 list-decimal space-y-1 pl-5 text-sm text-slate-700">{ex.explanation?.map((s: string, i: number) => <li key={i}>{s}</li>)}</ol><p className="mt-3 text-xs text-slate-500">{ex.disclaimer}</p></div>
          <div className="card p-5"><h2 className="font-bold text-navy-800">Evidence items</h2><ol className="mt-2 divide-y divide-slate-100 text-sm">{ex.evidence?.map((e: any) => <li key={e.rank} className="py-2"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold">#{e.rank}</span><span className="badge bg-slate-100 text-slate-700">{titleCase(e.type)}</span><ValueKind kind={e.value_kind} />{e.score != null && <span className="text-xs text-slate-500">score {Number(e.score).toFixed(3)}</span>}</div><div className="mt-1 font-medium text-navy-800">{e.label}</div>{e.locator && <div className="text-xs text-slate-500">{e.locator}</div>}{e.excerpt && <p className="mt-1 text-xs text-slate-600">“{e.excerpt.slice(0, 400)}{e.excerpt.length > 400 ? "…" : ""}”</p>}</li>)}</ol></div>
          {rec.assumptions?.length > 0 && <div className="card p-5"><h2 className="font-bold text-navy-800">Assumptions ({rec.assumptions.length})</h2><table className="table mt-2"><thead><tr><th>Code</th><th>Statement</th><th>Range</th></tr></thead><tbody>{rec.assumptions.slice(0, 40).map((a: any, i: number) => <tr key={i}><td className="font-mono text-[11px]">{a.code}</td><td>{a.statement}</td><td className="whitespace-nowrap">{a.low != null ? `${a.low} – ${a.high}` : "—"}</td></tr>)}</tbody></table></div>}
        </div>
        <div className="space-y-4">
          <div className="card p-5"><h2 className="font-bold text-navy-800">Provenance graph</h2><p className="text-xs text-slate-500">{tr?.nodes?.length || 0} nodes · {tr?.edges?.length || 0} edges · depth {tr?.depth}</p><div className="mt-2 flex flex-wrap gap-1 text-[10px]">{Array.from(new Set((tr?.nodes || []).map((n: any) => n.type))).map((t: any) => <span key={t} className="flex items-center gap-1 rounded bg-slate-50 px-1.5 py-0.5"><span className="h-2 w-2 rounded-full" style={{ background: NODE_COLORS[t] || "#94a3b8" }} />{titleCase(t)}</span>)}</div></div>
          <Link href="/app/ai" className="btn-secondary w-full">← Back to assistant</Link>
        </div>
      </div>
      <div className="mt-6">{tr ? <TraceGraph nodes={tr.nodes} edges={tr.edges} /> : <Loading label="Loading trace…" />}</div>
    </>
  );
}
