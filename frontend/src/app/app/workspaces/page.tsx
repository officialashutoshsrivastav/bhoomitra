"use client";

import { Plus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { DemoBadge, Empty, ErrorText, Field, Loading, StatusBadge } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

export default function WorkspacesPage() {
  const { can } = useAuth();
  const { data, loading, reload } = useApi<any>("/workspaces", { page_size: 50 });
  const [open, setOpen] = useState(false);
  const [f, setF] = useState({ name: "", objective: "", is_public: false });
  const [err, setErr] = useState<any>(null);
  const create = async () => { setErr(null); try { await api("/workspaces", { body: f }); setOpen(false); setF({ name: "", objective: "", is_public: false }); reload(); } catch (ex) { setErr(ex); } };
  return (
    <>
      <PageHeader title="Workspaces" subtitle="Collaborative spaces linking documents, datasets, scenarios and tasks with members, comments and an activity log." action={can("workspace.create") ? <button className="btn-primary" onClick={() => setOpen((o) => !o)}><Plus className="h-4 w-4" /> New workspace</button> : null} />
      {open && <div className="card mb-4 grid gap-3 p-4 md:grid-cols-3"><Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field><Field label="Objective"><input className="input" value={f.objective} onChange={(e) => setF({ ...f, objective: e.target.value })} /></Field><div className="flex items-end gap-3"><label className="flex items-center gap-2 text-sm"><input type="checkbox" className="accent-brand-600" checked={f.is_public} onChange={(e) => setF({ ...f, is_public: e.target.checked })} /> Public (read-only for non-members once active)</label><button className="btn-primary" disabled={f.name.length < 2} onClick={create}>Create</button></div><div className="md:col-span-3"><ErrorText error={err} /></div></div>}
      {loading ? <Loading /> : data?.items?.length ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{data.items.map((w: any) => <Link key={w.id} href={`/app/workspaces/${w.id}`} className="card p-4 hover:shadow-lg"><div className="flex flex-wrap items-center gap-2"><StatusBadge status={w.status} /><DemoBadge show={w.is_demo} />{w.my_role && <span className="badge bg-slate-100 text-slate-700">{w.my_role}</span>}</div><h3 className="mt-2 font-semibold text-navy-800">{w.name}</h3><p className="mt-1 line-clamp-2 text-sm text-slate-600">{w.objective || w.description || "—"}</p><div className="mt-3 flex items-center gap-3 text-xs text-slate-500"><span className="flex items-center gap-1"><Users className="h-3.5 w-3.5" />{w.members?.length}</span><span>{w.counts?.resources} resources</span><span>{w.counts?.tasks_open} open tasks</span><span className="ml-auto">{fmtDate(w.updated_at)}</span></div></Link>)}</div>
      ) : <Empty title="No workspaces" hint="Create a workspace to collaborate with colleagues." />}
    </>
  );
}
