"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const CATS = ["land_use", "agriculture", "population", "infrastructure", "climate", "socio_economic", "land_governance", "disputes", "project_outcomes", "remote_sensing", "geospatial_boundaries", "water", "forest", "soil"];

export default function NewDatasetPage() {
  const router = useRouter();
  const { data: sources } = useApi<any>("/datasets/sources");
  const [f, setF] = useState<any>({ name: "", description: "", category: "land_governance", publisher: "", source_id: "", geography: "", temporal_start: "", temporal_end: "", spatial_resolution: "", temporal_resolution: "", license: "", update_frequency: "", provenance: "", access_level: "internal", keywords: "", variables: "" });
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((s: any) => ({ ...s, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const body: any = { ...f, keywords: f.keywords ? f.keywords.split(",").map((k: string) => k.trim()).filter(Boolean) : [], variables: f.variables ? f.variables.split("\n").map((l: string) => l.trim()).filter(Boolean).map((l: string) => { const [code, name, unit] = l.split("|").map((x) => x.trim()); return { code, name: name || code, unit: unit || null }; }) : [] };
      ["source_id", "temporal_start", "temporal_end", "spatial_resolution", "temporal_resolution", "license", "update_frequency", "provenance", "publisher", "geography", "description"].forEach((k) => { if (!body[k]) delete body[k]; });
      const ds = await api("/datasets", { body });
      if (file) { const form = new FormData(); form.append("file", file); await api(`/datasets/${ds.id}/versions`, { form }); }
      router.push(`/app/datasets/${ds.id}`);
    } catch (ex) { setErr(ex); setBusy(false); }
  };
  return (
    <>
      <PageHeader title="Register dataset" subtitle="Describe the dataset, declare variables, then upload the first version (CSV, XLSX, GeoJSON, JSON)." />
      <form onSubmit={submit} className="card grid max-w-4xl gap-4 p-6 md:grid-cols-2">
        <div className="md:col-span-2"><Field label="Name"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} required minLength={3} /></Field></div>
        <Field label="Category"><select className="input" value={f.category} onChange={(e) => set("category", e.target.value)}>{CATS.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}</select></Field>
        <Field label="Access level"><select className="input" value={f.access_level} onChange={(e) => set("access_level", e.target.value)}><option value="internal">Internal</option><option value="public">Public</option><option value="open">Open data</option><option value="restricted">Restricted</option></select></Field>
        <div className="md:col-span-2"><Field label="Description"><textarea className="input" rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} /></Field></div>
        <Field label="Publisher"><input className="input" value={f.publisher} onChange={(e) => set("publisher", e.target.value)} /></Field>
        <Field label="Data source"><select className="input" value={f.source_id} onChange={(e) => set("source_id", e.target.value)}><option value="">—</option>{(sources || []).map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field>
        <Field label="Geography"><input className="input" value={f.geography} onChange={(e) => set("geography", e.target.value)} /></Field>
        <Field label="Licence"><input className="input" value={f.license} onChange={(e) => set("license", e.target.value)} /></Field>
        <Field label="Period start"><input className="input" type="date" value={f.temporal_start} onChange={(e) => set("temporal_start", e.target.value)} /></Field>
        <Field label="Period end"><input className="input" type="date" value={f.temporal_end} onChange={(e) => set("temporal_end", e.target.value)} /></Field>
        <Field label="Spatial resolution"><input className="input" placeholder="district" value={f.spatial_resolution} onChange={(e) => set("spatial_resolution", e.target.value)} /></Field>
        <Field label="Temporal resolution"><input className="input" placeholder="annual" value={f.temporal_resolution} onChange={(e) => set("temporal_resolution", e.target.value)} /></Field>
        <div className="md:col-span-2"><Field label="Provenance"><textarea className="input" rows={2} value={f.provenance} onChange={(e) => set("provenance", e.target.value)} placeholder="How was this data collected and processed?" /></Field></div>
        <Field label="Keywords (comma separated)"><input className="input" value={f.keywords} onChange={(e) => set("keywords", e.target.value)} /></Field>
        <Field label="Variables (one per line: code | name | unit)"><textarea className="input" rows={3} value={f.variables} onChange={(e) => set("variables", e.target.value)} placeholder={"cropping_intensity | Cropping intensity | %"} /></Field>
        <div className="md:col-span-2"><Field label="First version file" hint="Long format (variable, district/admin_code, year, value, unit) or wide format (one column per year) is recognised for observation ingestion."><input className="input" type="file" accept=".csv,.xlsx,.xls,.json,.geojson,.tsv" onChange={(e) => setFile(e.target.files?.[0] || null)} /></Field></div>
        <div className="md:col-span-2"><Alert kind="info">Uploaded versions are profiled automatically (column types, nulls, ranges). Rows that name an administrative unit are linked to it for spatial analytics.</Alert></div>
        <div className="md:col-span-2"><ErrorText error={err} /></div>
        <div className="md:col-span-2 flex gap-2"><button className="btn-primary" disabled={busy}>{busy ? "Saving…" : "Register dataset"}</button><button type="button" className="btn-ghost" onClick={() => router.back()}>Cancel</button></div>
      </form>
    </>
  );
}
