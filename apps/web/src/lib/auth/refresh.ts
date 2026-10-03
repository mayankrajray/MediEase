/**
 * Keeping a browser session alive without ending it by accident (FR-AUTH-02).
 *
 * The access token lives 15 minutes. When a call fails with 401
 * `AUTH_SESSION_EXPIRED` we rotate the refresh token once and retry the call
 * once. The subtle part: a refresh token is single use and the API has no grace
 * window, so presenting one that was already rotated revokes the whole session
 * (`AUTH_REFRESH_REUSED`, spec R5). Two refreshes racing would therefore sign
 * the user out. We prevent that at two levels:
 *
 * - **In this tab**, every call that needs a refresh shares one in-flight refresh.
 * - **Across tabs**, the refresh runs under a Web Lock, and inside the lock we
 *   first check whether the session already works (another tab may have just
 *   refreshed). Where Web Locks are unavailable we fall back to the tab-level
 *   guarantee alone.
 */

import {
  ApiError,
  apiGet,
  apiPost,
  type GetPath,
  type GetResponse,
  type PostBody,
  type PostPath,
  type PostResponse,
  type ApiResult,
  type RequestOptions,
} from "@/lib/api/client";

export const AUTH_SESSION_EXPIRED = "AUTH_SESSION_EXPIRED";
export const AUTH_REFRESH_REUSED = "AUTH_REFRESH_REUSED";
export const AUTH_ACCOUNT_DISABLED = "AUTH_ACCOUNT_DISABLED";

const LOCK_NAME = "mediease-session-refresh";

export interface RefreshDeps {
  /** Rotates the refresh token. Defaults to `POST /api/v1/auth/refresh`. */
  readonly refresh?: () => Promise<unknown>;
  /** A cheap authenticated call: does the session work right now? Defaults to `GET /api/v1/me`. */
  readonly probe?: () => Promise<unknown>;
  /** Defaults to `navigator.locks` when the browser has it. */
  readonly locks?: Pick<LockManager, "request"> | undefined;
}

let inFlight: Promise<void> | undefined;

/** Tests only: forget a refresh that is still "in flight". */
export function resetRefreshState(): void {
  inFlight = undefined;
}

export function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401 && error.code === AUTH_SESSION_EXPIRED;
}

/**
 * Runs `call`; if the access token had expired, refreshes the session once and
 * runs `call` again. Any other failure, or a second failure, is thrown as is.
 */
export async function withSessionRefresh<T>(
  call: () => Promise<T>,
  deps: RefreshDeps = {},
): Promise<T> {
  try {
    return await call();
  } catch (error) {
    if (!isSessionExpired(error)) {
      throw error;
    }
  }
  await refreshOnce(deps);
  return call();
}

function refreshOnce(deps: RefreshDeps): Promise<void> {
  inFlight ??= runRefresh(deps).finally(() => {
    inFlight = undefined;
  });
  return inFlight;
}

async function runRefresh(deps: RefreshDeps): Promise<void> {
  const refresh = deps.refresh ?? defaultRefresh;
  const probe = deps.probe ?? defaultProbe;

  const work = async (): Promise<void> => {
    try {
      // Another tab (or an earlier caller in this one) may have refreshed while
      // we waited for the lock; refreshing again would present a rotated token.
      await probe();
      return;
    } catch (error) {
      if (!isSessionExpired(error)) {
        throw error;
      }
    }
    await refresh();
  };

  const locks = "locks" in deps ? deps.locks : defaultLocks();
  if (locks === undefined) {
    return work();
  }
  return locks.request(LOCK_NAME, work);
}

async function defaultRefresh(): Promise<void> {
  await apiPost("/api/v1/auth/refresh", undefined);
}

async function defaultProbe(): Promise<void> {
  await apiGet("/api/v1/me");
}

function defaultLocks(): Pick<LockManager, "request"> | undefined {
  return typeof navigator !== "undefined" && "locks" in navigator ? navigator.locks : undefined;
}

/** `apiGet` that survives an expired access token. */
export function sessionGet<P extends GetPath>(
  path: P,
  options: RequestOptions = {},
): Promise<ApiResult<GetResponse<P>>> {
  return withSessionRefresh(() => apiGet(path, options));
}

/** `apiPost` that survives an expired access token. */
export function sessionPost<P extends PostPath>(
  path: P,
  body: PostBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PostResponse<P>>> {
  return withSessionRefresh(() => apiPost(path, body, options));
}
