"use client";

import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, ErrorText, Field, KV } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { ROLE_LABELS, useAuth } from "@/lib/auth";

export default function ProfilePage() {
  const { user, reload } = useAuth();
  const [f, setF] = useState({ full_name: user?.full_name || "", designation: user?.designation || "" });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<any>(null);
  const save = async () => { setErr(null); setMsg(null); try { await api("/auth/me", { method: "PATCH", body: f }); await reload(); setMsg("Profile updated."); } catch (ex) { setErr(ex); } };
  const change = async () => { setErr(null); setMsg(null); try { await api("/auth/password/change", { body: pw }); setMsg("Password changed. Other sessions have been signed out."); setPw({ current_password: "", new_password: "" }); } catch (ex) { setErr(ex); } };
  if (!user) return null;
  return (
    <>
      <PageHeader title="Profile & security" />
      {msg && <Alert kind="success" className="mb-3">{msg}</Alert>}<ErrorText error={err} />
      <div className="grid gap-4 md:grid-cols-2">
        <div className="card space-y-3 p-5"><h3 className="font-bold text-navy-800">Account</h3><KV items={[["Email", user.email], ["Roles", user.roles.map((r) => ROLE_LABELS[r] || r).join(", ")], ["Organisation", user.organization_name], ["Status", user.status], ["Permissions", `${user.permissions.length}`]]} /><Field label="Full name"><input className="input" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field><Field label="Designation"><input className="input" value={f.designation} onChange={(e) => setF({ ...f, designation: e.target.value })} /></Field><button className="btn-primary" onClick={save}>Save</button></div>
        <div className="card space-y-3 p-5"><h3 className="font-bold text-navy-800">Change password</h3><Field label="Current password"><input className="input" type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} /></Field><Field label="New password" hint="At least 10 characters with letters and digits. All refresh tokens are revoked on change."><input className="input" type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} /></Field><button className="btn-primary" onClick={change} disabled={!pw.current_password || pw.new_password.length < 10}>Change password</button><details className="text-xs text-slate-500"><summary className="cursor-pointer">Your permissions</summary><div className="mt-1 flex flex-wrap gap-1">{user.permissions.map((p) => <span key={p} className="badge bg-slate-100 text-slate-700">{p}</span>)}</div></details></div>
      </div>
      <p className="mt-4 text-xs text-slate-500">Session: access tokens expire automatically; refresh tokens rotate on every use and reuse is detected. Last update {fmtDate(new Date().toISOString())}.</p>
    </>
  );
}
