"use client";

/**
 * Today's counts, kept fresh (M6-P1, decision 5A).
 *
 * Polls `GET /api/v1/dashboard/today` every 5 seconds with the last ETag, the queue's rhythm
 * (`lib/api/poll.ts`): an unchanged day costs a bodiless 304, a hidden tab does not poll, and
 * after a failure the last good numbers stay on screen with the error beside them. `refresh()`
 * asks again at once (Try again).
 */

import { useCallback, useEffect, useState } from "react";

import { apiGetConditional, type GetResponse } from "@/lib/api/client";
import { startPolling } from "@/lib/api/poll";
import { withSessionRefresh } from "@/lib/auth/refresh";

export type Today = GetResponse<"/api/v1/dashboard/today">;

export interface TodayState {
  readonly today: Today | undefined;
  readonly error: unknown;
  readonly refresh: () => void;
}

export function useToday(clinicId: string | undefined, view?: "doctor"): TodayState {
  const [state, setState] = useState<{ readonly key: string; readonly today: Today | undefined; readonly error: unknown }>({
    key: `${clinicId ?? ""}:${view ?? ""}`,
    today: undefined,
    error: undefined,
  });
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  // M6a-P6: the practising owner's Doctor view is its own answer, never mixed with the clinic's.
  const key = `${clinicId ?? ""}:${view ?? ""}`;

  useEffect(
    () =>
      startPolling<Today>({
        load: (etag, signal) =>
          withSessionRefresh(() =>
            apiGetConditional("/api/v1/dashboard/today", etag, {
              ...(clinicId === undefined ? {} : { clinicId }),
              ...(view === undefined ? {} : { query: { view } }),
              signal,
            }),
          ),
        onData: (today) => setState({ key, today, error: undefined }),
        onError: (error) =>
          setState((previous) => ({ key, today: previous.key === key ? previous.today : undefined, error })),
      }),
    [key, clinicId, view, nonce],
  );

  // Another clinic's numbers are never shown under this one, even for one render.
  return state.key === key
    ? { today: state.today, error: state.error, refresh }
    : { today: undefined, error: undefined, refresh };
}
