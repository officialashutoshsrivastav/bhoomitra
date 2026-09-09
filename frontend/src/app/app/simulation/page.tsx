"use client";

import { Play, Plus } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, Field, Loading, StatusBadge, Tabs, ValueKind } from "@/components/ui";
import { api, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

const CLASSES = ["cropland", "forest", "grassland", "built_up", "water", "wasteland"];

function SimInner() {
  const sp = useSearchParams();
  const { can } = useAuth();
  const { data: model } = useApi<any>("/simulations/model");
  const { data: scenarios, reload } = useApi<any>("/simulations/scenarios", { page_size: 50 });
  const { data: layers } = useApi<any>("/gis/layers", { category: "land_use", page_size: 50 });
  const { data: units } = useApi<any>("/gis/admin-units", { level: "district", limit: 500 });
  const [selected, setSelected] = useState<string | null>(sp.get("scenario"));
  const [scenario, setScenario] = useState<any>(null);
  const [run, setRun] = useState<any>(null);
  const [compare, setCompare] = useState<any>(null);
  const [compareIds, setCompareIds] = useState<string[]>([]);
  const [tab, setTab] = useState("list");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [note, setNote] = useState("");
  const [f, setF] = useState<any>({ name: "", description: "", horizon_years: 10, admin_unit_id: "", baseline_layer_id: "", population_k: 900, rainfall_mm: 900, land: { cropland: 500, forest: 200, grassland: 100, built_up: 80, water: 40, wasteland: 120 }, interventions: [{ type: "reallocate", from_class: "wasteland", to_class: "forest", area_km2: 100, start_year_offset: 1, ramp_years: 5 }] });
  const [indicator, setIndicator] = useState("forest_area_km2");

  useEffect(() => { if (!selected) return; api(`/simulations/scenarios/${selected}`).then(async (s) => { setScenario(s); const last = s.runs?.[s.runs.length - 1]; if (last) setRun(await api(`/simulations/runs/${last.id}`)); else setRun(null); }).catch(() => {}); }, [selected]);
  const create = async () => {
    setBusy(true); setErr(null);
    try {
      const baseline: any = { population_k: Number(f.population_k), rainfall_mm: Number(f.rainfall_mm), base_year: new Date().getFullYear() };
      if (!f.baseline_layer_id) baseline.land_km2 = Object.fromEntries(Object.entries(f.land).map(([k, v]) => [k, Number(v)]));
      const s = await api("/simulations/scenarios", { body: { name: f.name, description: f.description || undefined, horizon_years: Number(f.horizon_years), admin_unit_id: f.admin_unit_id || undefined, baseline_layer_id: f.baseline_layer_id || undefined, baseline, interventions: f.interventions.map((i: any) => ({ ...i, area_km2: i.area_km2 !== undefined ? Number(i.area_km2) : undefined, pct: i.pct !== undefined ? Number(i.pct) : undefined, start_year_offset: Number(i.start_year_offset || 1), ramp_years: Number(i.ramp_years || 1) })) } });
      await reload(); setSelected(s.id); setTab("detail");
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  const doRun = async () => { if (!selected) return; setBusy(true); setErr(null); try { const r = await api(`/simulations/scenarios/${selected}/run`, { body: { iterations: 400 } }); setRun(r); setScenario(await api(`/simulations/scenarios/${selected}`)); reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const review = async (decision: string) => { if (!selected) return; setBusy(true); setErr(null); try { setScenario(await api(`/simulations/scenarios/${selected}/review`, { body: { decision, note: note || undefined } })); reload(); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const doCompare = async () => { if (compareIds.length < 2) return; setBusy(true); setErr(null); try { setCompare(await api("/simulations/compare", { params: { run_ids: compareIds.join(",") } })); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const series = run?.series?.[indicator];
  const chart = (series?.points || []).map((p: any) => ({ year: p.year, value: p.value, low: p.low, high: p.high }));
  const lastRunIds = (scenarios?.items || []).map((s: any) => s.runs?.[s.runs.length - 1]?.id).filter(Boolean);
  return (
    <>
      <PageHeader title="Policy simulation lab" subtitle="Transparent land-use scenarios: explicit assumptions, Monte Carlo uncertainty bands and labelled outputs. Projections are decision support, not forecasts." action={model && <span className="badge bg-slate-100 text-slate-700">{model.algorithm} · v{model.version}</span>} />
      <Tabs tabs={[{ id: "list", label: "Scenarios", count: scenarios?.total }, { id: "new", label: "New scenario" }, { id: "detail", label: "Scenario detail" }, { id: "compare", label: "Compare runs" }, { id: "model", label: "Model card" }]} value={tab} onChange={setTab} />
      <ErrorText error={err} />
      {tab === "list" && <div className="card mt-4 overflow-x-auto"><table className="table"><thead><tr><th>Scenario</th><th>Status</th><th>Unit</th><th>Horizon</th><th>Interventions</th><th>Runs</th><th>Created</th><th></th></tr></thead><tbody>{(scenarios?.items || []).map((s: any) => <tr key={s.id}><td className="font-medium text-navy-800">{s.name} <DemoBadge show={s.is_demo} /></td><td><StatusBadge status={s.status} /></td><td>{s.admin_unit?.name || "—"}</td><td>{s.horizon_years} y</td><td className="text-xs">{s.interventions?.map((i: any) => i.type).join(", ") || "baseline"}</td><td>{s.runs?.length}</td><td>{fmtDate(s.created_at)}</td><td><button className="text-brand-700 underline" onClick={() => { setSelected(s.id); setTab("detail"); }}>Open</button></td></tr>)}</tbody></table>{!scenarios?.items?.length && <p className="p-4 text-sm text-slate-500">No scenarios yet.</p>}</div>}
      {tab === "new" && (
        <div className="card mt-4 grid max-w-4xl gap-4 p-5 md:grid-cols-2">
          {!can("simulation.create") && <div className="md:col-span-2"><Alert kind="warn">Your role cannot create scenarios (requires simulation.create).</Alert></div>}
          <div className="md:col-span-2"><Field label="Scenario name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field></div>
          <div className="md:col-span-2"><Field label="Description"><textarea className="input" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field></div>
          <Field label="Administrative unit"><select className="input" value={f.admin_unit_id} onChange={(e) => setF({ ...f, admin_unit_id: e.target.value })}><option value="">—</option>{(units?.items || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></Field>
          <Field label="Baseline from land-cover layer (OBSERVED)" hint="If chosen, land classes are derived from the layer within the unit; otherwise the manual figures below are recorded as ASSUMPTIONS."><select className="input" value={f.baseline_layer_id} onChange={(e) => setF({ ...f, baseline_layer_id: e.target.value })}><option value="">— manual baseline —</option>{(layers?.items || []).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></Field>
          {!f.baseline_layer_id && <div className="md:col-span-2 grid grid-cols-3 gap-2 md:grid-cols-6">{CLASSES.map((c) => <Field key={c} label={`${titleCase(c)} km²`}><input className="input" type="number" value={f.land[c]} onChange={(e) => setF({ ...f, land: { ...f.land, [c]: e.target.value } })} /></Field>)}</div>}
          <Field label="Population (thousand)"><input className="input" type="number" value={f.population_k} onChange={(e) => setF({ ...f, population_k: e.target.value })} /></Field>
          <Field label="Annual rainfall (mm)"><input className="input" type="number" value={f.rainfall_mm} onChange={(e) => setF({ ...f, rainfall_mm: e.target.value })} /></Field>
          <Field label="Horizon (years)"><input className="input" type="number" min={1} max={50} value={f.horizon_years} onChange={(e) => setF({ ...f, horizon_years: e.target.value })} /></Field>
          <div className="md:col-span-2"><label className="label">Interventions</label>
            {f.interventions.map((iv: any, idx: number) => (
              <div key={idx} className="mb-2 grid grid-cols-2 gap-2 rounded border border-slate-200 p-2 md:grid-cols-6">
                <select className="input" value={iv.type} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, type: e.target.value }; setF({ ...f, interventions: arr }); }}>{(model?.intervention_types || ["reallocate", "yield_improvement", "irrigation_expansion", "rainfall_shift"]).map((t: string) => <option key={t} value={t}>{titleCase(t)}</option>)}</select>
                {iv.type === "reallocate" && <><select className="input" value={iv.from_class} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, from_class: e.target.value }; setF({ ...f, interventions: arr }); }}>{CLASSES.map((c) => <option key={c}>{c}</option>)}</select><select className="input" value={iv.to_class} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, to_class: e.target.value }; setF({ ...f, interventions: arr }); }}>{CLASSES.map((c) => <option key={c}>{c}</option>)}</select><input className="input" type="number" placeholder="km²" value={iv.area_km2 ?? ""} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, area_km2: e.target.value }; setF({ ...f, interventions: arr }); }} /></>}
                {iv.type === "irrigation_expansion" && <input className="input" type="number" placeholder="area km²" value={iv.area_km2 ?? ""} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, area_km2: e.target.value }; setF({ ...f, interventions: arr }); }} />}
                {(iv.type === "yield_improvement" || iv.type === "rainfall_shift") && <input className="input" type="number" placeholder="% change" value={iv.pct ?? ""} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, pct: e.target.value }; setF({ ...f, interventions: arr }); }} />}
                <input className="input" type="number" placeholder="ramp years" value={iv.ramp_years ?? 1} onChange={(e) => { const arr = [...f.interventions]; arr[idx] = { ...iv, ramp_years: e.target.value }; setF({ ...f, interventions: arr }); }} />
                <button type="button" className="btn-ghost" onClick={() => setF({ ...f, interventions: f.interventions.filter((_: any, i: number) => i !== idx) })}>Remove</button>
              </div>
            ))}
            <button type="button" className="btn-secondary" onClick={() => setF({ ...f, interventions: [...f.interventions, { type: "yield_improvement", pct: 10, start_year_offset: 1, ramp_years: 3 }] })}><Plus className="h-4 w-4" /> Add intervention</button>
          </div>
          <div className="md:col-span-2"><button className="btn-primary" disabled={busy || !f.name || !can("simulation.create")} onClick={create}>{busy ? "Creating…" : "Create scenario"}</button></div>
        </div>
      )}
      {tab === "detail" && (!scenario ? <p className="mt-4 text-sm text-slate-500">Select a scenario from the list.</p> : (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <div className="card p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="text-lg font-bold text-navy-800">{scenario.name} <DemoBadge show={scenario.is_demo} /></h2><p className="text-xs text-slate-500">{scenario.admin_unit?.name || "no unit"} · horizon {scenario.horizon_years} y · baseline {scenario.baseline?.value_kind || "ASSUMPTION"}{scenario.baseline?.source?.layer_name ? ` from ${scenario.baseline.source.layer_name}` : ""}</p></div><div className="flex flex-wrap items-center gap-2"><StatusBadge status={scenario.status} />{can("simulation.run") && <button className="btn-primary" disabled={busy} onClick={doRun}><Play className="h-4 w-4" /> Run (400 iterations)</button>}{scenario.status === "simulated" && <button className="btn-secondary" disabled={busy} onClick={() => review("submit")}>Submit for review</button>}{scenario.status === "under_review" && can("simulation.approve") && <><input className="input max-w-[180px]" placeholder="Review note" value={note} onChange={(e) => setNote(e.target.value)} /><button className="btn-primary" disabled={busy} onClick={() => review("approve")}>Approve</button><button className="btn-danger" disabled={busy} onClick={() => review("reject")}>Reject</button></>}</div></div>{scenario.review_note && <p className="mt-2 text-xs text-slate-600">Review note: {scenario.review_note}</p>}<div className="mt-3 flex flex-wrap gap-2 text-xs">{scenario.interventions?.map((i: any, k: number) => <span key={k} className="badge bg-orange-100 text-orange-800">{titleCase(i.type)}{i.from_class ? ` ${i.from_class}→${i.to_class} ${i.area_km2} km²` : i.pct ? ` ${i.pct}%` : i.area_km2 ? ` ${i.area_km2} km²` : ""}</span>)}{!scenario.interventions?.length && <span className="badge bg-slate-100 text-slate-700">Baseline (no intervention)</span>}</div></div>
            {run ? (
              <div className="card p-4">
                <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-bold text-navy-800">Latest run · {run.iterations} iterations · seed {run.seed}</h3><div className="flex gap-2"><ValueKind kind="MODELLED" /><ValueKind kind="UNCERTAINTY" />{run.recommendation_id && <Link href={`/app/evidence/${run.recommendation_id}`} className="badge bg-navy-800 text-white">Evidence trace</Link>}</div></div>
                <div className="mt-3 flex flex-wrap gap-1">{Object.entries(run.series || {}).map(([code, s]: any) => <button key={code} onClick={() => setIndicator(code)} className={`rounded-full px-2.5 py-0.5 text-xs ${indicator === code ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700"}`}>{s.label}</button>)}</div>
                {series && <div className="mt-3 h-64"><ResponsiveContainer><ComposedChart data={chart}><CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="year" /><YAxis /><Tooltip /><Area dataKey="high" stroke="none" fill="#dbeafe" /><Area dataKey="low" stroke="none" fill="#ffffff" /><Line dataKey="value" stroke="#0f5f3a" strokeWidth={2} dot={false} /></ComposedChart></ResponsiveContainer><p className="text-xs text-slate-500">{series.label} ({series.unit}) — median with p10–p90 band.</p></div>}
                <div className="mt-3 overflow-x-auto"><table className="table text-xs"><thead><tr><th>Indicator</th><th>Base</th><th>End (median)</th><th>p10–p90</th><th>Change</th></tr></thead><tbody>{Object.entries(run.summary?.summary || {}).map(([code, v]: any) => <tr key={code} className={code === indicator ? "bg-brand-50/50" : ""}><td>{v.label}</td><td>{fmtNum(v.base, 2)}</td><td>{fmtNum(v.end, 2)}</td><td>{fmtNum(v.end_low, 2)} – {fmtNum(v.end_high, 2)}</td><td className={v.change_pct > 0 ? "text-emerald-700" : v.change_pct < 0 ? "text-red-700" : ""}>{v.change_pct > 0 ? "+" : ""}{v.change_pct}%</td></tr>)}</tbody></table></div>
                {run.risks?.length > 0 && <div className="mt-3"><h4 className="font-semibold text-navy-800">Risk flags</h4><ul className="mt-1 space-y-1 text-sm">{run.risks.map((r: any, i: number) => <li key={i} className={`rounded px-2 py-1 ${r.severity === "high" ? "bg-red-50 text-red-800" : r.severity === "medium" ? "bg-amber-50 text-amber-800" : "bg-slate-50 text-slate-700"}`}><b>{titleCase(r.domain)}</b> · {r.statement}</li>)}</ul></div>}
                <p className="mt-3 text-[11px] text-slate-500">{run.disclaimer} Area conserved: {String(run.summary?.area_conserved)}.</p>
              </div>
            ) : <Alert kind="info">No run yet — press Run to simulate.</Alert>}
          </div>
          <div className="card p-4"><h3 className="font-bold text-navy-800">Assumptions ({scenario.assumptions?.length})</h3><ul className="mt-2 max-h-[600px] space-y-1 overflow-auto text-xs">{scenario.assumptions?.map((a: any) => <li key={a.id} className="rounded border border-slate-100 p-1.5"><div className="font-mono text-[10px] text-slate-500">{a.code}</div><div>{a.statement}</div>{a.low != null && <div className="text-slate-500">range {a.low} – {a.high} {a.unit || ""}</div>}</li>)}</ul></div>
        </div>
      ))}
      {tab === "compare" && (
        <div className="card mt-4 p-4">
          <p className="text-sm text-slate-600">Select two or more latest runs to compare end-of-horizon indicators.</p>
          <div className="mt-2 flex flex-wrap gap-2">{(scenarios?.items || []).filter((s: any) => s.runs?.length).map((s: any) => { const rid = s.runs[s.runs.length - 1].id; return <label key={s.id} className="flex items-center gap-2 rounded border border-slate-200 px-2 py-1 text-sm"><input type="checkbox" className="accent-brand-600" checked={compareIds.includes(rid)} onChange={() => setCompareIds((c) => (c.includes(rid) ? c.filter((x) => x !== rid) : [...c, rid]))} />{s.name}</label>; })}</div>
          <button className="btn-primary mt-3" disabled={busy || compareIds.length < 2 || lastRunIds.length < 2} onClick={doCompare}>Compare</button>
          {compare && <div className="mt-4 overflow-x-auto"><table className="table text-xs"><thead><tr><th>Indicator</th>{compare.runs.map((r: any) => <th key={r.id}>{r.scenario}{r.is_demo ? " (demo)" : ""}</th>)}<th>Spread</th></tr></thead><tbody>{compare.comparison.map((row: any) => <tr key={row.indicator}><td>{row.label} <span className="text-slate-400">({row.unit})</span></td>{compare.runs.map((r: any) => { const v = row.runs[r.id]; return <td key={r.id} className={r.id === row.best_run_id ? "font-bold text-emerald-700" : ""}>{v ? <>{fmtNum(v.end, 2)} <span className="text-slate-400">({v.change_pct > 0 ? "+" : ""}{v.change_pct}%)</span></> : "—"}</td>; })}<td>{fmtNum(row.spread, 2)}</td></tr>)}</tbody></table><p className="mt-2 text-xs text-slate-500">{compare.note} All values MODELLED.</p></div>}
        </div>
      )}
      {tab === "model" && model && <div className="card mt-4 p-5 text-sm"><h3 className="font-bold text-navy-800">{model.algorithm} — v{model.version}</h3><p className="mt-2 text-slate-700">{model.limitations}</p><h4 className="mt-3 font-semibold">Indicators</h4><ul className="mt-1 grid grid-cols-2 gap-1 text-xs md:grid-cols-3">{model.indicators.map((i: any) => <li key={i.code}>{i.label} <span className="text-slate-500">({i.unit}, {i.domain})</span></li>)}</ul><h4 className="mt-3 font-semibold">Coefficients (with uncertainty ranges)</h4><div className="mt-1 max-h-72 overflow-auto"><table className="table text-xs"><thead><tr><th>Coefficient</th><th>Value</th><th>Range</th><th>Basis</th></tr></thead><tbody>{Object.entries(model.coefficients || {}).map(([k, c]: any) => <tr key={k}><td className="font-mono">{k}</td><td>{JSON.stringify(c.value)}</td><td>{c.low != null ? `${c.low} – ${c.high}` : "—"}</td><td>{c.basis}</td></tr>)}</tbody></table></div></div>}
    </>
  );
}

export default function SimulationPage() {
  return <Suspense fallback={<Loading />}><SimInner /></Suspense>;
}
