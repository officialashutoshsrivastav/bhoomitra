"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, Field, Loading, StatusBadge, Tabs } from "@/components/ui";
import { api, fmtDate, fmtNum, titleCase } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";
import { useApi, useDebounce } from "@/lib/hooks";

function Users() {
  const { user: me } = useAuth();
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [status, setStatus] = useState("");
  const { data, reload, loading } = useApi<any>("/admin/users", { q: dq, status: status || undefined, page_size: 50 });
  const { data: roles } = useApi<any>("/admin/roles");
  const { data: orgs } = useApi<any>("/organizations", { page_size: 100 });
  const [err, setErr] = useState<any>(null);
  const [nu, setNu] = useState({ email: "", full_name: "", password: "", roles: ["public_user"], organization_id: "" });
  const [showNew, setShowNew] = useState(false);
  const call = async (fn: () => Promise<any>) => { setErr(null); try { await fn(); reload(); } catch (ex) { setErr(ex); } };
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-2"><input className="input max-w-xs" placeholder="Search name or email" value={q} onChange={(e) => setQ(e.target.value)} /><select className="input w-auto" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{["pending", "active", "disabled", "locked"].map((s) => <option key={s}>{s}</option>)}</select><button className="btn-primary ml-auto" onClick={() => setShowNew((s) => !s)}>Create user</button></div>
      {showNew && <div className="card grid gap-3 p-4 md:grid-cols-5"><Field label="Email"><input className="input" value={nu.email} onChange={(e) => setNu({ ...nu, email: e.target.value })} /></Field><Field label="Name"><input className="input" value={nu.full_name} onChange={(e) => setNu({ ...nu, full_name: e.target.value })} /></Field><Field label="Password"><input className="input" type="password" value={nu.password} onChange={(e) => setNu({ ...nu, password: e.target.value })} /></Field><Field label="Role"><select className="input" value={nu.roles[0]} onChange={(e) => setNu({ ...nu, roles: [e.target.value] })}>{(roles?.roles || []).map((r: any) => <option key={r.name} value={r.name}>{r.label}</option>)}</select></Field><Field label="Organisation"><select className="input" value={nu.organization_id} onChange={(e) => setNu({ ...nu, organization_id: e.target.value })}><option value="">—</option>{(orgs?.items || []).map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field><div className="md:col-span-5"><button className="btn-primary" onClick={() => call(async () => { await api("/admin/users", { body: { ...nu, organization_id: nu.organization_id || null } }); setShowNew(false); })}>Create</button></div></div>}
      <ErrorText error={err} />
      {loading ? <Loading /> : <div className="card overflow-x-auto"><table className="table"><thead><tr><th>User</th><th>Organisation</th><th>Roles</th><th>Status</th><th>Last login</th><th>Actions</th></tr></thead><tbody>{(data?.items || []).map((u: any) => <tr key={u.id}><td><div className="font-medium text-navy-800">{u.full_name}</div><div className="text-xs text-slate-500">{u.email}{u.designation ? ` · ${u.designation}` : ""}</div></td><td className="text-xs">{u.organization_name || "—"}</td><td><select className="input w-auto text-xs" value={u.roles[0] || "public_user"} onChange={(e) => call(() => api(`/admin/users/${u.id}/roles`, { method: "PUT", body: { roles: [e.target.value] } }))} disabled={u.id === me?.id}>{(roles?.roles || []).map((r: any) => <option key={r.name} value={r.name}>{r.label}</option>)}</select>{u.roles.length > 1 && <div className="text-[10px] text-slate-500">+{u.roles.slice(1).map((r: string) => ROLE_LABELS[r]).join(", ")}</div>}</td><td><StatusBadge status={u.status} />{u.locked_until && <div className="text-[10px] text-red-600">locked</div>}</td><td className="text-xs">{u.last_login_at ? fmtDate(u.last_login_at) : "never"}</td><td className="space-x-2 whitespace-nowrap text-xs">{u.status !== "active" && <button className="text-emerald-700 underline" onClick={() => call(() => api(`/admin/users/${u.id}/activate`, { body: {} }))}>activate</button>}{u.status === "active" && u.id !== me?.id && <button className="text-red-600 underline" onClick={() => call(() => api(`/admin/users/${u.id}/disable`, { body: {} }))}>disable</button>}</td></tr>)}</tbody></table></div>}
    </div>
  );
}

