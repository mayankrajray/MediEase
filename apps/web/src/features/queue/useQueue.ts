"use client";

/**
 * The day's queue, kept fresh (M3-P4; FR-QUE-03, spec R12, decision D25).
 *
 * Polls `GET /api/v1/queue` every 5 seconds with the last ETag, so an unchanged queue costs a
 * bodiless 304 and the screen keeps what it shows. A change made on another screen appears within
 * one interval (AC4). While the tab is hidden it does not poll. `error` is the last failure
 * until the next success; the last good queue stays on screen meanwhile. An expired access token
 * is refreshed once, like every other call. `refresh()` asks again at once (after an action on
 * this screen), keeping the queue on screen until the answer arrives.
 */

import { useCallback, useEffect, useState } from "react";

import { apiGetConditional, type GetResponse } from "@/lib/api/client";
import { withSessionRefresh } from "@/lib/auth/refresh";
import { startPolling } from "@/lib/api/poll";

export type Queue = GetResponse<"/api/v1/queue">;

export interface QueueFilter {
  readonly date?: string;
  readonly doctorId?: string;
  readonly clinicId?: string;
}

export interface QueueState {
  readonly queue: Queue | undefined;
  readonly error: unknown;
  readonly refresh: () => void;
}

export function useQueue(filter: QueueFilter): QueueState {
  const { date, doctorId, clinicId } = filter;
  // State belongs to one set of filters: under new filters the old queue is never shown.
  const key = [date, doctorId, clinicId].join("|");
  const [state, setState] = useState<{ readonly key: string; readonly queue: Queue | undefined; readonly error: unknown }>({
    key,
    queue: undefined,
    error: undefined,
  });
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(
    () =>
      startPolling<Queue>({
        load: (etag, signal) =>
          withSessionRefresh(() =>
            apiGetConditional("/api/v1/queue", etag, {
              query: { date, doctor_id: doctorId },
              ...(clinicId === undefined ? {} : { clinicId }),
              signal,
            }),
          ),
        onData: (queue) => setState({ key, queue, error: undefined }),
        onError: (error) =>
          setState((previous) => ({
            key,
            queue: previous.key === key ? previous.queue : undefined,
            error,
          })),
      }),
    [key, date, doctorId, clinicId, nonce],
  );

  return state.key === key
    ? { queue: state.queue, error: state.error, refresh }
    : { queue: undefined, error: undefined, refresh };
}
