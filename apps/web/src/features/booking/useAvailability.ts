"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { apiGet } from "@/lib/api/client";

import { isStale, STALE_MS, type Days } from "./availability";

export type AvailabilityState =
  | { readonly status: "loading" }
  | { readonly status: "failed" }
  /** `refreshing`: a newer answer is on its way; the times shown are still the last answer's. */
  | { readonly status: "ready"; readonly days: Days; readonly fetchedAt: number; readonly refreshing: boolean };

export interface Availability {
  readonly state: AvailabilityState;
  /** Fetch again now; resolves with the new days, or `undefined` when the call failed. */
  readonly refresh: () => Promise<Days | undefined>;
}

/** One answer, tagged with the doctor it is for; any other tag means "still loading". */
type Answer = { readonly key: string; readonly days: Days | undefined; readonly fetchedAt: number };

/**
 * One doctor's offered days (M7d-P2, design §7): fetched on mount, again when the answer is older
 * than a minute (checked every minute while the page is visible, and when the patient comes back to
 * it), and whenever the screen asks (`refresh`: after a choice, and before the confirmation). A
 * failed refresh keeps the last answer on screen; only a first load that fails is an error.
 */
export function useAvailability(slug: string, doctorId: string | undefined, viaDirectory: boolean): Availability {
  const key = `${slug}|${doctorId ?? ""}|${viaDirectory ? "directory" : ""}`;
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [pending, setPending] = useState(0);
  const current = useRef<{ key: string; answer: Answer | null }>({ key, answer });
  useEffect(() => {
    current.current = { key, answer };
  }, [key, answer]);

  const fetchDays = useCallback(async (): Promise<Days> => {
    const { data } = await apiGet("/api/v1/public/clinics/{slug}/availability", {
      pathParams: { slug },
      query: viaDirectory && doctorId !== undefined ? { doctor_id: doctorId, via: "directory" } : { doctor_id: doctorId ?? "" },
    });
    return data.days;
  }, [slug, doctorId, viaDirectory]);

  // Keep the last good answer when a later call fails; a first failure is an error.
  const settle = useCallback((forKey: string, days: Days | undefined) => {
    setAnswer((now) => {
      if (days !== undefined) return { key: forKey, days, fetchedAt: Date.now() };
      return now !== null && now.key === forKey && now.days !== undefined ? now : { key: forKey, days: undefined, fetchedAt: Date.now() };
    });
  }, []);

  const refresh = useCallback(async (): Promise<Days | undefined> => {
    if (doctorId === undefined) return undefined;
    const forKey = key;
    setPending((n) => n + 1);
    try {
      const days = await fetchDays().catch(() => undefined);
      if (current.current.key === forKey) settle(forKey, days);
      return days;
    } finally {
      setPending((n) => Math.max(0, n - 1));
    }
  }, [doctorId, fetchDays, key, settle]);

  useEffect(() => {
    if (doctorId === undefined) return;
    let gone = false;
    fetchDays().then(
      (days) => {
        if (!gone) settle(key, days);
      },
      () => {
        if (!gone) settle(key, undefined);
      },
    );
    const again = () => {
      const now = current.current.answer;
      if (document.visibilityState === "visible" && now !== null && now.key === key && isStale(now.fetchedAt, Date.now())) void refresh();
    };
    const timer = window.setInterval(again, STALE_MS);
    document.addEventListener("visibilitychange", again);
    window.addEventListener("focus", again);
    return () => {
      gone = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", again);
      window.removeEventListener("focus", again);
    };
  }, [doctorId, fetchDays, key, refresh, settle]);

  const state: AvailabilityState =
    answer === null || answer.key !== key || (answer.days === undefined && pending > 0)
      ? { status: "loading" }
      : answer.days === undefined
        ? { status: "failed" }
        : { status: "ready", days: answer.days, fetchedAt: answer.fetchedAt, refreshing: pending > 0 };
  return { state, refresh };
}