function Roles() {
  const { data } = useApi<any>("/admin/roles");
  if (!data) return <Loading />;
  return (
    <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{data.roles.map((r: any) => <div key={r.name} className="card p-4 text-sm"><div className="flex items-center justify-between"><b className="text-navy-800">{r.label}</b><span className="badge bg-slate-100 text-slate-700">{r.user_count} users</span></div><div className="mt-2 flex flex-wrap gap-1">{r.permissions.map((p: string) => <span key={p} className="badge bg-brand-50 text-brand-800">{p}</span>)}</div></div>)}<div className="card p-4 text-xs text-slate-600 md:col-span-2 xl:col-span-3"><b>Permission catalogue</b><div className="mt-1 grid gap-1 md:grid-cols-3">{data.permissions.map((p: any) => <div key={p.code}><code>{p.code}</code> — {p.description}</div>)}</div></div></div>
  );
}

function Approvals() {
  const { data, reload } = useApi<any>("/admin/approvals", { status: "pending", page_size: 50 });
  const [err, setErr] = useState<any>(null);
  const decide = async (id: string, decision: string) => { setErr(null); try { await api(`/admin/approvals/${id}/decide`, { body: { decision } }); reload(); } catch (ex) { setErr(ex); } };
  const activate = async (id: string) => { setErr(null); try { await api(`/admin/users/${id}/activate`, { body: {} }); reload(); } catch (ex) { setErr(ex); } };
  return (
    <div className="mt-4 space-y-4">
      <ErrorText error={err} />
      <div className="card overflow-x-auto"><h3 className="p-3 font-bold text-navy-800">Pending approvals</h3><table className="table"><thead><tr><th>Item</th><th>Type</th><th>Requested by</th><th>When</th><th></th></tr></thead><tbody>{(data?.items || []).map((a: any) => <tr key={a.id}><td>{a.link ? <a className="text-brand-700 underline" href={a.link}>{a.title}</a> : a.title}</td><td>{titleCase(a.target_type)}</td><td>{a.requested_by_name || "—"}</td><td>{fmtDate(a.created_at)}</td><td className="space-x-2"><button className="btn-primary" onClick={() => decide(a.id, "approve")}>Approve</button><button className="btn-danger" onClick={() => decide(a.id, "reject")}>Reject</button></td></tr>)}</tbody></table>{!data?.items?.length && <p className="p-3 text-sm text-slate-500">Queue is empty.</p>}</div>
      <div className="card overflow-x-auto"><h3 className="p-3 font-bold text-navy-800">Pending user activations</h3><table className="table"><thead><tr><th>User</th><th>Email</th><th>Registered</th><th></th></tr></thead><tbody>{(data?.pending_user_activations || []).map((u: any) => <tr key={u.id}><td>{u.full_name}</td><td>{u.email}</td><td>{fmtDate(u.created_at)}</td><td><button className="btn-secondary" onClick={() => activate(u.id)}>Activate</button></td></tr>)}</tbody></table>{!data?.pending_user_activations?.length && <p className="p-3 text-sm text-slate-500">No pending users.</p>}</div>
    </div>
  );
}

function Integrations() {
  const { data, reload } = useApi<any>("/integrations");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<any>(null);
  const check = async (c: string) => { setBusy(c); setErr(null); try { setResult(await api(`/integrations/${c}/check`, { body: {} })); reload(); } catch (ex) { setErr(ex); } finally { setBusy(null); } };
  const load = async () => { setBusy("load"); setErr(null); try { setResult(await api("/integrations/geoboundaries/load", { method: "POST", params: { adm: "ADM1" } })); } catch (ex) { setErr(ex); } finally { setBusy(null); } };
  return (
    <div className="mt-4 space-y-3">
      <ErrorText error={err} />
      {result && <Alert kind={result.status === "ok" || result.loaded ? "success" : "info"}>{JSON.stringify(result)}</Alert>}
      <div className="grid gap-3 md:grid-cols-2">{(data?.items || []).map((i: any) => <div key={i.connector} className="card p-4 text-sm"><div className="flex items-center justify-between"><b className="text-navy-800">{i.display_name}</b><span className={`badge ${i.mode === "live" ? "bg-emerald-100 text-emerald-800" : "bg-amber-100 text-amber-800"}`}>{i.mode}</span></div><p className="mt-1 text-slate-600">{i.description}</p><div className="mt-2 text-xs text-slate-500">Settings: {i.settings?.join(", ")}</div>{i.last_status && <div className="mt-1 text-xs">Last check: <b>{i.last_status}</b> — {i.last_message} <span className="text-slate-400">({fmtDate(i.last_checked_at)})</span></div>}<div className="mt-2 flex gap-2"><button className="btn-secondary" disabled={busy === i.connector} onClick={() => check(i.connector)}>{busy === i.connector ? "Checking…" : "Check"}</button>{i.connector === "geoboundaries" && <button className="btn-primary" disabled={busy === "load"} onClick={load}>{busy === "load" ? "Loading…" : "Load ADM1 (network)"}</button>}</div></div>)}</div>
    </div>
  );
}

