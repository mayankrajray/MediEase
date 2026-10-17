import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import { POLL_INTERVAL_MS } from "@/lib/api/poll";

import { useQueue, type Queue } from "./useQueue";

const queue = (n: number): Queue => ({ on_date: `2026-10-${19 + n}`, sessions: [] });

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useQueue (M3-P4, FR-QUE-03)", () => {
  it("shows the queue, keeps it on 304 and on an error, and updates on a change", async () => {
    const failure = new client.ApiError("WEB_API_UNREACHABLE", "down", 0, "r");
    const get = vi
      .spyOn(client, "apiGetConditional")
      .mockResolvedValueOnce({ notModified: false, data: queue(0), etag: '"a"', requestId: "r" })
      .mockResolvedValueOnce({ notModified: true, etag: '"a"', requestId: "r" })
      .mockRejectedValueOnce(failure)
      .mockResolvedValueOnce({ notModified: false, data: queue(1), etag: '"b"', requestId: "r" });

    const { result } = renderHook(() => useQueue({ doctorId: "d-1" }));
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(result.current.queue?.on_date).toBe("2026-10-19");
    expect(get).toHaveBeenCalledWith("/api/v1/queue", undefined, expect.objectContaining({
      query: { date: undefined, doctor_id: "d-1" },
    }));

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(result.current.queue?.on_date).toBe("2026-10-19");

    await act(() => vi.advanceTimersByTimeAsync(POLL_INTERVAL_MS));
    expect(result.current.error).toBe(failure);
    expect(result.current.queue?.on_date).toBe("2026-10-19");

    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(result.current).toEqual({ queue: queue(1), error: undefined });
  });
});
