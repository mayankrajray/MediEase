/**
 * The patient portal's session in the browser (M6a-P3, ADR-0015 decision 2).
 *
 * The same refresh-once rules as the staff session (`refresh.ts`), with the portal's own
 * endpoints, CSRF cookie (`me_pt_csrf`) and Web Lock, so a staff tab and a portal tab in one
 * browser never rotate each other's tokens.
 */

import {
  apiGet,
  apiPost,
  type ApiResult,
  type GetPath,
  type GetResponse,
  type PostBody,
  type PostPath,
  type PostResponse,
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
