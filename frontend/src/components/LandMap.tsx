"use client";

import maplibregl, { Map as MLMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

export type LayerDef = { id: string; name: string; category: string; geometry_type: string; class_field?: string | null; legend?: Record<string, string> | null; feature_count: number; is_demo: boolean };

const TILE_TEMPLATE = process.env.NEXT_PUBLIC_BASEMAP_TILES || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const FALLBACK_COLORS = ["#0f5f3a", "#3b82c4", "#f28c28", "#7c3aed", "#c9a36b", "#b0413e", "#0891b2", "#65a30d"];

function colorExpression(layer: LayerDef): any {
  const legend = layer.legend || {};
  const entries = Object.entries(legend);
  if (!entries.length) return FALLBACK_COLORS[Math.abs(layer.id.charCodeAt(0)) % FALLBACK_COLORS.length];
  const expr: any[] = ["match", ["get", "class"]];
  entries.forEach(([k, v]) => expr.push(k, v));
  expr.push("#94a3b8");
  return expr;
}

export default function LandMap({ layers, active, basemap, unitLevel, parentId, onSelectUnit, onFeature, selectedUnitId, highlightGeometry }: { layers: LayerDef[]; active: string[]; basemap: "osm" | "none"; unitLevel: string; parentId?: string | null; onSelectUnit?: (unit: any) => void; onFeature?: (props: any) => void; selectedUnitId?: string | null; highlightGeometry?: any }) {
  const ref = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ref.current || mapRef.current) return;
    const map = new maplibregl.Map({
      container: ref.current,
      style: { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#e8f1ec" } }] },
      center: [78.5, 23.5],
      zoom: 4.3,
      attributionControl: false,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), "top-left");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 120, unit: "metric" }), "bottom-left");
    map.addControl(new maplibregl.AttributionControl({ compact: true }), "bottom-right");
    map.on("load", () => {
      map.addSource("units", { type: "geojson", promoteId: "id", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "units-fill", type: "fill", source: "units", paint: { "fill-color": "#0f5f3a", "fill-opacity": ["case", ["boolean", ["feature-state", "selected"], false], 0.25, 0.05] } });
      map.addLayer({ id: "units-line", type: "line", source: "units", paint: { "line-color": "#0b4a2d", "line-width": 1.2 } });
      map.addLayer({ id: "units-label", type: "symbol", source: "units", layout: { "text-field": ["get", "name"], "text-size": 11, "text-font": ["Open Sans Regular", "Arial Unicode MS Regular"] }, paint: { "text-color": "#17244a", "text-halo-color": "#ffffff", "text-halo-width": 1.2 } });
      map.addSource("highlight", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "highlight-fill", type: "fill", source: "highlight", paint: { "fill-color": "#f28c28", "fill-opacity": 0.25 } });
      map.addLayer({ id: "highlight-line", type: "line", source: "highlight", paint: { "line-color": "#f28c28", "line-width": 2 } });
      map.on("click", "units-fill", (e) => {
        const f = e.features?.[0];
        if (f && onSelectUnit) onSelectUnit({ ...f.properties, id: f.properties?.id });
      });
      map.on("mouseenter", "units-fill", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "units-fill", () => (map.getCanvas().style.cursor = ""));
      mapRef.current = map;
      setReady(true);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // basemap
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const has = !!map.getSource("basemap");
    if (basemap === "osm" && !has) {
      map.addSource("basemap", { type: "raster", tiles: [TILE_TEMPLATE], tileSize: 256, attribution: "© OpenStreetMap contributors" });
      map.addLayer({ id: "basemap", type: "raster", source: "basemap", paint: { "raster-opacity": 0.85 } }, "units-fill");
    } else if (basemap === "none" && has) {
      map.removeLayer("basemap");
      map.removeSource("basemap");
    }
  }, [basemap, ready]);

  // admin units
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    api<any>("/gis/admin-units/geojson", { params: { level: unitLevel, parent_id: parentId || undefined, simplify: 0.005 } })
      .then((fc) => {
        const data = { type: "FeatureCollection", features: (fc.features || []).map((f: any) => ({ ...f, properties: { ...(f.properties || {}), id: f.id } })) } as any;
        (map.getSource("units") as maplibregl.GeoJSONSource).setData(data);
        if (fc.features?.length && parentId) {
          const b = new maplibregl.LngLatBounds();
          fc.features.forEach((f: any) => walkCoords(f.geometry, (c) => b.extend(c as [number, number])));
          map.fitBounds(b, { padding: 40, duration: 600 });
        }
      })
      .catch(() => {});
  }, [unitLevel, parentId, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("highlight") as maplibregl.GeoJSONSource | undefined)?.setData(highlightGeometry ? { type: "Feature", geometry: highlightGeometry, properties: {} } : { type: "FeatureCollection", features: [] });
  }, [highlightGeometry, ready]);

  // thematic layers
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    layers.forEach((layer) => {
      const sid = `layer-${layer.id}`;
      const on = active.includes(layer.id);
      if (on && !map.getSource(sid)) {
        map.addSource(sid, { type: "geojson", data: { type: "FeatureCollection", features: [] } });
        const color = colorExpression(layer);
        if (layer.geometry_type === "Point") {
          map.addLayer({ id: `${sid}-pt`, type: "circle", source: sid, paint: { "circle-radius": 5, "circle-color": color, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } }, "units-label");
        } else {
          map.addLayer({ id: `${sid}-fill`, type: "fill", source: sid, paint: { "fill-color": color, "fill-opacity": 0.55 } }, "units-line");
          map.addLayer({ id: `${sid}-line`, type: "line", source: sid, paint: { "line-color": color, "line-width": 0.8 } }, "units-line");
        }
        const clickLayer = layer.geometry_type === "Point" ? `${sid}-pt` : `${sid}-fill`;
        map.on("click", clickLayer, (e) => {
          const f = e.features?.[0];
          if (!f) return;
          const props = { ...(f.properties || {}), __layer: layer.name };
          onFeature?.(props);
          new maplibregl.Popup({ closeButton: true, maxWidth: "260px" }).setLngLat(e.lngLat).setHTML(`<div style="font:12px system-ui"><b>${layer.name}</b><br/>${Object.entries(props).filter(([k]) => !k.startsWith("__") && k !== "properties").slice(0, 8).map(([k, v]) => `<span style="color:#64748b">${k}</span>: ${typeof v === "object" ? JSON.stringify(v) : v}`).join("<br/>")}</div>`).addTo(map);
        });
        api<any>(`/gis/layers/${layer.id}/features`, { params: { limit: 2000, simplify: 0.002 } })
          .then((fc) => {
            const src = map.getSource(sid) as maplibregl.GeoJSONSource | undefined;
            src?.setData({ type: "FeatureCollection", features: fc.features.map((f: any) => ({ ...f, properties: { ...(f.properties || {}), ...(typeof f.properties?.properties === "object" ? f.properties.properties : {}) } })) });
          })
          .catch(() => {});
      } else if (!on && map.getSource(sid)) {
        [`${sid}-pt`, `${sid}-fill`, `${sid}-line`].forEach((l) => map.getLayer(l) && map.removeLayer(l));
        map.removeSource(sid);
      }
    });
  }, [layers, active, ready]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !selectedUnitId) return;
    api<any>(`/gis/admin-units/${selectedUnitId}`, { params: { simplify: 0.003 } })
      .then((f) => {
        const b = new maplibregl.LngLatBounds();
        walkCoords(f.geometry, (c) => b.extend(c as [number, number]));
        if (!b.isEmpty()) map.fitBounds(b, { padding: 60, duration: 700 });
      })
      .catch(() => {});
  }, [selectedUnitId, ready]);

  return <div ref={ref} className="h-full w-full rounded-xl" role="application" aria-label="Interactive land map" />;
}

function walkCoords(geom: any, fn: (c: number[]) => void) {
  if (!geom) return;
  const rec = (c: any) => (typeof c[0] === "number" ? fn(c) : c.forEach(rec));
  rec(geom.coordinates);
}
