"use client";

import { Award, Lightbulb, Rocket, Users } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { SearchBar } from "@/components/catalogue";
import { DemoBadge, Empty, Hero, Loading, Pagination, Section, StatCard, StatusBadge, Tabs } from "@/components/ui";
import { fmtDate, fmtNum, titleCase } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks";

export default function InnovationPage() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q);
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const params = useMemo(() => ({ q: dq, status: status || undefined, page, page_size: 12 }), [dq, status, page]);
  const { data, loading } = useApi<any>("/challenges", params);
  const { data: overview } = useApi<any>("/innovation/overview");
  return (
    <>
      <Hero title="Innovation" accent="Portal" subtitle="Challenges, research calls, pilots and hackathons for land governance." crumbs={[{ label: "Home", href: "/" }, { label: "Innovation" }]} tag="Ideas for a Sustainable India" />
      <Section>
        <div className="mb-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Open challenges" value={fmtNum(overview?.open_challenges)} sub="Accepting submissions" color="orange" icon={<Lightbulb />} />
          <StatCard label="Submissions" value={fmtNum(overview?.submissions_total)} sub="Across all challenges" color="blue" icon={<Users />} />
          <StatCard label="Active pilots" value={fmtNum(overview?.pilots_active)} sub="Planned or running" color="brand" icon={<Rocket />} />
          <StatCard label="Themes" value={fmtNum(overview?.themes?.length)} sub="Problem areas" color="purple" icon={<Award />} />
        </div>
        <SearchBar value={q} onChange={setQ} placeholder="Search challenges…" />
        <div className="mt-3"><Tabs tabs={[{ id: "", label: "All" }, { id: "open", label: "Open" }, { id: "evaluation", label: "Under evaluation" }, { id: "pilot", label: "Pilot" }, { id: "completed", label: "Completed" }]} value={status} onChange={(v) => { setStatus(v); setPage(1); }} /></div>
        {loading ? <Loading /> : data?.items?.length ? (
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            {data.items.map((c: any) => (
              <div key={c.id} className="card flex flex-col p-5">
                <div className="flex flex-wrap items-center gap-2"><span className="badge bg-orange-100 text-orange-800">{titleCase(c.challenge_type)}</span><StatusBadge status={c.status} /><DemoBadge show={c.is_demo} /></div>
                <Link href={`/innovation/${c.id}`} className="mt-2 text-lg font-semibold text-navy-800 hover:text-brand-700">{c.title}</Link>
                <p className="mt-1 flex-1 text-sm text-slate-600">{c.summary}</p>
                <div className="mt-3 grid grid-cols-3 gap-2 text-xs text-slate-500"><div><div className="text-slate-400">Theme</div>{c.theme || "—"}</div><div><div className="text-slate-400">Closes</div>{fmtDate(c.closes_at)}</div><div><div className="text-slate-400">Submissions</div>{c.submission_count}</div></div>
                <Link href={`/innovation/${c.id}`} className="btn-primary mt-4">{c.is_open ? "View & apply" : "View details"}</Link>
              </div>
            ))}
          </div>
        ) : <div className="mt-4"><Empty title="No challenges found" /></div>}
        <Pagination page={page} pages={data?.pages || 1} onChange={setPage} />
      </Section>
    </>
  );
}
