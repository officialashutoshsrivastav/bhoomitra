"use client";

import { useState } from "react";
import { Alert, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";

export default function ForgotPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<any>(null);
  const [err, setErr] = useState<any>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { setSent(await api("/auth/password/forgot", { body: { email }, auth: false })); } catch (ex) { setErr(ex); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-16"><div className="card p-8">
      <h1 className="text-2xl font-extrabold text-navy-800">Reset your password</h1>
      {sent ? <Alert kind="success" className="mt-4">{sent.message}{sent.detail?.reset_token && <div className="mt-2 text-xs">Development mode token: <code className="break-all">{sent.detail.reset_token}</code> — use it at <a className="underline" href={`/login/reset?token=${sent.detail.reset_token}`}>/login/reset</a>.</div>}</Alert> : (
        <form onSubmit={submit} className="mt-6 space-y-4"><Field label="Email"><input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field><ErrorText error={err} /><button className="btn-primary w-full">Send reset link</button></form>
      )}
    </div></div>
  );
}
