// @vitest-environment node
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, type ConditionalResult } from "./client";
import { POLL_BACKOFF_MS, POLL_INTERVAL_MS, startPolling } from "./poll";

type Body = { readonly n: number };

function page(hidden = false) {
  const listeners = new Set<() => void>();
  return {
    hidden,
    addEventListener: (_: string, fn: () => void) => {
      listeners.add(fn);
    },
    removeEventListener: (_: string, fn: () => void) => {
      listeners.delete(fn);
    },
    setHidden(value: boolean) {
      this.hidden = value;
      listeners.forEach((fn) => fn());
    },
    listeners,
  };
}

const changed = (n: number, etag: string): ConditionalResult<Body> => ({
  notModified: false,
  data: { n },
  etag,
  requestId: "r",
});
const same = (etag: string): ConditionalResult<Body> => ({ notModified: true, etag, requestId: "r" });

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("startPolling (M3-P4, R12)", () => {
  it("FR-QUE-03: polls at once, then every 5 s, sending the last ETag back", async () => {
    const load = vi
      .fn<(etag: string | undefined, signal: AbortSignal) => Promise<ConditionalResult<Body>>>()
      .mockResolvedValueOnce(changed(1, '"a"'))
      .mockResolvedValueOnce(same('"a"'))
      .mockResolvedValueOnce(changed(2, '"b"'));
    const onData = vi.fn();
    const stop = startPolling({ load, onData, visibility: page() });

    await vi.advanceTimersByTimeAsync(0);
    expect(load).toHaveBeenNthCalledWith(1, undefined, expect.any(AbortSignal));
    expect(onData).toHaveBeenLastCalledWith({ n: 1 });

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(load).toHaveBeenNthCalledWith(2, '"a"', expect.any(AbortSignal));
    expect(onData).toHaveBeenCalledTimes(1); // a 304 keeps what the screen has

    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(load).toHaveBeenNthCalledWith(3, '"a"', expect.any(AbortSignal));
    expect(onData).toHaveBeenLastCalledWith({ n: 2 });
    stop();
  });

  it("D25: does not poll while the tab is hidden and polls at once when it returns", async () => {
    const load = vi.fn().mockResolvedValue(same('"a"'));
    const tab = page();
    const stop = startPolling<Body>({ load, onData: vi.fn(), visibility: tab });
    await vi.advanceTimersByTimeAsync(0);
    expect(load).toHaveBeenCalledTimes(1);

    tab.setHidden(true);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 4);
    expect(load).toHaveBeenCalledTimes(1);

    tab.setHidden(false);
    await vi.advanceTimersByTimeAsync(0);
    expect(load).toHaveBeenCalledTimes(2);
    stop();
  });

  it("D25: backs off to 30 s after an error and reports it, then recovers", async () => {
    const failure = new ApiError("WEB_API_UNREACHABLE", "down", 0, "r");
    const load = vi
      .fn()
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce(changed(3, '"c"'));
    const onData = vi.fn();
    const onError = vi.fn();
    const stop = startPolling<Body>({ load, onData, onError, visibility: page() });

    await vi.advanceTimersByTimeAsync(0);
    expect(onError).toHaveBeenCalledWith(failure);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(POLL_BACKOFF_MS - POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledTimes(2);
    expect(onData).toHaveBeenCalledWith({ n: 3 });
    stop();
  });

  it("stops cleanly: no more requests, the one in flight aborted, the listener removed", async () => {
    let seen: AbortSignal | undefined;
    const load = vi.fn((_etag: string | undefined, signal: AbortSignal) => {
      seen = signal;
      return new Promise<ConditionalResult<Body>>(() => undefined);
    });
    const tab = page();
    const stop = startPolling<Body>({ load, onData: vi.fn(), visibility: tab });
    await vi.advanceTimersByTimeAsync(0);
    stop();
    expect(seen?.aborted).toBe(true);
    expect(tab.listeners.size).toBe(0);
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    expect(load).toHaveBeenCalledTimes(1);
  });

  it("never overlaps requests when one is slower than the interval", async () => {
    let resolve: ((r: ConditionalResult<Body>) => void) | undefined;
    const load = vi.fn(
      () =>
        new Promise<ConditionalResult<Body>>((r) => {
          resolve = r;
        }),
    );
    const stop = startPolling<Body>({ load, onData: vi.fn(), visibility: page() });
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS * 3);
    expect(load).toHaveBeenCalledTimes(1);
    resolve?.(same('"a"'));
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledTimes(2);
    stop();
  });
});

describe("startPolling from server-rendered data (M6b-P6, R72)", () => {
  it("with an initial tag, waits one interval and sends that tag first", async () => {
    const load = vi.fn<(etag: string | undefined, signal: AbortSignal) => Promise<ConditionalResult<Body>>>().mockResolvedValue(same('"s"'));
    const stop = startPolling<Body>({ load, onData: vi.fn(), initialEtag: '"s"', visibility: page() });

    await vi.advanceTimersByTimeAsync(0);
    expect(load).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS);
    expect(load).toHaveBeenCalledWith('"s"', expect.any(AbortSignal));
    stop();
  });
});
