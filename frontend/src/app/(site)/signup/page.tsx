"use client";

import Link from "next/link";
import { useState } from "react";
import { Alert, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function SignupPage() {
  const { data: orgs } = useApi<any>("/organizations", { page_size: 100 });
  const [form, setForm] = useState({ email: "", password: "", full_name: "", designation: "", organization_id: "", phone: "" });
  const [res, setRes] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null);
    try { setRes(await api("/auth/register", { body: { ...form, organization_id: form.organization_id || null }, auth: false })); } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-lg px-4 py-16">
      <div className="card p-8">
        <h1 className="text-2xl font-extrabold text-navy-800">Create an account</h1>
        <p className="mt-1 text-sm text-slate-600">New accounts receive the Public User role. Administrators assign professional roles after verification.</p>
        {res ? <Alert kind="success" className="mt-6">{res.message}{res.detail?.status === "active" ? <> — you can <Link href="/login" className="underline">sign in now</Link>.</> : <> Check your email for the activation link.</>}{res.detail?.activation_token && <div className="mt-2 text-xs">Development mode: activation token <code className="break-all">{res.detail.activation_token}</code></div>}</Alert> : (
          <form onSubmit={submit} className="mt-6 grid gap-4">
            <Field label="Full name"><input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} required minLength={2} /></Field>
            <Field label="Email"><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></Field>
            <Field label="Password" hint="At least 10 characters, including letters and digits."><input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={10} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Designation"><input className="input" value={form.designation} onChange={(e) => setForm({ ...form, designation: e.target.value })} /></Field>
              <Field label="Organisation"><select className="input" value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: e.target.value })}><option value="">— none —</option>{(orgs?.items || []).map((o: any) => <option key={o.id} value={o.id}>{o.name}</option>)}</select></Field>
            </div>
            <ErrorText error={err} />
            <button className="btn-primary" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
            <p className="text-center text-sm text-slate-500">Already registered? <Link href="/login" className="text-brand-700">Sign in</Link></p>
          </form>
        )}
      </div>
    </div>
  );
}
