"use client";

/**
 * The day's queue, kept fresh (M3-P4; FR-QUE-03, spec R12, decision D25).
 *
 * Polls `GET /api/v1/queue` every 5 seconds with the last ETag, so an unchanged queue costs a
 * bodiless 304 and the screen keeps what it shows. A change made on another screen appears within
 * one interval (AC4). While the tab is hidden it does not poll. `error` is the last failure
 * until the next success; the last good queue stays on screen meanwhile. The queue board (P5)
 * builds on this.
 */

import { useEffect, useState } from "react";

import { apiGetConditional, type GetResponse } from "@/lib/api/client";
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
}

export function useQueue(filter: QueueFilter): QueueState {
  const { date, doctorId, clinicId } = filter;
  // State belongs to one set of filters: under new filters the old queue is never shown.
  const key = [date, doctorId, clinicId].join("|");
  const [state, setState] = useState<QueueState & { readonly key: string }>({
    key,
    queue: undefined,
    error: undefined,
  });

  useEffect(
    () =>
      startPolling<Queue>({
        load: (etag, signal) =>
          apiGetConditional("/api/v1/queue", etag, {
            query: { date, doctor_id: doctorId },
            ...(clinicId === undefined ? {} : { clinicId }),
            signal,
          }),
        onData: (queue) => setState({ key, queue, error: undefined }),
        onError: (error) =>
          setState((previous) => ({
            key,
            queue: previous.key === key ? previous.queue : undefined,
            error,
          })),
      }),
    [key, date, doctorId, clinicId],
  );

  return state.key === key
    ? { queue: state.queue, error: state.error }
    : { queue: undefined, error: undefined };
}