function Audit() {
  const [action, setAction] = useState("");
  const [result, setResult] = useState("");
  const [page, setPage] = useState(1);
  const { data } = useApi<any>("/audit", { action: action || undefined, result: result || undefined, page, page_size: 50 });
  const { data: actions } = useApi<any>("/audit/actions");
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap gap-2"><select className="input w-auto" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}><option value="">All actions</option>{(actions?.items || []).map((a: any) => <option key={a.action} value={a.action}>{a.action} ({a.count})</option>)}</select><select className="input w-auto" value={result} onChange={(e) => { setResult(e.target.value); setPage(1); }}><option value="">All results</option><option value="success">success</option><option value="failure">failure</option><option value="denied">denied</option></select><span className="ml-auto text-sm text-slate-500">{fmtNum(data?.total)} events</span></div>
      <div className="card overflow-x-auto"><table className="table text-xs"><thead><tr><th>Time</th><th>Action</th><th>Result</th><th>User</th><th>Resource</th><th>IP</th><th>Detail</th></tr></thead><tbody>{(data?.items || []).map((a: any) => <tr key={a.id}><td className="whitespace-nowrap">{a.created_at.slice(0, 19).replace("T", " ")}</td><td className="font-mono">{a.action}</td><td><span className={`badge ${a.result === "success" ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-700"}`}>{a.result}</span></td><td>{a.user_email || "—"}</td><td className="font-mono">{a.resource_type}{a.resource_id ? `:${a.resource_id.slice(0, 8)}` : ""}</td><td>{a.ip_address || "—"}</td><td className="max-w-[300px] truncate" title={JSON.stringify(a.detail)}>{a.detail ? JSON.stringify(a.detail) : ""}</td></tr>)}</tbody></table></div>
      <div className="flex justify-between text-sm"><button className="btn-ghost" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Prev</button><span>Page {page} / {data?.pages || 1}</span><button className="btn-ghost" disabled={page >= (data?.pages || 1)} onClick={() => setPage(page + 1)}>Next →</button></div>
    </div>
  );
}

function Jobs() {
  const { data, reload } = useApi<any>("/admin/jobs", { page_size: 50 });
  const [err, setErr] = useState<any>(null);
  const retry = async (id: string) => { setErr(null); try { await api(`/admin/jobs/${id}/retry`, { body: {} }); reload(); } catch (ex) { setErr(ex); } };
  const reindex = async () => { setErr(null); try { await api("/admin/maintenance/reindex", { body: {} }); reload(); } catch (ex) { setErr(ex); } };
  return (
    <div className="mt-4 space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm"><span className="badge bg-slate-100 text-slate-700">worker mode: {data?.workers?.mode}</span>{data?.workers?.note && <span className="text-xs text-slate-500">{data.workers.note}</span>}<button className="btn-secondary ml-auto" onClick={reindex}>Rebuild search index</button><button className="btn-ghost" onClick={reload}>Refresh</button></div>
      <ErrorText error={err} />
      <div className="card overflow-x-auto"><table className="table text-xs"><thead><tr><th>Job</th><th>Target</th><th>Status</th><th>Progress</th><th>Retries</th><th>Created</th><th>Error</th><th></th></tr></thead><tbody>{(data?.items || []).map((j: any) => <tr key={j.id}><td className="font-mono">{j.job_type}</td><td className="font-mono">{j.target_type}{j.target_id ? `:${j.target_id.slice(0, 8)}` : ""}</td><td><StatusBadge status={j.status} /></td><td>{j.progress}%</td><td>{j.retry_count}/{j.max_retries}</td><td className="whitespace-nowrap">{j.created_at.slice(0, 19).replace("T", " ")}</td><td className="max-w-[260px] truncate text-red-600" title={j.error}>{j.error}</td><td>{["failed", "cancelled"].includes(j.status) && <button className="text-brand-700 underline" onClick={() => retry(j.id)}>retry</button>}</td></tr>)}</tbody></table></div>
    </div>
  );
}

