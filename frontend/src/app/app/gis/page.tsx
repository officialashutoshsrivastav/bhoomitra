"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, Loading, Tabs, ValueKind } from "@/components/ui";
import { api, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

const LandMap = dynamic(() => import("@/components/LandMap"), { ssr: false, loading: () => <Loading label="Loading map…" /> });
const OPS = [{ id: "area", label: "Area & perimeter" }, { id: "intersection", label: "Intersection" }, { id: "proximity", label: "Proximity" }, { id: "aggregate", label: "Aggregate by unit" }, { id: "hotspot", label: "Hotspot" }, { id: "boundary-select", label: "Boundary select" }, { id: "affected-area", label: "Affected area" }];

function GisInner() {
  const sp = useSearchParams();
  const { can } = useAuth();
  const { data: layersData } = useApi<any>("/gis/layers", { page_size: 100 });
  const layers = layersData?.items || [];
  const { data: units } = useApi<any>("/gis/admin-units", { level: "district", limit: 500 });
  const [active, setActive] = useState<string[]>([]);
  const [unit, setUnit] = useState<string>(sp.get("unit") || "");
  const [layer, setLayer] = useState<string>(sp.get("layer") || "");
  const [op, setOp] = useState("area");
  const [params, setParams] = useState<any>({ lon: 76.5, lat: 23.0, radius_m: 20000, level: "district", metric: "area", cell_deg: 0.25, buffer_m: 5000 });
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [rsTab, setRsTab] = useState("ops");
  const [scenes, setScenes] = useState<any[]>([]);
  const [products, setProducts] = useState<any[]>([]);
  const [change, setChange] = useState<any>(null);
  const { data: runs, reload: reloadRuns } = useApi<any>("/gis/ops/runs", { limit: 15 });
  const { data: unitDetail } = useApi<any>(unit ? `/gis/admin-units/${unit}` : null, { simplify: 0.002 }, [unit]);
  useEffect(() => { if (layers.length && !layer) setLayer(layers[0].id); if (layers.length && !active.length) setActive([layer || layers[0].id]); }, [layers]);
  useEffect(() => { if (layer && !active.includes(layer)) setActive((a) => [...a, layer]); }, [layer]);
  const geometryOrUnit = () => (unit ? { admin_unit_id: unit } : { geometry: { type: "Point", coordinates: [params.lon, params.lat] } });
  const run = async () => {
    setBusy(true); setErr(null); setResult(null);
    try {
      let body: any;
      if (op === "area") body = unit ? { admin_unit_id: unit } : { geometry: { type: "Polygon", coordinates: [[[params.lon - 0.1, params.lat - 0.1], [params.lon + 0.1, params.lat - 0.1], [params.lon + 0.1, params.lat + 0.1], [params.lon - 0.1, params.lat + 0.1], [params.lon - 0.1, params.lat - 0.1]]] } };
      else if (op === "intersection") body = { layer_a: layer, layer_b: params.layer_b || undefined, ...(unit ? { admin_unit_id: unit } : {}) };
      else if (op === "proximity") body = { layer_id: layer, lon: Number(params.lon), lat: Number(params.lat), radius_m: Number(params.radius_m), limit: 50 };
      else if (op === "aggregate") body = { layer_id: layer, level: params.level, metric: params.metric };
      else if (op === "hotspot") body = { layer_id: layer, cell_deg: Number(params.cell_deg), admin_unit_id: unit || undefined };
      else if (op === "boundary-select") body = { geometry: { type: "Polygon", coordinates: [[[params.lon - 0.5, params.lat - 0.5], [params.lon + 0.5, params.lat - 0.5], [params.lon + 0.5, params.lat + 0.5], [params.lon - 0.5, params.lat + 0.5], [params.lon - 0.5, params.lat - 0.5]]] }, level: params.level };
      else if (op === "affected-area") body = { geometry: { type: "Point", coordinates: [Number(params.lon), Number(params.lat)] }, buffer_m: Number(params.buffer_m), layer_ids: active.length ? active : [layer] };
      setResult(await api(`/gis/ops/${op}`, { body }));
      reloadRuns();
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  const searchScenes = async () => { setBusy(true); setErr(null); try { const r = await api("/remote-sensing/scenes/search", { body: { bbox: [params.lon - 0.5, params.lat - 0.5, params.lon + 0.5, params.lat + 0.5], start: "2023-01-01", end: "2024-12-31", limit: 4 } }); setScenes(r.items); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const product = async (sceneId: string, type: string) => { setBusy(true); setErr(null); try { const p = await api(`/remote-sensing/scenes/${sceneId}/products`, { method: "POST", params: { product_type: type } }); setProducts((ps) => [p, ...ps]); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const detect = async () => { if (scenes.length < 2) return; setBusy(true); setErr(null); try { setChange(await api("/remote-sensing/change", { method: "POST", params: { before_id: scenes[0].id, after_id: scenes[scenes.length - 1].id } })); } catch (ex) { setErr(ex); } finally { setBusy(false); } };
  const highlight = useMemo(() => result?.geometry || result?.zone_geometry || unitDetail?.geometry, [result, unitDetail]);
  const selectedLayer = layers.find((l: any) => l.id === layer);
  return (
    <>
      <PageHeader title="GIS workbench" subtitle="PostGIS spatial operations, thematic layers and remote-sensing products. Every run is recorded with its inputs." />
      <div className="grid gap-4 xl:grid-cols-[300px_1fr_340px]">
        <aside className="card space-y-3 p-4">
          <div><label className="label">Layer</label><select className="input" value={layer} onChange={(e) => setLayer(e.target.value)}>{layers.map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}</select>{selectedLayer && <p className="mt-1 text-xs text-slate-500">{titleCase(selectedLayer.category)} · {selectedLayer.geometry_type} · {fmtNum(selectedLayer.feature_count)} features <DemoBadge show={selectedLayer.is_demo} /></p>}</div>
          <div><label className="label">Visible layers</label><div className="max-h-40 space-y-1 overflow-auto text-sm">{layers.map((l: any) => <label key={l.id} className="flex items-center gap-2"><input type="checkbox" className="accent-brand-600" checked={active.includes(l.id)} onChange={() => setActive((a) => (a.includes(l.id) ? a.filter((x) => x !== l.id) : [...a, l.id]))} />{l.name.replace(" (Demo)", "")}</label>)}</div></div>
          <div><label className="label">Administrative unit (district)</label><select className="input" value={unit} onChange={(e) => setUnit(e.target.value)}><option value="">— none / use point —</option>{(units?.items || []).map((u: any) => <option key={u.id} value={u.id}>{u.name}</option>)}</select></div>
          <div className="grid grid-cols-2 gap-2"><div><label className="label">Longitude</label><input className="input" type="number" step="0.01" value={params.lon} onChange={(e) => setParams({ ...params, lon: Number(e.target.value) })} /></div><div><label className="label">Latitude</label><input className="input" type="number" step="0.01" value={params.lat} onChange={(e) => setParams({ ...params, lat: Number(e.target.value) })} /></div></div>
        </aside>
        <div className="space-y-3">
          <div className="h-[520px] overflow-hidden rounded-xl border border-slate-200"><LandMap layers={layers} active={active} basemap="osm" unitLevel="district" parentId={null} selectedUnitId={unit || null} highlightGeometry={highlight} onSelectUnit={(u) => setUnit(u.id)} /></div>
          <div className="card p-4">
            <Tabs tabs={[{ id: "ops", label: "Spatial operations" }, { id: "rs", label: "Remote sensing" }, { id: "runs", label: "Run history", count: runs?.items?.length }]} value={rsTab} onChange={setRsTab} />
            {rsTab === "ops" && (
              <div className="mt-3">
                {!can("gis.analyze") && <Alert kind="warn" className="mb-3">Your role can view layers but not run analyses (requires gis.analyze).</Alert>}
                <div className="flex flex-wrap gap-1">{OPS.map((o) => <button key={o.id} onClick={() => setOp(o.id)} className={`rounded-full px-3 py-1 text-xs font-semibold ${op === o.id ? "bg-brand-600 text-white" : "bg-slate-100 text-slate-700"}`}>{o.label}</button>)}</div>
                <div className="mt-3 grid gap-2 sm:grid-cols-3">
                  {op === "intersection" && <div><label className="label">Intersect with layer (optional)</label><select className="input" value={params.layer_b || ""} onChange={(e) => setParams({ ...params, layer_b: e.target.value })}><option value="">— admin unit / point —</option>{layers.filter((l: any) => l.id !== layer).map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}</select></div>}
                  {op === "proximity" && <div><label className="label">Radius (m)</label><input className="input" type="number" value={params.radius_m} onChange={(e) => setParams({ ...params, radius_m: e.target.value })} /></div>}
                  {(op === "aggregate" || op === "boundary-select") && <div><label className="label">Level</label><select className="input" value={params.level} onChange={(e) => setParams({ ...params, level: e.target.value })}><option value="state">State</option><option value="district">District</option></select></div>}
                  {op === "aggregate" && <div><label className="label">Metric</label><select className="input" value={params.metric} onChange={(e) => setParams({ ...params, metric: e.target.value })}><option value="area">Area</option><option value="count">Count</option><option value="sum">Sum of value</option><option value="mean">Mean value</option></select></div>}
                  {op === "hotspot" && <div><label className="label">Cell size (deg)</label><input className="input" type="number" step="0.05" value={params.cell_deg} onChange={(e) => setParams({ ...params, cell_deg: e.target.value })} /></div>}
                  {op === "affected-area" && <div><label className="label">Buffer (m)</label><input className="input" type="number" value={params.buffer_m} onChange={(e) => setParams({ ...params, buffer_m: e.target.value })} /></div>}
                </div>
                <button className="btn-primary mt-3" disabled={busy || !can("gis.analyze")} onClick={run}>{busy ? "Running…" : `Run ${OPS.find((o) => o.id === op)?.label}`}</button>
                <ErrorText error={err} />
              </div>
            )}
            {rsTab === "rs" && (
              <div className="mt-3 space-y-3 text-sm">
                <p className="text-slate-600">Search scenes around the current point (STAC connector; demo adapter generates labelled synthetic reflectance when no STAC endpoint is configured), derive NDVI / NDWI / NDBI / land-cover products and detect change.</p>
                <div className="flex flex-wrap gap-2"><button className="btn-secondary" disabled={busy} onClick={searchScenes}>Search scenes</button><button className="btn-primary" disabled={busy || scenes.length < 2} onClick={detect}>Detect change (first → last)</button></div>
                <ErrorText error={err} />
                {scenes.length > 0 && <table className="table"><thead><tr><th>Scene</th><th>Date</th><th>Cloud %</th><th>Products</th></tr></thead><tbody>{scenes.map((s: any) => <tr key={s.id}><td>{s.platform || s.scene_id} <DemoBadge show={s.is_demo} /></td><td>{s.acquired_at?.slice(0, 10)}</td><td>{s.cloud_cover?.toFixed?.(1)}</td><td className="space-x-1">{["ndvi", "ndwi", "ndbi", "lulc"].map((t) => <button key={t} className="badge bg-slate-100 text-slate-700 hover:bg-brand-100" onClick={() => product(s.id, t)}>{t.toUpperCase()}</button>)}</td></tr>)}</tbody></table>}
                {products.map((p: any) => <div key={p.id} className="rounded border border-slate-200 p-3"><div className="flex flex-wrap items-center gap-2"><b>{p.product_type?.toUpperCase()}</b><ValueKind kind={p.value_kind} /><DemoBadge show={p.is_demo} /></div><pre className="mt-1 overflow-auto text-xs text-slate-600">{JSON.stringify(p.statistics, null, 1)}</pre></div>)}
                {change && <div className="rounded border border-brand-200 bg-brand-50 p-3"><b>Change detection</b> <ValueKind kind={change.value_kind} /><div className="mt-1 grid grid-cols-2 gap-1 text-xs sm:grid-cols-4"><div>Vegetation loss: <b>{change.vegetation_loss_km2} km²</b></div><div>Vegetation gain: <b>{change.vegetation_gain_km2} km²</b></div><div>Urban expansion: <b>{change.urban_expansion_km2} km²</b></div><div>Water change: <b>{change.water_change_km2 ?? "—"} km²</b></div></div>{change.recommendation_id && <Link href={`/app/evidence/${change.recommendation_id}`} className="mt-2 inline-block text-xs text-brand-700 underline">Evidence trace →</Link>}</div>}
              </div>
            )}
            {rsTab === "runs" && <table className="table mt-3"><thead><tr><th>Operation</th><th>Status</th><th>Duration</th><th>When</th></tr></thead><tbody>{(runs?.items || []).map((r: any) => <tr key={r.id}><td>{titleCase(r.operation)}</td><td>{r.status}</td><td>{r.duration_ms} ms</td><td>{r.created_at?.slice(0, 16).replace("T", " ")}</td></tr>)}</tbody></table>}
          </div>
        </div>
        <aside className="card p-4">
          <h3 className="font-bold text-navy-800">Result</h3>
          {!result ? <p className="mt-2 text-sm text-slate-500">Run an operation to see results. Geometric results are highlighted on the map.</p> : (
            <div className="mt-2 space-y-2 text-sm">
              <div className="flex flex-wrap gap-1"><span className="badge bg-brand-100 text-brand-800">{titleCase(result.operation || op)}</span>{result.value_kind && <ValueKind kind={result.value_kind} />}{result.is_demo && <DemoBadge />}</div>
              {op === "area" && <div className="grid grid-cols-2 gap-2"><div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-500">Area</div><b>{fmtNum(result.area_km2, 2)} km²</b></div><div className="rounded bg-slate-50 p-2"><div className="text-xs text-slate-500">Perimeter</div><b>{fmtNum(result.perimeter_km, 1)} km</b></div></div>}
              {op === "intersection" && <div><div>Intersection area: <b>{fmtNum(result.total_area_km2, 2)} km²</b> ({result.feature_count} features)</div><ul className="mt-1 max-h-40 overflow-auto text-xs">{(result.by_class || []).map((c: any) => <li key={c.class} className="flex justify-between"><span>{c.class}</span><b>{fmtNum(c.area_km2, 2)} km²</b></li>)}</ul></div>}
              {op === "proximity" && <div><div>{result.count} features within radius · nearest {fmtNum(result.nearest_m)} m</div><ul className="mt-1 max-h-48 overflow-auto text-xs">{(result.features || []).map((f: any) => <li key={f.id} className="flex justify-between"><span>{f.name || f.class || f.id.slice(0, 8)}</span><b>{fmtNum(f.distance_m)} m</b></li>)}</ul></div>}
              {op === "aggregate" && <table className="table text-xs"><thead><tr><th>Unit</th><th>Total</th><th>Share %</th></tr></thead><tbody>{(result.items || []).map((u: any) => <tr key={u.id}><td>{u.name}</td><td>{fmtNum(u.total, 2)}</td><td>{u.share_of_unit_pct ?? "—"}</td></tr>)}</tbody></table>}
              {op === "hotspot" && <div><div>{result.hot_cells} hot cells of {result.cells?.length} · mean {fmtNum(result.mean, 2)} · sd {fmtNum(result.sd, 2)}</div><ul className="mt-1 max-h-48 overflow-auto text-xs">{(result.cells || []).slice(0, 12).map((c: any, i: number) => <li key={i} className="flex justify-between"><span>[{c.cell.map((v: number) => v.toFixed(2)).join(", ")}]</span><b className={c.class === "hot" ? "text-red-600" : c.class === "cold" ? "text-blue-600" : ""}>z {c.z}</b></li>)}</ul></div>}
              {op === "boundary-select" && <ul className="text-xs">{(result.items || []).map((u: any) => <li key={u.id} className="flex justify-between"><span>{u.name}</span><b>{u.overlap_pct}% overlap</b></li>)}</ul>}
              {op === "affected-area" && <div><div>Zone {fmtNum(result.zone_area_km2, 1)} km² · {result.admin_units_affected} admin units</div><ul className="mt-1 text-xs">{(result.impacts || []).map((i: any) => <li key={i.layer.id}><b>{i.layer.name}</b>: {fmtNum(i.affected_area_km2, 2)} km² · {i.feature_count} features</li>)}</ul></div>}
              {result.recommendation_id && <Link href={`/app/evidence/${result.recommendation_id}`} className="btn-secondary mt-2 w-full">Evidence trace</Link>}
              <details className="text-xs"><summary className="cursor-pointer text-slate-500">Raw JSON</summary><pre className="max-h-60 overflow-auto rounded bg-slate-50 p-2">{JSON.stringify(result, null, 1).slice(0, 4000)}</pre></details>
            </div>
          )}
        </aside>
      </div>
    </>
  );
}

export default function GisPage() {
  return <Suspense fallback={<Loading />}><GisInner /></Suspense>;
}
