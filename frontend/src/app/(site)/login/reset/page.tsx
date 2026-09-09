"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Alert, ErrorText, Field } from "@/components/ui";
import { api } from "@/lib/api";

function ResetInner() {
  const sp = useSearchParams();
  const [token, setToken] = useState(sp.get("token") || "");
  const [password, setPassword] = useState("");
  const [ok, setOk] = useState(false);
  const [err, setErr] = useState<any>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr(null);
    try { await api("/auth/password/reset", { body: { token, new_password: password }, auth: false }); setOk(true); } catch (ex) { setErr(ex); }
  };
  return (
    <div className="mx-auto max-w-md px-4 py-16"><div className="card p-8">
      <h1 className="text-2xl font-extrabold text-navy-800">Choose a new password</h1>
      {ok ? <Alert kind="success" className="mt-4">Password updated. <Link href="/login" className="underline">Sign in</Link>.</Alert> : (
        <form onSubmit={submit} className="mt-6 space-y-4"><Field label="Reset token"><input className="input" value={token} onChange={(e) => setToken(e.target.value)} required /></Field><Field label="New password" hint="At least 10 characters with letters and digits."><input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field><ErrorText error={err} /><button className="btn-primary w-full">Update password</button></form>
      )}
    </div></div>
  );
}

export default function ResetPage() {
  return <Suspense><ResetInner /></Suspense>;
}
