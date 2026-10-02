import type { PlatformStatus } from "./status";

const BADGE = {
  ok: "bg-green-100 text-green-900 ring-green-700",
  warn: "bg-amber-100 text-amber-900 ring-amber-700",
  bad: "bg-red-100 text-red-900 ring-red-700",
} as const;

function Badge({ tone, children }: { tone: keyof typeof BADGE; children: string }) {
  return (
    <span className={`rounded px-2 py-0.5 font-semibold ring-1 ring-inset ${BADGE[tone]}`}>
      {children}
    </span>
  );
}

/**
 * Presents a PlatformStatus. Every state shows "Ref: <request_id>" so staff can
 * quote it when reporting a problem (apps/web/CLAUDE.md). State is conveyed by
 * text, never by colour alone.
 */
export function StatusView({ status }: { status: PlatformStatus }) {
  const api = status.state === "down" ? "unreachable" : "healthy";
  const db = status.state === "healthy" ? "ready" : status.state === "degraded" ? "not ready" : "unknown";

  return (
    <section aria-labelledby="status-heading" className="mx-auto max-w-xl space-y-4 p-6">
      <h1 id="status-heading" className="text-2xl font-bold">
        System status
      </h1>

      {/* Spaces are real text so copy-paste and screen readers get
          "API: healthy · DB: ready · Ref: …", not "healthy·DB". */}
      <p role="status" className="text-lg leading-loose">
        API: <Badge tone={api === "healthy" ? "ok" : "bad"}>{api}</Badge>
        {" · "}
        DB: <Badge tone={db === "ready" ? "ok" : db === "not ready" ? "warn" : "bad"}>{db}</Badge>
        {" · "}
        Ref: <code className="font-mono text-sm">{status.requestId}</code>
      </p>

      {status.state !== "healthy" && (
        <div className="rounded border border-slate-300 p-4">
          <p>{status.message}</p>
          <p className="mt-1 text-sm text-slate-700">
            Code: <code className="font-mono">{status.code}</code>
          </p>
        </div>
      )}

      <p>
        <a href="/status" className="text-blue-800 underline">
          Check again
        </a>
      </p>
    </section>
  );
}