function Settings() {
  const { data, reload } = useApi<any>("/admin/settings");
  const [f, setF] = useState({ key: "", value: "", value_type: "string", description: "", is_secret: false });
  const [err, setErr] = useState<any>(null);
  const save = async () => { setErr(null); try { await api("/admin/settings", { method: "PUT", body: f }); setF({ key: "", value: "", value_type: "string", description: "", is_secret: false }); reload(); } catch (ex) { setErr(ex); } };
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <div className="card p-4"><h3 className="font-bold text-navy-800">Runtime configuration</h3><dl className="mt-2 grid grid-cols-2 gap-y-1 text-sm">{Object.entries(data?.runtime || {}).map(([k, v]) => <div key={k} className="contents"><dt className="text-slate-500">{k}</dt><dd className="font-mono text-xs">{String(v)}</dd></div>)}</dl><p className="mt-3 text-xs text-slate-500">Runtime values come from environment variables; see backend/.env.example.</p></div>
      <div className="card p-4"><h3 className="font-bold text-navy-800">System settings</h3><table className="table mt-2 text-xs"><thead><tr><th>Key</th><th>Value</th><th>Type</th><th>Updated</th></tr></thead><tbody>{(data?.items || []).map((s: any) => <tr key={s.key}><td className="font-mono">{s.key}</td><td className="max-w-[200px] truncate">{s.value}</td><td>{s.value_type}</td><td>{fmtDate(s.updated_at)}</td></tr>)}</tbody></table><div className="mt-3 grid grid-cols-2 gap-2"><input className="input" placeholder="key (e.g. platform.banner)" value={f.key} onChange={(e) => setF({ ...f, key: e.target.value })} /><input className="input" placeholder="value" value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /><input className="input" placeholder="description" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /><div className="flex items-center gap-2"><select className="input w-auto" value={f.value_type} onChange={(e) => setF({ ...f, value_type: e.target.value })}>{["string", "int", "float", "bool", "json"].map((t) => <option key={t}>{t}</option>)}</select><label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={f.is_secret} onChange={(e) => setF({ ...f, is_secret: e.target.checked })} /> secret</label><button className="btn-primary" disabled={!f.key} onClick={save}>Save</button></div></div><ErrorText error={err} /></div>
    </div>
  );
}

function Overview() {
  const { data } = useApi<any>("/admin/overview");
  if (!data) return <Loading />;
  return <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">{[["Users", data.users?.total], ["Active users", data.users?.active], ["Pending users", data.users?.pending], ["Organisations", data.organizations], ["Approvals pending", data.approvals_pending], ["Workspaces", data.workspaces], ["Scenarios under review", data.scenarios_under_review], ["Versions processing", data.processing?.versions_in_progress], ["Versions failed", data.processing?.versions_failed], ["Jobs queued", data.processing?.jobs_queued], ["Jobs failed", data.processing?.jobs_failed], ["Audit events (24h)", data.audit_events_24h], ["Failed logins (24h)", data.failed_logins_24h]].map(([l, v]) => <div key={String(l)} className="card p-3"><div className="text-xs text-slate-500">{l}</div><div className="text-xl font-bold text-navy-800">{fmtNum(v as number)}</div></div>)}<div className="card p-3 md:col-span-2"><div className="text-xs text-slate-500">Workers</div><div className="text-sm">{data.workers?.mode} · {data.workers?.note}</div></div></div>;
}

function AdminInner() {
  const sp = useSearchParams();
  const { can } = useAuth();
  const [tab, setTab] = useState(sp.get("tab") || "overview");
  const tabs = [{ id: "overview", label: "Overview" }, ...(can("admin.manage_users") ? [{ id: "users", label: "Users" }] : []), ...(can("admin.manage_roles", "admin.manage_users") ? [{ id: "roles", label: "Roles & permissions" }] : []), ...(can("admin.approvals", "document.review", "dataset.approve") ? [{ id: "approvals", label: "Approvals" }] : []), ...(can("integration.manage") ? [{ id: "integrations", label: "Integrations" }] : []), ...(can("admin.manage_config") ? [{ id: "jobs", label: "Jobs" }, { id: "settings", label: "Settings" }] : []), ...(can("audit.read") ? [{ id: "audit", label: "Audit log" }] : [])];
  return (
    <>
      <PageHeader title="Administration" subtitle="Users, roles, approvals, integrations, background jobs, settings and the audit trail." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === "overview" && <Overview />}
      {tab === "users" && <Users />}
      {tab === "roles" && <Roles />}
      {tab === "approvals" && <Approvals />}
      {tab === "integrations" && <Integrations />}
      {tab === "jobs" && <Jobs />}
      {tab === "settings" && <Settings />}
      {tab === "audit" && <Audit />}
      <p className="mt-6 text-xs text-slate-500"><DemoBadge /> badges mark synthetic seed data throughout the platform.</p>
    </>
  );
}

export default function AdminPage() {
  return <Suspense fallback={<Loading />}><AdminInner /></Suspense>;
}
