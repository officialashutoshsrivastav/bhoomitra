"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

const TYPES = ["research_paper", "policy_paper", "government_report", "legal_document", "case_study", "working_paper", "technical_report", "guideline", "framework", "project_report", "policy_brief", "scheme", "act_rule"];

export default function NewDocumentPage() {
  const router = useRouter();
  const { data: orgs } = useApi<any>("/organizations", { page_size: 100 });
  const [f, setF] = useState<any>({ title: "", document_type: "research_paper", description: "", abstract: "", authors: "", keywords: "", topic: "", policy_area: "", research_area: "", geography: "", publication_date: "", language: "en", visibility: "internal", organization_id: "", publisher: "", source: "", license: "", doi: "" });
  const [file, setFile] = useState<File | null>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((s: any) => ({ ...s, [k]: v }));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try {
      const body: any = { ...f, authors: f.authors ? f.authors.split(",").map((a: string) => a.trim()).filter(Boolean) : [], keywords: f.keywords ? f.keywords.split(",").map((a: string) => a.trim()).filter(Boolean) : [] };
      ["publication_date", "organization_id", "topic", "policy_area", "research_area", "geography", "publisher", "source", "license", "doi", "description", "abstract"].forEach((k) => { if (!body[k]) delete body[k]; });
      const doc = await api("/documents", { body });
      if (file) {
        const form = new FormData();
        form.append("file", file);
        form.append("change_note", "Initial upload");
        await api(`/documents/${doc.id}/versions`, { form });
      }
      router.push(`/app/repository/${doc.id}`);
    } catch (ex) { setErr(ex); setBusy(false); }
  };
  return (
    <>
      <PageHeader title="New document" subtitle="Create the record, then upload the file. Processing starts automatically." />
      <form onSubmit={submit} className="card grid max-w-4xl gap-4 p-6 md:grid-cols-2">
        <div className="md:col-span-2"><Field label="Title"><input className="input" value={f.title} onChange={(e) => set("title", e.target.value)} required minLength={3} /></Field></div>
        <Field label="Document type"><select className="input" value={f.document_type} onChange={(e) => set("document_type", e.target.value)}>{TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}</select></Field>
        <Field label="Visibility"><select className="input" value={f.visibility} onChange={(e) => set("visibility", e.target.value)}><option value="internal">Internal (logged-in users)</option><option value="public">Public (after publication)</option><option value="restricted">Restricted (organisation)</option><option value="private">Private</option></select></Field>
        <div className="md:col-span-2"><Field label="Description"><textarea className="input" rows={3} value={f.description} onChange={(e) => set("description", e.target.value)} /></Field></div>
        <div className="md:col-span-2"><Field label="Abstract"><textarea className="input" rows={4} value={f.abstract} onChange={(e) => set("abstract", e.target.value)} /></Field></div>
        <Field label="Authors (comma separated)"><input className="input" value={f.authors} onChange={(e) => set("authors", e.target.value)} /></Field>
        <Field label="Keywords (comma separated)"><input className="input" value={f.keywords} onChange={(e) => set("keywords", e.target.value)} /></Field>
        <Field label="Topic"><input className="input" value={f.topic} onChange={(e) => set("topic", e.target.value)} /></Field>
        <Field label="Policy area"><input className="input" value={f.policy_area} onChange={(e) => set("policy_area", e.target.value)} /></Field>
        <Field label="Research area"><input className="input" value={f.research_area} onChange={(e) => set("research_area", e.target.value)} /></Field>
        <Field label="Geography"><input className="input" value={f.geography} onChange={(e) => set("geography", e.target.value)} /></Field>
        <Field label="Publication date"><input className="input" type="date" value={f.publication_date} onChange={(e) => set("publication_date", e.target.value)} /></Field>
        <Field label="Organisation"><select className="input" value={f.organization_id} onChange={(e) => set("organization_id", e.target.value)}><option value="">—</option>{(orgs?.items || []).map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
        <Field label="Publisher"><input className="input" value={f.publisher} onChange={(e) => set("publisher", e.target.value)} /></Field>
        <Field label="Source"><input className="input" value={f.source} onChange={(e) => set("source", e.target.value)} /></Field>
        <Field label="Licence"><input className="input" value={f.license} onChange={(e) => set("license", e.target.value)} /></Field>
        <Field label="DOI"><input className="input" value={f.doi} onChange={(e) => set("doi", e.target.value)} /></Field>
        <div className="md:col-span-2"><Field label="File (PDF, DOCX, TXT, CSV, XLSX, images)" hint="Files are checksummed, type-sniffed and scanned before processing."><input className="input" type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} accept=".pdf,.docx,.txt,.csv,.xlsx,.png,.jpg,.jpeg,.tif,.tiff,.md" /></Field></div>
        <div className="md:col-span-2"><ErrorText error={err} /></div>
        <div className="md:col-span-2 flex gap-2"><button className="btn-primary" disabled={busy}>{busy ? "Creating…" : "Create document"}</button><button type="button" className="btn-ghost" onClick={() => router.back()}>Cancel</button></div>
      </form>
    </>
  );
}
