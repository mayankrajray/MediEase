/**
 * The only way the web app talks to the MediEase API (apps/web/CLAUDE.md).
 *
 * - Types come from `schema.d.ts`, generated from contracts/openapi.yaml.
 * - Every request carries an `X-Request-ID`, so a problem a user reports with
 *   "Ref: <id>" can be found in the API logs (NFR-12).
 * - Every failure becomes an `ApiError` with a stable `code`: the API's own
 *   code from its error envelope, or a `WEB_*` code when the API could not be
 *   reached or did not answer in the contract's shape (docs/ERRORS.md).
 */

import type { components, paths } from "./schema";

export const REQUEST_ID_HEADER = "X-Request-ID";

/** The API did not answer: network failure, DNS, refused connection or timeout. */
export const WEB_API_UNREACHABLE = "WEB_API_UNREACHABLE";
/** The API (or something in front of it) answered with a body that is not the contract's. */
export const WEB_API_BAD_RESPONSE = "WEB_API_BAD_RESPONSE";

const DEFAULT_TIMEOUT_MS = 5_000;

type ErrorBody = components["schemas"]["Error"];

/** Paths in the contract that support GET. */
export type GetPath = {
  [P in keyof paths]: paths[P] extends { readonly get: object } ? P : never;
}[keyof paths];

type JsonOf<R> = R extends { readonly content: { readonly "application/json": infer B } } ? B : never;

type GetOperation<P extends GetPath> = paths[P] extends { readonly get: infer Op } ? Op : never;

/** The JSON body of the 200 response the contract declares for `GET path`. */
export type GetResponse<P extends GetPath> =
  GetOperation<P> extends { readonly responses: { readonly 200: infer R } } ? JsonOf<R> : never;

export interface ApiResult<T> {
  readonly data: T;
  readonly status: number;
  /** The request ID the API echoed (or the one we sent, if it echoed none). */
  readonly requestId: string;
}

export interface RequestOptions {
  /** Defaults to a fresh random ID. Pass one to correlate several calls. */
  readonly requestId?: string;
  readonly timeoutMs?: number;
  /** Injected in tests; defaults to the global fetch. */
  readonly fetchImpl?: typeof fetch;
}

export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly requestId: string,
    readonly details: Readonly<Record<string, unknown>> = {},
  ) {
    super(message);
  }
}

export function newRequestId(): string {
  return crypto.randomUUID();
}

/**
 * Where API requests go. On the server: API_INTERNAL_URL (the API on the
 * internal network). In the browser: this origin, whose `/api`, `/health` and
 * `/ready` paths next.config rewrites to the API (ADR-0006).
 */
export function apiBaseUrl(): string {
  if (typeof window !== "undefined") {
    return "";
  }
  const url = process.env.API_INTERNAL_URL;
  if (!url) {
    throw new Error("API_INTERNAL_URL is not set; see .env.example (M0-P4).");
  }
  return url.replace(/\/+$/, "");
}

export async function apiGet<P extends GetPath>(
  path: P,
  options: RequestOptions = {},
): Promise<ApiResult<GetResponse<P>>> {
  const sentRequestId = options.requestId ?? newRequestId();
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  // Outside the try below: a configuration error must surface as itself, not
  // be mistaken for the API being unreachable.
  const url = `${apiBaseUrl()}${path}`;

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method: "GET",
      headers: { Accept: "application/json", [REQUEST_ID_HEADER]: sentRequestId },
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (cause) {
    const reason = isTimeout(cause) ? "timeout" : "network";
    throw new ApiError(WEB_API_UNREACHABLE, "The API could not be reached.", 0, sentRequestId, {
      reason,
    });
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER) ?? sentRequestId;
  const body = await readJson(response);

  if (response.ok) {
    if (body === undefined) {
      throw badResponse(response.status, requestId);
    }
    return { data: body as GetResponse<P>, status: response.status, requestId };
  }

  const envelope = asErrorBody(body);
  if (envelope === undefined) {
    throw badResponse(response.status, requestId);
  }
  throw new ApiError(
    envelope.code,
    envelope.message,
    response.status,
    envelope.request_id || requestId,
    envelope.details ?? {},
  );
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return (await response.json()) as unknown;
  } catch {
    return undefined;
  }
}

function asErrorBody(body: unknown): ErrorBody | undefined {
  if (typeof body !== "object" || body === null || !("error" in body)) {
    return undefined;
  }
  const error: unknown = body.error;
  if (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    typeof error.code === "string" &&
    "message" in error &&
    typeof error.message === "string" &&
    "request_id" in error &&
    typeof error.request_id === "string"
  ) {
    return error as ErrorBody;
  }
  return undefined;
}

function badResponse(status: number, requestId: string): ApiError {
  return new ApiError(
    WEB_API_BAD_RESPONSE,
    "The API sent a response the app did not understand.",
    status,
    requestId,
  );
}

function isTimeout(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "TimeoutError";
}
