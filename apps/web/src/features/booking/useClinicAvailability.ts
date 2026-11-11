"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiGet } from "@/lib/api/client";

import { isStale, STALE_MS, type Days } from "./availability";

export type ClinicAvailabilityState =
  | { readonly status: "loading" }
  | { readonly status: "failed" }
  /** `days` per doctor id; `null` for a doctor whose times could not be loaded this time. */
  | { readonly status: "ready"; readonly byDoctor: Readonly<Record<string, Days | null>>; readonly fetchedAt: number };

/**
 * Every doctor's offered days for the clinic page (M7d-P4): one call per doctor, in parallel (a
 * clinic has a handful). Fetched again when over a minute old, as `useAvailability`. When some
 * doctors fail the others still show; only when every call fails is it an error.
 */
export function useClinicAvailability(slug: string, doctorIds: readonly string[], viaDirectory: boolean): { state: ClinicAvailabilityState; refresh: () => void } {
  const key = `${slug}|${doctorIds.join(",")}|${viaDirectory ? "directory" : ""}`;
  const [answer, setAnswer] = useState<{ key: string; state: ClinicAvailabilityState } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const latest = useRef(answer);
  useEffect(() => {
    latest.current = answer;
  }, [answer]);

  useEffect(() => {
    let gone = false;
    const ids = key.split("|")[1]?.split(",").filter((id) => id !== "") ?? [];
    Promise.all(
      ids.map((id) =>
        apiGet("/api/v1/public/clinics/{slug}/availability", {
          pathParams: { slug },
          query: viaDirectory ? { doctor_id: id, via: "directory" } : { doctor_id: id },
        }).then(
          ({ data }) => [id, data.days] as const,
          () => [id, null] as const,
        ),
      ),
    ).then((pairs) => {
      if (gone) return;
      const byDoctor = Object.fromEntries(pairs);
      const anyLoaded = pairs.length === 0 || pairs.some(([, days]) => days !== null);
      setAnswer({ key, state: anyLoaded ? { status: "ready", byDoctor, fetchedAt: Date.now() } : { status: "failed" } });
    });
    return () => {
      gone = true;
    };
  }, [key, slug, viaDirectory, attempt]);

  useEffect(() => {
    const again = () => {
      const now = latest.current;
      if (document.visibilityState === "visible" && now?.key === key && now.state.status === "ready" && isStale(now.state.fetchedAt, Date.now())) setAttempt((n) => n + 1);
    };
    const timer = window.setInterval(again, STALE_MS);
    document.addEventListener("visibilitychange", again);
    window.addEventListener("focus", again);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", again);
      window.removeEventListener("focus", again);
    };
  }, [key]);

  const refresh = useCallback(() => {
    setAnswer((now) => (now !== null && now.state.status === "failed" ? null : now));
    setAttempt((n) => n + 1);
  }, []);

  return { state: answer === null || answer.key !== key ? { status: "loading" } : answer.state, refresh };
}
