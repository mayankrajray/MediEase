"use client";

import { useSyncExternalStore } from "react";

import { formatDuration, minutesBetween } from "@/lib/format/time";

const MINUTE_MS = 60_000;

function subscribe(onChange: () => void): () => void {
  const timer = setInterval(onChange, 30_000);
  return () => clearInterval(timer);
}

/** The current time, moving on once a minute. Server render and first paint read 0. */
function useMinute(): number {
  return useSyncExternalStore(
    subscribe,
    () => Math.floor(Date.now() / MINUTE_MS) * MINUTE_MS,
    () => 0,
  );
}

/**
 * How long onboarding has taken (goal G4: under an hour). The start is the
 * server's `started_at` from the onboarding checklist; only "now" is the
 * browser's.
 */
export function ElapsedTimer({ startedAt }: { startedAt: string }) {
  const now = useMinute();
  const minutes = now === 0 ? undefined : minutesBetween(startedAt, now);

  return (
    <p className="text-slate-800">
      Onboarding time:{" "}
      <strong>{minutes === undefined ? "…" : formatDuration(minutes)}</strong>
      {minutes !== undefined && minutes >= 60 && " (over the one-hour goal)"}
    </p>
  );
}
