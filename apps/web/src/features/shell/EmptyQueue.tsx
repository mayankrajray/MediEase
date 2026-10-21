"use client";

import { ROLE_LABELS } from "@/features/auth/labels";
import { useSession } from "@/features/auth/SessionProvider";

import { useClinic } from "./ClinicGate";

/**
 * The empty dashboard (M1-P6): the clinic the person is working in, and an
 * honest empty state. The queue itself arrives with appointments. The time zone
 * line shows that the clinic's own setting is available for the screens that
 * will format times (apps/web/CLAUDE.md: clinic time, never the browser's).
 */
export function EmptyQueue() {
  const clinic = useClinic();
  const { clinic: choice } = useSession();
  const role = choice.kind === "active" ? ROLE_LABELS[choice.membership.role] : undefined;

  return (
    <section aria-labelledby="queue-heading" className="space-y-4">
      <h1 id="queue-heading" className="text-2xl font-bold tracking-tight">
        Today&apos;s queue
      </h1>
      <p className="text-lg">
        Nothing here yet. Today&apos;s queue will appear here once appointments are set up.
      </p>
      <dl className="grid max-w-md grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-slate-800">
        <dt className="font-medium">Clinic</dt>
        <dd>{clinic.name}</dd>
        {role !== undefined && (
          <>
            <dt className="font-medium">Your role</dt>
            <dd>{role}</dd>
          </>
        )}
        <dt className="font-medium">Clinic time zone</dt>
        <dd>{clinic.timezone}</dd>
      </dl>
    </section>
  );
}
