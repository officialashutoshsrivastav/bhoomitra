"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, Field, Loading, StatusBadge, Tabs } from "@/components/ui";
import { api, fmtDate, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

const RES_HREF: Record<string, (id: string) => string> = { document: (id) => `/app/repository/${id}`, dataset: (id) => `/app/datasets/${id}`, scenario: (id) => `/app/simulation?scenario=${id}`, gis_layer: (id) => `/app/gis?layer=${id}`, report: () => `/app/reports`, analytics_run: () => `/app/analytics` };

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const { user } = useAuth();
  const { data: ws, loading, error, reload } = useApi<any>(`/workspaces/${id}`);
  const [tab, setTab] = useState("overview");
  const { data: tasks, reload: reloadTasks } = useApi<any>(`/workspaces/${id}/tasks`, {}, [tab]);
  const { data: resources, reload: reloadRes } = useApi<any>(`/workspaces/${id}/resources`, {}, [tab]);
  const { data: comments, reload: reloadComments } = useApi<any>(`/workspaces/${id}/comments`, {}, [tab]);
  const { data: activity } = useApi<any>(tab === "activity" ? `/workspaces/${id}/activity` : null, {}, [tab]);
  const [err, setErr] = useState<any>(null);
  const [task, setTask] = useState({ title: "", assignee_id: "", priority: "medium", due_date: "" });
  const [member, setMember] = useState({ email: "", role: "contributor" });
  const [comment, setComment] = useState("");
  const [res, setRes] = useState({ resource_type: "document", resource_id: "", title: "" });
  const call = async (fn: () => Promise<any>, after?: () => void) => { setErr(null); try { await fn(); after?.(); } catch (ex) { setErr(ex); } };
  if (loading) return <Loading />;
  if (error || !ws) return <Alert kind="error">Workspace not found or access denied.</Alert>;
  const editable = ws.my_role && ws.my_role !== "viewer";
  const isOwner = ws.my_role === "owner" || ws.owner_id === user?.id;
  return (
    <>
      <PageHeader title={ws.name} subtitle={ws.objective || ws.description} action={<div className="flex flex-wrap items-center gap-2"><StatusBadge status={ws.status} /><DemoBadge show={ws.is_demo} />{isOwner && ws.allowed_transitions?.map((t: string) => <button key={t} className="btn-secondary" onClick={() => call(() => api(`/workspaces/${id}/transition`, { body: { status: t } }), reload)}>→ {titleCase(t)}</button>)}</div>} />
      <ErrorText error={err} />
      <Tabs tabs={[{ id: "overview", label: "Overview" }, { id: "tasks", label: "Tasks", count: tasks?.items?.length }, { id: "resources", label: "Resources", count: resources?.items?.length }, { id: "discussion", label: "Discussion", count: comments?.items?.length }, { id: "activity", label: "Activity" }]} value={tab} onChange={setTab} />
      {tab === "overview" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-3">
          <div className="card p-5 lg:col-span-2"><h3 className="font-bold text-navy-800">Members</h3><ul className="mt-2 divide-y divide-slate-100 text-sm">{ws.members.map((m: any) => <li key={m.user_id} className="flex items-center justify-between py-1.5"><span>{m.name || m.email} <span className="text-xs text-slate-500">{m.email}</span></span><span className="flex items-center gap-2"><span className="badge bg-slate-100 text-slate-700">{m.role}</span>{isOwner && m.user_id !== ws.owner_id && <button className="text-xs text-red-600" onClick={() => call(() => api(`/workspaces/${id}/members/${m.user_id}`, { method: "DELETE" }), reload)}>remove</button>}</span></li>)}</ul>{isOwner && <div className="mt-3 flex flex-wrap gap-2"><input className="input max-w-xs" placeholder="user email" value={member.email} onChange={(e) => setMember({ ...member, email: e.target.value })} /><select className="input w-auto" value={member.role} onChange={(e) => setMember({ ...member, role: e.target.value })}><option value="viewer">viewer</option><option value="contributor">contributor</option><option value="editor">editor</option><option value="owner">owner</option></select><button className="btn-primary" disabled={!member.email} onClick={() => call(() => api(`/workspaces/${id}/members`, { body: member }), () => { setMember({ email: "", role: "contributor" }); reload(); })}>Add member</button></div>}</div>
          <div className="card p-5 text-sm"><div className="text-xs uppercase text-slate-500">Status</div><StatusBadge status={ws.status} /><div className="mt-3 text-xs uppercase text-slate-500">Created</div>{fmtDate(ws.created_at)}<div className="mt-3 text-xs uppercase text-slate-500">Visibility</div>{ws.is_public ? "Public" : "Private"}<div className="mt-3 text-xs uppercase text-slate-500">Tags</div>{ws.tags?.join(", ") || "—"}<p className="mt-4 text-xs text-slate-500">Lifecycle: draft → active → review → published → archived. Publishing requires an approved review request (or workspace.manage).</p></div>
        </div>
      )}
      {tab === "tasks" && (
        <div className="mt-4 space-y-3">
          {editable && <div className="card flex flex-wrap items-end gap-2 p-3"><Field label="Task"><input className="input min-w-[240px]" value={task.title} onChange={(e) => setTask({ ...task, title: e.target.value })} /></Field><Field label="Assignee"><select className="input" value={task.assignee_id} onChange={(e) => setTask({ ...task, assignee_id: e.target.value })}><option value="">—</option>{ws.members.map((m: any) => <option key={m.user_id} value={m.user_id}>{m.name || m.email}</option>)}</select></Field><Field label="Priority"><select className="input" value={task.priority} onChange={(e) => setTask({ ...task, priority: e.target.value })}>{["low", "medium", "high", "critical"].map((p) => <option key={p}>{p}</option>)}</select></Field><Field label="Due"><input className="input" type="date" value={task.due_date} onChange={(e) => setTask({ ...task, due_date: e.target.value })} /></Field><button className="btn-primary" disabled={task.title.length < 2} onClick={() => call(() => api(`/workspaces/${id}/tasks`, { body: { ...task, assignee_id: task.assignee_id || null, due_date: task.due_date || null } }), () => { setTask({ title: "", assignee_id: "", priority: "medium", due_date: "" }); reloadTasks(); })}>Add</button></div>}
          <div className="card overflow-x-auto"><table className="table"><thead><tr><th>Task</th><th>Assignee</th><th>Priority</th><th>Due</th><th>Status</th></tr></thead><tbody>{(tasks?.items || []).map((t: any) => <tr key={t.id}><td>{t.title}</td><td>{ws.members.find((m: any) => m.user_id === t.assignee_id)?.name || "—"}</td><td>{t.priority}</td><td>{t.due_date || "—"}</td><td>{editable ? <select className="input w-auto" value={t.status} onChange={(e) => call(() => api(`/workspaces/${id}/tasks/${t.id}`, { method: "PATCH", body: { status: e.target.value } }), reloadTasks)}>{["todo", "in_progress", "blocked", "done", "cancelled"].map((s) => <option key={s} value={s}>{s}</option>)}</select> : <StatusBadge status={t.status} />}</td></tr>)}</tbody></table>{!tasks?.items?.length && <p className="p-4 text-sm text-slate-500">No tasks.</p>}</div>
        </div>
      )}
      {tab === "resources" && (
        <div className="mt-4 space-y-3">
          {editable && <div className="card flex flex-wrap items-end gap-2 p-3"><Field label="Type"><select className="input" value={res.resource_type} onChange={(e) => setRes({ ...res, resource_type: e.target.value })}>{["document", "dataset", "scenario", "gis_layer", "analytics_run", "policy", "research_project", "report"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</select></Field><Field label="Resource ID"><input className="input min-w-[300px] font-mono text-xs" value={res.resource_id} onChange={(e) => setRes({ ...res, resource_id: e.target.value })} placeholder="UUID from the resource page" /></Field><Field label="Title"><input className="input" value={res.title} onChange={(e) => setRes({ ...res, title: e.target.value })} /></Field><button className="btn-primary" disabled={!res.resource_id} onClick={() => call(() => api(`/workspaces/${id}/resources`, { body: res }), () => { setRes({ resource_type: "document", resource_id: "", title: "" }); reloadRes(); })}>Link</button></div>}
          <ul className="grid gap-3 md:grid-cols-2">{(resources?.items || []).map((r: any) => <li key={r.id} className="card flex items-start justify-between gap-2 p-3 text-sm"><div><span className="badge bg-slate-100 text-slate-700">{titleCase(r.resource_type)}</span><Link href={RES_HREF[r.resource_type]?.(r.resource_id) || "#"} className="mt-1 block font-medium text-navy-800 hover:text-brand-700">{r.title || r.resource_id}</Link>{r.note && <p className="text-xs text-slate-500">{r.note}</p>}</div>{editable && <button className="text-xs text-red-600" onClick={() => call(() => api(`/workspaces/${id}/resources/${r.id}`, { method: "DELETE" }), reloadRes)}>unlink</button>}</li>)}</ul>{!resources?.items?.length && <p className="text-sm text-slate-500">No resources linked.</p>}
        </div>
      )}
      {tab === "discussion" && (
        <div className="mt-4 space-y-3">
          <ul className="space-y-2">{(comments?.items || []).map((c: any) => <li key={c.id} className="card p-3 text-sm"><div className="flex justify-between text-xs text-slate-500"><span className="font-semibold text-slate-700">{c.author_name || "User"}</span><span>{fmtDate(c.created_at)}</span></div><p className="mt-1 whitespace-pre-wrap text-slate-800">{c.body}</p></li>)}</ul>
          {editable && <div className="flex gap-2"><input className="input" placeholder="Write a comment…" value={comment} onChange={(e) => setComment(e.target.value)} /><button className="btn-primary" disabled={!comment} onClick={() => call(() => api(`/workspaces/${id}/comments`, { body: { body: comment } }), () => { setComment(""); reloadComments(); })}>Post</button></div>}
        </div>
      )}
      {tab === "activity" && <ul className="card mt-4 divide-y divide-slate-100 text-sm">{(activity?.items || []).map((a: any) => <li key={a.id} className="flex justify-between gap-3 p-3"><span>{a.summary || a.action}</span><span className="whitespace-nowrap text-xs text-slate-500">{fmtDate(a.created_at)}</span></li>)}{!activity?.items?.length && <li className="p-4 text-slate-500">No activity yet.</li>}</ul>}
    </>
  );
}
