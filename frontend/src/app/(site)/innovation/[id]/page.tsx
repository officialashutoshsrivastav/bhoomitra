"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Alert, DemoBadge, ErrorText, Field, Hero, KV, Loading, Section, StatusBadge } from "@/components/ui";
import { api, fmtDate, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

export default function ChallengePage() {
  const { id } = useParams<{ id: string }>();
  const { user, can } = useAuth();
  const { data: c, loading, error } = useApi<any>(`/challenges/${id}`);
  const [form, setForm] = useState({ title: "", abstract: "", team_name: "", contact_email: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const [done, setDone] = useState<any>(null);
  if (loading) return <Loading />;
  if (error || !c) return <Section><Alert kind="error">Challenge not found.</Alert></Section>;
  const apply = async () => {
    setBusy(true); setErr(null);
    try {
      const s = await api(`/challenges/${id}/submissions`, { body: form });
      await api(`/submissions/${s.id}/submit`, { body: {} });
      setDone(s);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  };
  return (
    <>
      <Hero title={c.title} crumbs={[{ label: "Home", href: "/" }, { label: "Innovation", href: "/innovation" }, { label: c.title.slice(0, 40) }]} />
      <Section>
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="space-y-4 lg:col-span-2">
            <div className="card p-5">
              <div className="flex flex-wrap items-center gap-2"><span className="badge bg-orange-100 text-orange-800">{titleCase(c.challenge_type)}</span><StatusBadge status={c.status} /><DemoBadge show={c.is_demo} /></div>
              <p className="mt-3 text-slate-700">{c.description || c.summary}</p>
              {c.eligibility && <p className="mt-3 text-sm text-slate-600"><b>Eligibility:</b> {c.eligibility}</p>}
              {c.prize_or_grant && <p className="mt-1 text-sm text-slate-600"><b>Prize / grant:</b> {c.prize_or_grant}</p>}
            </div>
            <div className="card p-5">
              <h2 className="font-bold text-navy-800">Evaluation criteria</h2>
              <table className="table mt-2"><thead><tr><th>Criterion</th><th>Weight</th><th>Max score</th></tr></thead><tbody>{(c.evaluation_criteria || []).map((cr: any) => <tr key={cr.code}><td>{cr.label}</td><td>{Math.round((cr.weight || 0) * 100)}%</td><td>{cr.max}</td></tr>)}</tbody></table>
            </div>
            {c.is_open && (
              <div className="card p-5">
                <h2 className="font-bold text-navy-800">Apply</h2>
                {!user ? <p className="mt-2 text-sm text-slate-600"><Link href="/login" className="text-brand-700 underline">Log in</Link> or <Link href="/signup" className="text-brand-700 underline">create an account</Link> to submit a proposal.</p> : !can("innovation.submit") ? <Alert kind="warn" className="mt-2">Your role does not include submission rights. Contact the administrator.</Alert> : done ? <Alert kind="success" className="mt-2">Submission received (status: {done.status}). Track it in <Link href="/app/innovation" className="underline">your dashboard</Link>.</Alert> : (
                  <div className="mt-3 grid gap-3">
                    <Field label="Proposal title"><input className="input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
                    <Field label="Abstract"><textarea className="input" rows={5} value={form.abstract} onChange={(e) => setForm({ ...form, abstract: e.target.value })} /></Field>
                    <div className="grid gap-3 sm:grid-cols-2"><Field label="Team / organisation"><input className="input" value={form.team_name} onChange={(e) => setForm({ ...form, team_name: e.target.value })} /></Field><Field label="Contact email"><input className="input" value={form.contact_email} onChange={(e) => setForm({ ...form, contact_email: e.target.value })} /></Field></div>
                    <ErrorText error={err} />
                    <button className="btn-primary w-fit" disabled={busy || form.title.length < 3 || !form.abstract} onClick={apply}>{busy ? "Submitting…" : "Submit proposal"}</button>
                    <p className="text-xs text-slate-500">Attachments can be added from the dashboard before final submission if you save as draft via the app.</p>
                  </div>
                )}
              </div>
            )}
          </div>
          <aside className="card h-fit p-5">
            <KV items={[["Theme", c.theme], ["Opens", fmtDate(c.opens_at)], ["Closes", fmtDate(c.closes_at)], ["Submissions", c.submission_count], ["Status", titleCase(c.status)]]} />
          </aside>
        </div>
      </Section>
    </>
  );
}
