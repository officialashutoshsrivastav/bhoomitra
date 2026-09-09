"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, ErrorText, Field } from "@/components/ui";
import { useAuth } from "@/lib/auth";

function LoginInner() {
  const { login } = useAuth();
  const router = useRouter();
  const sp = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await login(email, password);
      router.push(sp.get("next") || "/app");
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <div className="card p-8">
        <h1 className="text-2xl font-extrabold text-navy-800">Sign in</h1>
        <p className="mt-1 text-sm text-slate-600">Access dashboards, the AI assistant, GIS tools and workspaces.</p>
        <form onSubmit={submit} className="mt-6 space-y-4">
          <Field label="Email"><input className="input" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label="Password"><input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <ErrorText error={err} />
          <button className="btn-primary w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <div className="mt-4 flex justify-between text-sm"><Link href="/signup" className="text-brand-700">Create an account</Link><Link href="/login/forgot" className="text-slate-500">Forgot password?</Link></div>
        <Alert kind="info" className="mt-6"><b>Demo accounts</b> (password <code>Demo@Bhoomitra2026</code>): policy.maker@, researcher@, gis.analyst@, data.analyst@, project.manager@, evaluator@ … <code>@demo.bhoomitra.in</code>. Only available when demo data is seeded.</Alert>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginInner /></Suspense>;
}
