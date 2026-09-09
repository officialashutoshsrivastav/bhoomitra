"use client";

import { AlertTriangle, RotateCcw, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";

/**
 * Without this file Next.js renders its bare "Application error: a client-side
 * exception has occurred", which tells you nothing. This boundary catches the
 * throw, keeps the rest of the shell usable, and shows the actual message and
 * digest so the failure can be traced.
 */
export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Also goes to the browser console, and to the server log via the digest.
    console.error("Page error:", error);
  }, [error]);

  return (
    <div className="mx-auto max-w-2xl py-10">
      <div className="card p-6 sm:p-8">
        <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-red-200 bg-red-50 text-red-600">
          <AlertTriangle className="h-5 w-5" aria-hidden />
        </div>

        <h1 className="font-display text-xl font-bold text-navy-800 sm:text-2xl">This page could not be displayed</h1>
        <p className="prose-body mt-2 text-sm">
          Something in the page threw an error while rendering. Your data is unaffected — nothing was saved or changed.
        </p>

        <div className="mt-5 rounded-lg border border-paper-200 bg-paper-50 p-4">
          <div className="text-xs font-semibold tracking-wide text-slate-500">ERROR</div>
          <p className="mt-1 break-words font-mono text-[13px] leading-relaxed text-red-800">
            {error?.message || "No message was provided by the error."}
          </p>
          {error?.digest && (
            <>
              <div className="mt-3 text-xs font-semibold tracking-wide text-slate-500">DIGEST</div>
              <p className="mt-1 font-mono text-[13px] text-slate-700">{error.digest}</p>
            </>
          )}
        </div>

        <p className="mt-3 text-xs text-slate-500">
          Open the browser console for the full stack trace.
          {error?.digest && (
            <span className="ml-1">
              On the server, search the logs for the digest:
              <span className="ml-1 font-mono">docker compose logs frontend | grep {error.digest}</span>
            </span>
          )}
        </p>

        <div className="mt-6 flex flex-wrap gap-3">
          <button onClick={reset} className="btn-primary">
            <RotateCcw className="h-4 w-4" aria-hidden /> Try again
          </button>
          <Link href="/app" className="btn-secondary">
            <ArrowLeft className="h-4 w-4" aria-hidden /> Back to dashboard
          </Link>
        </div>
      </div>
    </div>
  );
}
