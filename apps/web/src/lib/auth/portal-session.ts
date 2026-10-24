/**
 * The patient portal's session in the browser (M6a-P3, ADR-0015 decision 2).
 *
 * The same refresh-once rules as the staff session (`refresh.ts`), with the portal's own
 * endpoints, CSRF cookie (`me_pt_csrf`) and Web Lock, so a staff tab and a portal tab in one
 * browser never rotate each other's tokens.
 */

import {
  ApiError,
  apiDelete,
  apiGet,
  apiPatch,
  apiPost,
  apiPut,
  newRequestId,
  REQUEST_ID_HEADER,
  type ApiResult,
  type DeletePath,
  type DeleteResponse,
  type GetPath,
  type GetResponse,
  type PatchBody,
  type PatchPath,
  type PatchResponse,
  type PostBody,
  type PostPath,
  type PostResponse,
  type PutBody,
  type PutPath,
  type PutResponse,
  type RequestOptions,
} from "@/lib/api/client";
import { PORTAL_CSRF_COOKIE } from "@/lib/api/csrf";

import { withSessionRefresh, type RefreshDeps } from "./refresh";

export const PORTAL_SIGN_IN_PATH = "/portal/sign-in";
export const PORTAL_HOME_PATH = "/portal";

const PORTAL: RefreshDeps = {
  refresh: () =>
    apiPost("/api/v1/portal/auth/refresh", undefined, { csrfCookie: PORTAL_CSRF_COOKIE }),
  probe: () => apiGet("/api/v1/portal/me"),
  lockName: "mediease-portal-session-refresh",
};

/** `apiGet` for a portal route that survives an expired access token. */
export function portalGet<P extends GetPath>(
  path: P,
  options: RequestOptions = {},
): Promise<ApiResult<GetResponse<P>>> {
  return withSessionRefresh(() => apiGet(path, options), PORTAL);
}

/** `apiPost` for a portal route: sends `me_pt_csrf`, survives an expired access token. */
export function portalPost<P extends PostPath>(
  path: P,
  body: PostBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PostResponse<P>>> {
  return withSessionRefresh(
    () => apiPost(path, body, { ...options, csrfCookie: PORTAL_CSRF_COOKIE }),
    PORTAL,
  );
}

/** `apiPatch` for a portal route (M6b-P2: the account's language). */
export function portalPatch<P extends PatchPath>(
  path: P,
  body: PatchBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PatchResponse<P>>> {
  return withSessionRefresh(
    () => apiPatch(path, body, { ...options, csrfCookie: PORTAL_CSRF_COOKIE }),
    PORTAL,
  );
}

/** `apiPut` for a portal route (M6b-P3: a medicine-reminder choice). */
export function portalPut<P extends PutPath>(
  path: P,
  body: PutBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PutResponse<P>>> {
  return withSessionRefresh(
    () => apiPut(path, body, { ...options, csrfCookie: PORTAL_CSRF_COOKIE }),
    PORTAL,
  );
}

/** `apiDelete` for a portal route (M6b-P2: unlinking a clinic). */
export function portalDelete<P extends DeletePath>(
  path: P,
  options: RequestOptions = {},
): Promise<ApiResult<DeleteResponse<P>>> {
  return withSessionRefresh(
    () => apiDelete(path, { ...options, csrfCookie: PORTAL_CSRF_COOKIE }),
    PORTAL,
  );
}

const PDF_TIMEOUT_MS = 30_000;

/**
 * A prescription's PDF through the portal session (M6b-P2, decision 6A): refreshed once like
 * every portal call, never a bare link that an expired access token would turn into a 401.
 */
export function portalPdf(rxId: string, fetchImpl: typeof fetch = fetch): Promise<Blob> {
  const once = async (): Promise<Blob> => {
    const requestId = newRequestId();
    let response: Response;
    try {
      response = await fetchImpl(`/api/v1/portal/prescriptions/${encodeURIComponent(rxId)}/pdf`, {
        headers: { [REQUEST_ID_HEADER]: requestId },
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(PDF_TIMEOUT_MS),
      });
    } catch {
      throw new ApiError("WEB_API_UNREACHABLE", "The API could not be reached.", 0, requestId, { reason: "network" });
    }
    if (response.ok) return response.blob();
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    const error = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)
      ?.error;
    throw new ApiError(
      error?.code ?? "WEB_API_BAD_RESPONSE",
      error?.message ?? "The API sent an unexpected response.",
      response.status,
      response.headers.get(REQUEST_ID_HEADER) ?? requestId,
      error?.details ?? {},
    );
  };
  return withSessionRefresh(once, PORTAL);
}