"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { DemoBadge, Empty, ErrorText, Field, Loading, StatusBadge, Tabs } from "@/components/ui";
import { api, fmtDate, titleCase } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/hooks";

export default function AppInnovationPage() {
  const { can } = useAuth();
  const [tab, setTab] = useState("challenges");
  const { data: challenges, reload } = useApi<any>("/challenges", { page_size: 50 });
  const { data: mine, reload: reloadMine } = useApi<any>("/submissions/mine");
  const { data: pilots } = useApi<any>(can("innovation.manage") || can("innovation.evaluate") ? "/innovation/pilots" : null);
  const [selected, setSelected] = useState<any>(null);
  const { data: subs, reload: reloadSubs } = useApi<any>(selected ? `/challenges/${selected.id}/submissions` : null, { page_size: 50 }, [selected?.id]);
  const [scores, setScores] = useState<Record<string, Record<string, number>>>({});
  const [err, setErr] = useState<any>(null);
  const [nc, setNc] = useState({ title: "", summary: "", theme: "", challenge_type: "innovation_challenge", closes_at: "" });
  const [showNew, setShowNew] = useState(false);
  const call = async (fn: () => Promise<any>, after?: () => void) => { setErr(null); try { await fn(); after?.(); } catch (ex) { setErr(ex); } };
  const evaluate = (s: any) => { const sc = scores[s.id] || {}; return call(() => api(`/submissions/${s.id}/evaluate`, { body: { scores: sc, recommendation: "consider" } }), reloadSubs); };
  return (
    <>
      <PageHeader title="Innovation portal" subtitle="Manage challenges, evaluate submissions with weighted criteria, shortlist and launch pilots." action={can("innovation.create", "innovation.manage") ? <button className="btn-primary" onClick={() => setShowNew((s) => !s)}><Plus className="h-4 w-4" /> New challenge</button> : null} />
      <ErrorText error={err} />
      {showNew && <div className="card mb-4 grid gap-3 p-4 md:grid-cols-5"><Field label="Title"><input className="input" value={nc.title} onChange={(e) => setNc({ ...nc, title: e.target.value })} /></Field><Field label="Theme"><input className="input" value={nc.theme} onChange={(e) => setNc({ ...nc, theme: e.target.value })} /></Field><Field label="Type"><select className="input" value={nc.challenge_type} onChange={(e) => setNc({ ...nc, challenge_type: e.target.value })}>{["innovation_challenge", "research_call", "pilot_programme", "hackathon", "expression_of_interest"].map((t) => <option key={t} value={t}>{titleCase(t)}</option>)}</select></Field><Field label="Closes"><input className="input" type="date" value={nc.closes_at} onChange={(e) => setNc({ ...nc, closes_at: e.target.value })} /></Field><div className="flex items-end"><button className="btn-primary" disabled={nc.title.length < 3} onClick={() => call(() => api("/challenges", { body: { ...nc, closes_at: nc.closes_at ? `${nc.closes_at}T23:59:59Z` : undefined } }), () => { setShowNew(false); reload(); })}>Create draft</button></div><div className="md:col-span-5"><Field label="Summary"><textarea className="input" rows={2} value={nc.summary} onChange={(e) => setNc({ ...nc, summary: e.target.value })} /></Field></div></div>}
      <Tabs tabs={[{ id: "challenges", label: "Challenges", count: challenges?.total }, { id: "mine", label: "My submissions", count: mine?.items?.length }, ...(pilots ? [{ id: "pilots", label: "Pilots", count: pilots.items?.length }] : [])]} value={tab} onChange={setTab} />
      {tab === "challenges" && (
        <div className="mt-4 grid gap-4 lg:grid-cols-[360px_1fr]">
          <ul className="space-y-2">{(challenges?.items || []).map((c: any) => <li key={c.id}><button onClick={() => setSelected(c)} className={`card w-full p-3 text-left hover:shadow ${selected?.id === c.id ? "ring-2 ring-brand-400" : ""}`}><div className="flex items-center gap-2"><StatusBadge status={c.status} /><DemoBadge show={c.is_demo} /></div><div className="mt-1 font-semibold text-navy-800">{c.title}</div><div className="text-xs text-slate-500">{titleCase(c.challenge_type)} · {c.submission_count} submissions · closes {fmtDate(c.closes_at)}</div></button></li>)}</ul>
          <div className="card p-4">
            {!selected ? <p className="text-sm text-slate-500">Select a challenge.</p> : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2"><div><h2 className="font-bold text-navy-800">{selected.title}</h2><p className="text-xs text-slate-500">{selected.summary}</p></div><div className="flex flex-wrap gap-2">{can("innovation.manage") && selected.allowed_transitions?.map((t: string) => <button key={t} className="btn-secondary" onClick={() => call(() => api(`/challenges/${selected.id}/transition`, { body: { status: t } }), async () => { const c = await api(`/challenges/${selected.id}`); setSelected(c); reload(); })}>→ {titleCase(t)}</button>)}<Link href={`/innovation/${selected.id}`} className="btn-ghost">Public page</Link></div></div>
                <h3 className="mt-4 font-semibold text-navy-800">Submissions</h3>
                <ul className="mt-2 space-y-3">{(subs?.items || []).map((s: any) => (
                  <li key={s.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                    <div className="flex flex-wrap items-center gap-2"><StatusBadge status={s.status} /><b>{s.title}</b><span className="text-xs text-slate-500">{s.team_name || ""} · submitted {fmtDate(s.submitted_at)}</span>{s.average_score != null && <span className="badge bg-blue-100 text-blue-800">avg {s.average_score}</span>}</div>
                    <p className="mt-1 text-slate-700">{s.abstract}</p>
                    {s.attachments?.length > 0 && <div className="mt-1 text-xs text-slate-500">Attachments: {s.attachments.map((a: any) => a.file_name).join(", ")}</div>}
                    {can("innovation.evaluate") && ["submitted", "under_evaluation"].includes(s.status) && (
                      <div className="mt-2 flex flex-wrap items-end gap-2 rounded bg-slate-50 p-2">{(s.criteria || []).map((cr: any) => <label key={cr.code} className="text-xs"><span className="block text-slate-500">{cr.label} (≤{cr.max})</span><input type="number" min={0} max={cr.max} className="input w-20" value={scores[s.id]?.[cr.code] ?? ""} onChange={(e) => setScores({ ...scores, [s.id]: { ...(scores[s.id] || {}), [cr.code]: Number(e.target.value) } })} /></label>)}<button className="btn-primary" onClick={() => evaluate(s)}>Score</button></div>
                    )}
                    {s.evaluations?.length > 0 && <ul className="mt-2 text-xs text-slate-600">{s.evaluations.map((e: any) => <li key={e.id}>Evaluator {e.evaluator_id.slice(0, 8)} · weighted {e.weighted_score} · {e.recommendation}{e.comments ? ` · ${e.comments}` : ""}</li>)}</ul>}
                    {can("innovation.manage") && <div className="mt-2 flex flex-wrap gap-2">{["submitted", "under_evaluation"].includes(s.status) && <><button className="btn-secondary" onClick={() => call(() => api(`/submissions/${s.id}/decision`, { method: "POST", params: { decision: "shortlist" } }), reloadSubs)}>Shortlist</button><button className="btn-ghost" onClick={() => call(() => api(`/submissions/${s.id}/decision`, { method: "POST", params: { decision: "not_selected" } }), reloadSubs)}>Not selected</button></>}{s.status === "shortlisted" && <button className="btn-primary" onClick={() => call(() => api(`/submissions/${s.id}/pilots`, { body: { title: `Pilot: ${s.title}` } }), reloadSubs)}>Launch pilot</button>}</div>}
                  </li>
                ))}</ul>{subs && !subs.items?.length && <p className="mt-2 text-sm text-slate-500">No submissions visible.</p>}
              </>
            )}
          </div>
        </div>
      )}
      {tab === "mine" && <div className="mt-4 grid gap-3 md:grid-cols-2">{(mine?.items || []).map((s: any) => <div key={s.id} className="card p-4 text-sm"><div className="flex items-center gap-2"><StatusBadge status={s.status} />{s.average_score != null && <span className="badge bg-blue-100 text-blue-800">score {s.average_score}</span>}</div><div className="mt-1 font-semibold text-navy-800">{s.title}</div><p className="text-slate-600">{s.abstract}</p><div className="mt-2 text-xs text-slate-500">Submitted {fmtDate(s.submitted_at)}{s.decision_note ? ` · ${s.decision_note}` : ""}</div>{s.status === "draft" && <div className="mt-2 flex gap-2"><label className="btn-secondary cursor-pointer">Add attachment<input type="file" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (!file) return; const form = new FormData(); form.append("file", file); call(() => api(`/submissions/${s.id}/attachments`, { form }), reloadMine); }} /></label><button className="btn-primary" onClick={() => call(() => api(`/submissions/${s.id}/submit`, { body: {} }), reloadMine)}>Submit</button></div>}</div>)}{!mine?.items?.length && <Empty title="No submissions yet" hint="Apply to an open challenge from the public portal." />}</div>}
      {tab === "pilots" && <div className="card mt-4 overflow-x-auto"><table className="table"><thead><tr><th>Pilot</th><th>Status</th><th>Start</th><th>End</th><th>Budget</th><th>Outcome</th></tr></thead><tbody>{(pilots?.items || []).map((p: any) => <tr key={p.id}><td>{p.title} <DemoBadge show={p.is_demo} /></td><td>{can("innovation.manage") ? <select className="input w-auto" value={p.status} onChange={(e) => call(() => api(`/innovation/pilots/${p.id}`, { method: "PATCH", params: { status: e.target.value } }))}>{["planned", "active", "completed", "cancelled"].map((s) => <option key={s}>{s}</option>)}</select> : <StatusBadge status={p.status} />}</td><td>{p.start_date || "—"}</td><td>{p.end_date || "—"}</td><td>{p.budget ? `₹${p.budget.toLocaleString("en-IN")}` : "—"}</td><td className="text-xs">{p.outcomes || "—"}</td></tr>)}</tbody></table></div>}
    </>
  );
}
