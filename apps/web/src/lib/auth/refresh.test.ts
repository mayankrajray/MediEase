import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, WEB_API_UNREACHABLE } from "@/lib/api/client";

import {
  AUTH_REFRESH_REUSED,
  AUTH_SESSION_EXPIRED,
  isSessionExpired,
  resetRefreshState,
  withSessionRefresh,
} from "./refresh";

const expired = () => new ApiError(AUTH_SESSION_EXPIRED, "Please sign in again", 401, "req-1");

/** A lock manager that runs requests one after another, like navigator.locks. */
function serialLocks() {
  let tail: Promise<unknown> = Promise.resolve();
  const request = vi.fn(async <T,>(_name: string, callback: () => Promise<T>): Promise<T> => {
    const run = tail.then(callback, callback);
    tail = run.catch(() => undefined);
    return run;
  });
  return { request } as unknown as Pick<LockManager, "request"> & { request: typeof request };
}

beforeEach(() => {
  resetRefreshState();
});

describe("withSessionRefresh", () => {
  it("passes a successful call through without refreshing", async () => {
    const refresh = vi.fn();
    const result = await withSessionRefresh(() => Promise.resolve("ok"), { refresh, locks: undefined });

    expect(result).toBe("ok");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("FR-AUTH-02: an expired access token is refreshed once and the call retried", async () => {
    const call = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("fresh");
    const probe = vi.fn().mockRejectedValue(expired());
    const refresh = vi.fn().mockResolvedValue(undefined);

    const result = await withSessionRefresh(call, { refresh, probe, locks: undefined });

    expect(result).toBe("fresh");
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(call).toHaveBeenCalledTimes(2);
  });

  it("test_fr_auth_02_concurrent_401s_refresh_once: five parallel 401s share one refresh", async () => {
    let refreshed = false;
    const refresh = vi.fn(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10));
      refreshed = true;
    });
    const probe = vi.fn(async () => {
      if (!refreshed) throw expired();
    });
    const makeCall = () =>
      vi.fn(async () => {
        if (!refreshed) throw expired();
        return "data";
      });

    const results = await Promise.all(
      Array.from({ length: 5 }, () =>
        withSessionRefresh(makeCall(), { refresh, probe, locks: serialLocks() }),
      ),
    );

    expect(results).toEqual(["data", "data", "data", "data", "data"]);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("a caller that gets its 401 just after another's refresh finished does not refresh again", async () => {
    let refreshed = false;
    const refresh = vi.fn(async () => {
      refreshed = true;
    });
    const probe = vi.fn(async () => {
      if (!refreshed) throw expired();
    });
    const stale = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("late");
    const first = withSessionRefresh(() => (refreshed ? Promise.resolve("early") : Promise.reject(expired())), {
      refresh,
      probe,
      locks: undefined,
    });
    await first;

    // The slow caller's first attempt happened before the refresh; its retry path runs after.
    const late = await withSessionRefresh(stale, { refresh, probe, locks: undefined });

    expect(late).toBe("late");
    expect(refresh).toHaveBeenCalledTimes(1); // the probe saw a working session and skipped it
  });

  it("FR-AUTH-02: another tab's refresh is noticed inside the lock, so this tab does not refresh", async () => {
    const call = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("ok");
    const probe = vi.fn().mockResolvedValue(undefined); // the session already works
    const refresh = vi.fn();

    const result = await withSessionRefresh(call, { refresh, probe, locks: serialLocks() });

    expect(result).toBe("ok");
    expect(probe).toHaveBeenCalledTimes(1);
    expect(refresh).not.toHaveBeenCalled();
  });

  it("takes the named Web Lock around the refresh", async () => {
    const locks = serialLocks();
    const call = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("ok");

    await withSessionRefresh(call, {
      refresh: vi.fn().mockResolvedValue(undefined),
      probe: vi.fn().mockRejectedValue(expired()),
      locks,
    });

    expect(locks.request).toHaveBeenCalledTimes(1);
    expect(locks.request.mock.calls[0]?.[0]).toBe("mediease-session-refresh");
  });

  it("works without Web Locks (tab-level guard only)", async () => {
    const call = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("ok");
    const refresh = vi.fn().mockResolvedValue(undefined);

    const result = await withSessionRefresh(call, {
      refresh,
      probe: vi.fn().mockRejectedValue(expired()),
      locks: undefined,
    });

    expect(result).toBe("ok");
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("FR-AUTH-02: a failed refresh is thrown as is and the call is not retried or looped", async () => {
    const reused = new ApiError(AUTH_REFRESH_REUSED, "Session ended for safety", 401, "req-2");
    const call = vi.fn().mockRejectedValue(expired());
    const refresh = vi.fn().mockRejectedValue(reused);

    await expect(
      withSessionRefresh(call, {
        refresh,
        probe: vi.fn().mockRejectedValue(expired()),
        locks: undefined,
      }),
    ).rejects.toBe(reused);

    expect(call).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("gives up after one retry: a second 401 is thrown, not refreshed again", async () => {
    const call = vi.fn().mockRejectedValue(expired());
    const refresh = vi.fn().mockResolvedValue(undefined);

    await expect(
      withSessionRefresh(call, {
        refresh,
        probe: vi.fn().mockRejectedValue(expired()),
        locks: undefined,
      }),
    ).rejects.toSatisfy(isSessionExpired);

    expect(call).toHaveBeenCalledTimes(2);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it("does not refresh for other errors", async () => {
    const forbidden = new ApiError("PERM_DENIED", "No access", 403, "req-3");
    const refresh = vi.fn();

    await expect(
      withSessionRefresh(() => Promise.reject(forbidden), { refresh, locks: undefined }),
    ).rejects.toBe(forbidden);

    expect(refresh).not.toHaveBeenCalled();
  });

  it("surfaces an unreachable API during the probe instead of refreshing blindly", async () => {
    const down = new ApiError(WEB_API_UNREACHABLE, "The API could not be reached.", 0, "req-4");
    const refresh = vi.fn();

    await expect(
      withSessionRefresh(() => Promise.reject(expired()), {
        refresh,
        probe: vi.fn().mockRejectedValue(down),
        locks: undefined,
      }),
    ).rejects.toBe(down);

    expect(refresh).not.toHaveBeenCalled();
  });

  it("a later expiry refreshes again (the shared refresh is forgotten once it settles)", async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const deps = { refresh, probe: vi.fn().mockRejectedValue(expired()), locks: undefined };

    for (let round = 0; round < 2; round++) {
      const call = vi.fn().mockRejectedValueOnce(expired()).mockResolvedValueOnce("ok");
      await withSessionRefresh(call, deps);
    }

    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
