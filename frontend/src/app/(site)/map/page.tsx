"use client";

import { Layers as LayersIcon, MapPin, Search } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { Alert, DemoBadge, Hero, Loading } from "@/components/ui";
import { api, fmtNum, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi, useDebounce } from "@/lib/hooks";

const LandMap = dynamic(() => import("@/components/LandMap"), { ssr: false, loading: () => <Loading label="Loading map…" /> });

function MapInner() {
  const sp = useSearchParams();
  const { user } = useAuth();
  const { data: layersData } = useApi<any>("/gis/layers", { page_size: 100 });
  const layers = layersData?.items || [];
  const [active, setActive] = useState<string[]>([]);
  const [basemap, setBasemap] = useState<"osm" | "none">("osm");
  const [level, setLevel] = useState("state");
  const [parent, setParent] = useState<string | null>(null);
  const [selected, setSelected] = useState<any>(null);
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const { data: search } = useApi<any>(dq.length >= 2 ? "/gis/admin-units/search" : null, { q: dq });
  const statsLayer = active[0] || layers.find((l: any) => l.category === "land_use")?.id;
  const { data: stats } = useApi<any>(statsLayer ? `/gis/layers/${statsLayer}/statistics` : null, { admin_unit_id: selected?.id || undefined }, [statsLayer, selected?.id]);
  const { data: unitDetail } = useApi<any>(selected?.id ? `/gis/admin-units/${selected.id}` : null, { simplify: 0.002 }, [selected?.id]);

  useEffect(() => {
    if (!layers.length || active.length) return;
    const pre = sp.get("layer");
    const first = layers.find((l: any) => l.id === pre) || layers.find((l: any) => l.category === "land_use") || layers[0];
    if (first) setActive([first.id]);
    const unit = sp.get("unit");
    if (unit) api<any>(`/gis/admin-units/${unit}`).then((f) => selectUnit({ id: f.id, ...f.properties })).catch(() => {});
  }, [layers]);

  const selectUnit = (u: any) => {
    setSelected(u);
    if (u.level === "state") { setLevel("district"); setParent(u.id); }
  };
  const toggle = (id: string) => setActive((a) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]));
  const legendLayer = layers.find((l: any) => l.id === active[active.length - 1]);
  const pie = useMemo(() => (stats?.classes || []).map((c: any) => ({ name: c.class, value: c.share_pct, color: legendLayer?.legend?.[c.class] || "#94a3b8" })), [stats, legendLayer]);
  const allDemo = layers.length > 0 && layers.every((l: any) => l.is_demo);

  return (
    <>
      <Hero title="Interactive" accent="Map" subtitle="Explore land data with powerful geospatial tools" crumbs={[{ label: "Home", href: "/" }, { label: "Interactive Map" }]} tag="Maps for a Sustainable India" />
      <div className="mx-auto max-w-[1600px] px-4 py-6 sm:px-6 lg:px-8">
        {allDemo && <Alert kind="warn" className="mb-4">Boundaries and layers currently shown are <b>Demo / Synthetic Data</b>. Administrators can load real geoBoundaries (CC BY 4.0) from Admin → Integrations.</Alert>}
        <div className="grid gap-4 lg:grid-cols-[260px_1fr_300px]">
          <aside className="card p-4">
            <h3 className="flex items-center gap-2 font-bold text-navy-800"><LayersIcon className="h-4 w-4" /> Data layers</h3>
            <ul className="mt-2 space-y-1">
              {layers.map((l: any) => (
                <li key={l.id}><label className="flex cursor-pointer items-start gap-2 text-sm"><input type="checkbox" className="mt-0.5 accent-brand-600" checked={active.includes(l.id)} onChange={() => toggle(l.id)} /><span><span className="text-slate-800">{l.name.replace(" (Demo)", "")}</span><span className="block text-[11px] text-slate-500">{titleCase(l.category)} · {fmtNum(l.feature_count)} features{l.is_demo ? " · demo" : ""}</span></span></label></li>
              ))}
              {!layers.length && <li className="text-xs text-slate-500">No layers published yet.</li>}
            </ul>
            <h3 className="mt-5 font-bold text-navy-800">Base map</h3>
            <div className="mt-1 space-y-1 text-sm">
              <label className="flex items-center gap-2"><input type="radio" className="accent-brand-600" checked={basemap === "osm"} onChange={() => setBasemap("osm")} /> OpenStreetMap</label>
              <label className="flex items-center gap-2"><input type="radio" className="accent-brand-600" checked={basemap === "none"} onChange={() => setBasemap("none")} /> None (offline)</label>
            </div>
            <h3 className="mt-5 font-bold text-navy-800">Administrative level</h3>
            <select className="input mt-1" value={level} onChange={(e) => { setLevel(e.target.value); setParent(null); setSelected(null); }}><option value="state">States</option><option value="district">Districts</option></select>
            {parent && <button className="btn-ghost mt-2 w-full" onClick={() => { setLevel("state"); setParent(null); setSelected(null); }}>← Back to states</button>}
          </aside>
          <div className="space-y-3">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input className="input pl-9" placeholder="Search location (state, district…)" value={q} onChange={(e) => setQ(e.target.value)} />
              {search?.items?.length > 0 && q && (
                <ul className="absolute z-20 mt-1 w-full rounded-md border border-slate-200 bg-white shadow-lg">{search.items.map((u: any) => <li key={u.id}><button className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => { selectUnit(u); setQ(""); }}><MapPin className="h-4 w-4 text-brand-600" />{u.name} <span className="text-xs text-slate-500">{u.level}{u.parent_name ? ` · ${u.parent_name}` : ""}</span></button></li>)}</ul>
              )}
            </div>
            <div className="relative h-[560px] overflow-hidden rounded-xl border border-slate-200 bg-slate-100">
              <LandMap layers={layers} active={active} basemap={basemap} unitLevel={level} parentId={parent} onSelectUnit={selectUnit} selectedUnitId={selected?.id} highlightGeometry={unitDetail?.geometry} />
              {legendLayer?.legend && (
                <div className="absolute right-3 top-3 max-h-72 w-52 overflow-auto rounded-lg bg-white/95 p-3 text-xs shadow-card">
                  <div className="mb-1 font-bold text-navy-800">Legend — {legendLayer.name.replace(" (Demo)", "")}</div>
                  {Object.entries(legendLayer.legend).map(([k, v]: any) => <div key={k} className="flex items-center gap-2 py-0.5"><span className="h-3 w-3 rounded-sm" style={{ background: v }} />{titleCase(k)}</div>)}
                </div>
              )}
            </div>
          </div>
          <aside className="space-y-4">
            <div className="card p-4">
              <h3 className="flex items-center gap-2 font-bold text-navy-800"><MapPin className="h-4 w-4" /> Selected location</h3>
              {selected ? (
                <div className="mt-2 text-sm">
                  <div className="font-semibold text-navy-800">{selected.name} <DemoBadge show={!!selected.is_demo} /></div>
                  <div className="text-xs text-slate-500">{titleCase(selected.level)} · {selected.code}</div>
                  {unitDetail?.properties?.path?.length > 0 && <div className="mt-1 text-xs text-slate-500">{unitDetail.properties.path.map((p: any) => p.name).join(" › ")}</div>}
                  <div className="mt-2 grid grid-cols-2 gap-2 text-xs"><div className="rounded bg-slate-50 p-2"><div className="text-slate-500">Area</div><div className="font-semibold">{fmtNum(unitDetail?.properties?.area_km2 ?? selected.area_km2)} km²</div></div><div className="rounded bg-slate-50 p-2"><div className="text-slate-500">Centroid</div><div className="font-semibold">{unitDetail?.properties?.centroid_lat?.toFixed(2)}, {unitDetail?.properties?.centroid_lon?.toFixed(2)}</div></div></div>
                  {user && <Link href={`/app/gis?unit=${selected.id}`} className="btn-primary mt-3 w-full">Open in GIS workbench →</Link>}
                </div>
              ) : <p className="mt-2 text-sm text-slate-500">Click a boundary or search for a location.</p>}
            </div>
            <div className="card p-4">
              <h3 className="font-bold text-navy-800">Land use statistics</h3>
              <p className="text-xs text-slate-500">{legendLayer?.name?.replace(" (Demo)", "") || "Select a layer"}{selected ? ` · ${selected.name}` : " · all units"}</p>
              {stats?.classes?.length ? (
                <>
                  <div className="h-44"><ResponsiveContainer><PieChart><Pie data={pie} dataKey="value" nameKey="name" innerRadius={40} outerRadius={70} paddingAngle={2}>{pie.map((p: any, i: number) => <Cell key={i} fill={p.color} />)}</Pie><Tooltip formatter={(v: any) => `${Number(v).toFixed(1)}%`} /></PieChart></ResponsiveContainer></div>
                  <ul className="space-y-0.5 text-xs">{stats.classes.map((c: any) => <li key={c.class} className="flex justify-between"><span className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: legendLayer?.legend?.[c.class] || "#94a3b8" }} />{titleCase(c.class)}</span><span className="font-semibold">{c.share_pct?.toFixed(1)}% · {fmtNum(c.area_km2)} km²</span></li>)}</ul>
                  <div className="mt-2 text-xs text-slate-500">Total {fmtNum(stats.total_area_km2)} km² · {fmtNum(stats.feature_count)} features <DemoBadge show={!!legendLayer?.is_demo} /></div>
                </>
              ) : <p className="mt-2 text-sm text-slate-500">No statistics available.</p>}
            </div>
          </aside>
        </div>
      </div>
    </>
  );
}

export default function MapPage() {
  return <Suspense fallback={<Loading />}><MapInner /></Suspense>;
}
