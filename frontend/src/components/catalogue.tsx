"use client";

import { Calendar, Download, Eye, FileText, Filter, Search, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import React, { useState } from "react";
import clsx from "clsx";
import { DemoBadge, StatusBadge } from "./ui";
import { Collapse } from "./motion";
import { downloadUrl, fmtDate, titleCase } from "@/lib/api";

export type FacetGroup = { key: string; label: string; options: { value: string; count?: number; label?: string }[] };

/**
 * Filters. On a phone this collapses behind a button that reports how many are
 * active — previously the whole sidebar sat above the results, so a visitor had
 * to scroll past every facet before seeing a single record.
 */
export function FilterSidebar({ groups, values, onChange, onReset }: { groups: FacetGroup[]; values: Record<string, string>; onChange: (key: string, value: string) => void; onReset: () => void }) {
  const [open, setOpen] = useState(false);
  const active = Object.values(values).filter(Boolean).length;

  const body = (
    <>
      {groups.map((g) => (
        <div key={g.key} className="border-b border-paper-200 py-3 last:border-0">
          <h4 className="mb-2 text-xs font-semibold tracking-wide text-slate-600">{g.label}</h4>
          <ul className="space-y-0.5">
            {g.options.slice(0, 10).map((o) => {
              const on = values[g.key] === o.value;
              return (
                <li key={o.value}>
                  <button
                    onClick={() => onChange(g.key, on ? "" : o.value)}
                    aria-pressed={on}
                    className={clsx(
                      "flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm transition-colors duration-tap",
                      on ? "bg-brand-50 font-medium text-brand-800" : "text-slate-700 hover:bg-paper-100"
                    )}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full transition-colors duration-tap", on ? "bg-brand-600" : "bg-paper-300")} aria-hidden />
                      <span className="truncate capitalize">{o.label || titleCase(o.value)}</span>
                    </span>
                    {o.count !== undefined && <span className="shrink-0 tabular-nums text-xs text-slate-400">{o.count}</span>}
                  </button>
                </li>
              );
            })}
            {g.options.length === 0 && <li className="px-2 text-xs text-slate-400">No values</li>}
          </ul>
        </div>
      ))}
    </>
  );

  return (
    <>
      {/* Mobile trigger */}
      <div className="lg:hidden">
        <button onClick={() => setOpen((o) => !o)} className="btn-secondary w-full justify-between" aria-expanded={open}>
          <span className="flex items-center gap-2"><SlidersHorizontal className="h-4 w-4" aria-hidden /> Filters</span>
          {active > 0 && <span className="badge bg-brand-600 text-white">{active}</span>}
        </button>
        <Collapse open={open}>
          <div className="card mt-2 p-4">
            {body}
            {active > 0 && <button onClick={() => { onReset(); setOpen(false); }} className="btn-ghost btn-sm mt-3 w-full">Clear all filters</button>}
          </div>
        </Collapse>
      </div>

      {/* Desktop sidebar */}
      <aside className="card sticky top-24 hidden h-fit p-4 lg:block">
        <div className="mb-1 flex items-center justify-between border-b border-paper-200 pb-2.5">
          <h3 className="flex items-center gap-2 font-display text-sm font-bold text-navy-800"><Filter className="h-4 w-4 text-brand-600" aria-hidden /> Filters</h3>
          {active > 0 && (
            <button onClick={onReset} className="flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-800">
              <X className="h-3 w-3" aria-hidden /> Clear {active}
            </button>
          )}
        </div>
        {body}
      </aside>
    </>
  );
}

export function SearchBar({ value, onChange, onSubmit, placeholder }: { value: string; onChange: (v: string) => void; onSubmit?: () => void; placeholder?: string }) {
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit?.(); }}
      role="search"
      className="flex overflow-hidden rounded-xl border border-paper-300 bg-white shadow-card transition-shadow duration-state focus-within:border-brand-500 focus-within:shadow-lift"
    >
      <Search className="ml-3.5 mt-3.5 h-5 w-5 shrink-0 self-start text-slate-400" aria-hidden />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="min-w-0 flex-1 bg-transparent px-3 py-3 text-sm outline-none placeholder:text-slate-400"
        placeholder={placeholder || "Search…"}
        aria-label="Search"
      />
      <button className="shrink-0 bg-brand-600 px-4 text-sm font-semibold text-white transition-colors duration-state hover:bg-brand-700 sm:px-6">
        <span className="hidden sm:inline">Search</span>
        <Search className="h-4 w-4 sm:hidden" aria-hidden />
      </button>
    </form>
  );
}

const TYPE_COLORS: Record<string, string> = {
  research_paper: "border-blue-200 bg-blue-50 text-blue-800",
  policy_paper: "border-purple-200 bg-purple-50 text-purple-800",
  government_report: "border-emerald-200 bg-emerald-50 text-emerald-800",
  legal_document: "border-amber-200 bg-amber-50 text-amber-800",
  case_study: "border-pink-200 bg-pink-50 text-pink-800",
  working_paper: "border-sky-200 bg-sky-50 text-sky-800",
  technical_report: "border-indigo-200 bg-indigo-50 text-indigo-800",
  guideline: "border-teal-200 bg-teal-50 text-teal-800",
  framework: "border-cyan-200 bg-cyan-50 text-cyan-800",
  act_rule: "border-orange-200 bg-orange-50 text-orange-800",
  scheme: "border-lime-200 bg-lime-50 text-lime-800",
  policy_brief: "border-fuchsia-200 bg-fuchsia-50 text-fuchsia-800",
};

export function DocumentCard({ d, href }: { d: any; href?: string }) {
  const target = href || `/documents/${d.id}`;
  return (
    <article className="card flex flex-col p-4 transition-shadow duration-state hover:shadow-lift sm:p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={clsx("badge border", TYPE_COLORS[d.document_type] || "border-slate-200 bg-slate-50 text-slate-700")}>{titleCase(d.document_type)}</span>
        <DemoBadge show={d.is_demo} />
        {d.status && d.status !== "published" && <StatusBadge status={d.status} />}
      </div>

      <h3 className="mt-3">
        <Link href={target} className="line-clamp-2 font-display text-base font-semibold leading-snug text-navy-800 transition-colors duration-state hover:text-brand-700">
          {d.title}
        </Link>
      </h3>

      <p className="mt-1.5 line-clamp-2 flex-1 text-sm leading-relaxed text-slate-600">{d.description || d.abstract || "—"}</p>

      <div className="meta mt-3 flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className="flex items-center gap-1"><Calendar className="h-3.5 w-3.5" aria-hidden />{fmtDate(d.publication_date)}</span>
        {d.geography && <span className="truncate">{d.geography}</span>}
        {d.view_count !== undefined && <span className="flex items-center gap-1"><Eye className="h-3.5 w-3.5" aria-hidden />{d.view_count}</span>}
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 border-t border-paper-200 pt-3">
        <Link href={target} className="btn-secondary btn-sm">View details</Link>
        {d.current_version_id ? (
          <a href={downloadUrl(`/documents/${d.id}/download`)} className="btn-primary btn-sm"><Download className="h-3.5 w-3.5" aria-hidden /> Download</a>
        ) : (
          <span className="btn btn-sm cursor-default justify-center text-slate-400"><FileText className="h-3.5 w-3.5" aria-hidden /> No file</span>
        )}
      </div>
    </article>
  );
}
