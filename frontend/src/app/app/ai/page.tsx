"use client";

import { Bot, Send, ShieldCheck, User as UserIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/AppShell";
import { Alert, DemoBadge, ErrorText, Loading, ValueKind } from "@/components/ui";
import { api, fmtDate } from "@/lib/api";
import { useApi } from "@/lib/hooks";

type Msg = { role: "user" | "assistant"; content: string; citations?: any[]; confidence?: number; evidence_sufficient?: boolean; recommendation_id?: string; related?: any; provider?: string; limitations?: string };

export default function AiPage() {
  const { data: status } = useApi<any>("/ai/status");
  const { data: convs, reload: reloadConvs } = useApi<any>("/ai/conversations");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<any>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);
  const load = async (id: string) => { const c = await api(`/ai/conversations/${id}`); setConversationId(id); setMessages(c.messages.map((m: any) => ({ role: m.role, content: m.content, citations: m.citations, confidence: m.confidence, evidence_sufficient: m.evidence_sufficient, recommendation_id: m.recommendation_id }))); };
  const ask = async () => {
    if (q.trim().length < 3) return;
    const question = q; setQ(""); setBusy(true); setErr(null);
    setMessages((m) => [...m, { role: "user", content: question }]);
    try {
      const r = await api("/ai/ask", { body: { question, conversation_id: conversationId } });
      setConversationId(r.conversation_id);
      setMessages((m) => [...m, { role: "assistant", content: r.answer, citations: r.citations, confidence: r.confidence, evidence_sufficient: r.evidence_sufficient, recommendation_id: r.recommendation_id, related: r.related, provider: r.provider, limitations: r.limitations }]);
      reloadConvs();
    } catch (ex) { setErr(ex); } finally { setBusy(false); }
  };
  return (
    <>
      <PageHeader title="AI research assistant" subtitle="Answers are generated only from retrieved repository evidence, with citations, confidence and a full provenance trace." action={status && <span className="badge bg-slate-100 text-slate-700">{status.generation?.provider}{status.generation?.model ? ` · ${status.generation.model}` : ""} · {status.embeddings?.model}</span>} />
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <aside className="card h-fit p-4"><div className="flex items-center justify-between"><h3 className="font-bold text-navy-800">Conversations</h3><button className="text-xs text-brand-700" onClick={() => { setConversationId(null); setMessages([]); }}>New</button></div><ul className="mt-2 space-y-1 text-sm">{(convs?.items || []).map((c: any) => <li key={c.id}><button onClick={() => load(c.id)} className={`w-full truncate rounded px-2 py-1 text-left hover:bg-slate-50 ${c.id === conversationId ? "bg-brand-50 text-brand-800" : "text-slate-700"}`}>{c.title || "Untitled"}<span className="block text-[10px] text-slate-400">{fmtDate(c.updated_at)} · {c.message_count} msgs</span></button></li>)}{!convs?.items?.length && <li className="text-xs text-slate-500">No conversations yet.</li>}</ul></aside>
        <div className="flex min-h-[70vh] flex-col">
          {status?.generation?.provider === "local-extractive" && <Alert kind="info" className="mb-3">No LLM API key configured — the assistant is running in <b>extractive mode</b>: it quotes and cites retrieved passages verbatim and never generates unsupported text. Set <code>AI_PROVIDER=openai</code> and an API key for generative synthesis (still citation-constrained).</Alert>}
          <div className="card flex-1 space-y-4 overflow-y-auto p-4">
            {!messages.length && <div className="py-10 text-center text-sm text-slate-500"><Bot className="mx-auto mb-2 h-8 w-8 text-brand-600" />Ask about land records, watershed outcomes, wasteland reclamation, zoning, tenure… The assistant will refuse when the repository lacks evidence.</div>}
            {messages.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === "user" ? "justify-end" : ""}`}>
                {m.role === "assistant" && <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-600 text-white"><Bot className="h-4 w-4" /></div>}
                <div className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${m.role === "user" ? "bg-brand-600 text-white" : "bg-slate-50 text-slate-800"}`}>
                  <p className="whitespace-pre-wrap">{m.content}</p>
                  {m.role === "assistant" && (
                    <div className="mt-3 border-t border-slate-200 pt-2 text-xs">
                      <div className="flex flex-wrap items-center gap-2"><span className={`badge ${m.evidence_sufficient ? "bg-emerald-100 text-emerald-800" : "bg-red-100 text-red-700"}`}>{m.evidence_sufficient ? "Evidence sufficient" : "Insufficient evidence"}</span><span className="badge bg-blue-100 text-blue-800">Confidence {Math.round((m.confidence || 0) * 100)}%</span>{m.provider && <span className="badge bg-slate-100 text-slate-600">{m.provider}</span>}{m.recommendation_id && <Link href={`/app/evidence/${m.recommendation_id}`} className="badge bg-navy-800 text-white hover:bg-navy-900"><ShieldCheck className="mr-1 h-3 w-3" /> Evidence trace</Link>}</div>
                      {m.citations?.length ? <ol className="mt-2 space-y-1">{m.citations.map((c: any) => <li key={c.marker} className={c.cited_in_answer ? "" : "opacity-60"}><span className="font-semibold">[{c.marker}]</span> <Link href={`/app/repository/${c.document_id}`} className="text-brand-700 hover:underline">{c.title}</Link> <span className="text-slate-500">{c.locator}</span>{c.is_demo && <DemoBadge className="ml-1" />} {c.value_kind && <ValueKind kind={c.value_kind} />}<div className="text-slate-500">“{(c.excerpt || "").slice(0, 200)}{c.excerpt?.length > 200 ? "…" : ""}”</div></li>)}</ol> : null}
                      {m.related && (m.related.datasets?.length || m.related.policies?.length || m.related.maps?.length) ? <div className="mt-2 text-slate-600">Related: {m.related.datasets?.map((d: any) => <Link key={d.id} href={`/app/datasets/${d.id}`} className="mr-2 text-brand-700 hover:underline">{d.name}</Link>)}{m.related.policies?.map((p: any) => <span key={p.id} className="mr-2">{p.title}</span>)}{m.related.maps?.map((l: any) => <Link key={l.id} href={`/app/gis?layer=${l.id}`} className="mr-2 text-brand-700 hover:underline">{l.name}</Link>)}</div> : null}
                      {m.limitations && <div className="mt-1 text-slate-500">{m.limitations}</div>}
                    </div>
                  )}
                </div>
                {m.role === "user" && <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-slate-200"><UserIcon className="h-4 w-4 text-slate-600" /></div>}
              </div>
            ))}
            {busy && <Loading label="Retrieving evidence…" />}
            <div ref={bottom} />
          </div>
          <ErrorText error={err} />
          <form onSubmit={(e) => { e.preventDefault(); ask(); }} className="mt-3 flex gap-2"><input className="input flex-1" placeholder="Ask a question grounded in the repository…" value={q} onChange={(e) => setQ(e.target.value)} disabled={busy} /><button className="btn-primary" disabled={busy || q.trim().length < 3}><Send className="h-4 w-4" /> Ask</button></form>
          <p className="mt-2 text-[11px] text-slate-500">Decision-support output — not an official government position. Each answer is stored as a recommendation with its evidence items.</p>
        </div>
      </div>
    </>
  );
}
