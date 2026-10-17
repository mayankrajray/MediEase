/**
 * Polling a conditional GET (M3-P4; spec R12, decision D25).
 *
 * `startPolling` calls `load(etag)` at once and then every `intervalMs` (5 s for the queue). A
 * `notModified` answer keeps the data the caller already has; a new body is handed to `onData`
 * with its tag, which the next request sends back as `If-None-Match`. While the tab is hidden
 * nothing is requested; when it becomes visible again it polls at once. After an error it waits
 * `backoffMs` (30 s) before trying again, and `onError` is told; the next success clears it.
 * Requests never overlap: the next one is scheduled only after the previous one settles.
 */

import type { ConditionalResult } from "./client";

export const POLL_INTERVAL_MS = 5_000;
export const POLL_BACKOFF_MS = 30_000;

/** What polling needs from the page: whether it is hidden, and to hear when that changes. */
export interface PageVisibility {
  readonly hidden: boolean;
  addEventListener(type: "visibilitychange", listener: () => void): void;
  removeEventListener(type: "visibilitychange", listener: () => void): void;
}

export interface PollOptions<T> {
  readonly load: (etag: string | undefined, signal: AbortSignal) => Promise<ConditionalResult<T>>;
  readonly onData: (data: T) => void;
  readonly onError?: (error: unknown) => void;
  readonly intervalMs?: number;
  readonly backoffMs?: number;
  /** Injected in tests; defaults to the global document (absent on the server). */
  readonly visibility?: PageVisibility;
}

/** Starts polling; returns a function that stops it and cancels a request in flight. */
export function startPolling<T>(options: PollOptions<T>): () => void {
  const intervalMs = options.intervalMs ?? POLL_INTERVAL_MS;
  const backoffMs = options.backoffMs ?? POLL_BACKOFF_MS;
  const page = options.visibility ?? (typeof document === "undefined" ? undefined : document);

  let etag: string | undefined;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inFlight: AbortController | undefined;
  let stopped = false;

  const schedule = (delay: number) => {
    if (stopped || page?.hidden === true) return;
    timer = setTimeout(() => void tick(), delay);
  };

  const tick = async () => {
    timer = undefined;
    if (stopped || inFlight !== undefined) return;
    if (page?.hidden === true) return;
    const controller = new AbortController();
    inFlight = controller;
    let delay = intervalMs;
    try {
      const result = await options.load(etag, controller.signal);
      if (stopped) return;
      etag = result.etag;
      if (!result.notModified) options.onData(result.data);
    } catch (error) {
      if (stopped) return;
      delay = backoffMs;
      options.onError?.(error);
    } finally {
      inFlight = undefined;
    }
    schedule(delay);
  };

  const onVisibility = () => {
    if (page?.hidden === true) {
      if (timer !== undefined) clearTimeout(timer);
      timer = undefined;
    } else if (timer === undefined) {
      void tick();
    }
  };

  page?.addEventListener("visibilitychange", onVisibility);
  void tick();

  return () => {
    stopped = true;
    if (timer !== undefined) clearTimeout(timer);
    inFlight?.abort();
    page?.removeEventListener("visibilitychange", onVisibility);
  };
}
