"use client";

import Link from "next/link";
import { PageHeader } from "@/components/AppShell";
import { Empty, Loading } from "@/components/ui";
import { api, fmtDate, titleCase } from "@/lib/api";
import { useApi } from "@/lib/hooks";

export default function NotificationsPage() {
  const { data, loading, reload } = useApi<any>("/notifications", { limit: 100 });
  const markAll = async () => { await api("/notifications/read", { body: {} }); reload(); };
  const markOne = async (id: string) => { await api("/notifications/read", { method: "POST", params: { notification_id: id }, body: {} }); reload(); };
  return (
    <>
      <PageHeader title="Notifications" subtitle={`${data?.unread ?? 0} unread`} action={<button className="btn-secondary" onClick={markAll} disabled={!data?.unread}>Mark all read</button>} />
      {loading ? <Loading /> : data?.items?.length ? (
        <ul className="card divide-y divide-slate-100">{data.items.map((n: any) => <li key={n.id} className={`flex items-start justify-between gap-3 p-3 text-sm ${n.read_at ? "opacity-70" : ""}`}><div><span className="badge bg-slate-100 text-slate-700">{titleCase(n.category)}</span><div className="mt-1 font-semibold text-navy-800">{n.title}</div>{n.body && <div className="text-slate-600">{n.body}</div>}<div className="mt-1 text-xs text-slate-500">{fmtDate(n.created_at)}{n.link && <> · <Link href={n.link} className="text-brand-700 underline">open</Link></>}</div></div>{!n.read_at && <button className="text-xs text-brand-700" onClick={() => markOne(n.id)}>mark read</button>}</li>)}</ul>
      ) : <Empty title="No notifications" />}
    </>
  );
}
