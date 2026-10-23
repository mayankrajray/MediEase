/**
 * The only way the web app talks to the MediEase API (apps/web/CLAUDE.md).
 *
 * - Types come from `schema.d.ts`, generated from contracts/openapi.yaml.
 * - Every request carries an `X-Request-ID`, so a problem a user reports with
 *   "Ref: <id>" can be found in the API logs (NFR-12).
 * - Unsafe requests (POST, PUT, PATCH) carry `X-CSRF-Token`, copied from the readable
 *   `me_csrf` cookie (double-submit, ADR-0006). The session tokens themselves
 *   are HttpOnly: this code never sees them.
 * - A clinic request can name its clinic (`clinicId` -> `X-Clinic-ID`, spec R6).
 * - Every failure becomes an `ApiError` with a stable `code`: the API's own
 *   code from its error envelope, or a `WEB_*` code when the API could not be
 *   reached or did not answer in the contract's shape (docs/ERRORS.md).
 * - `apiGetConditional` sends `If-None-Match` and turns a 304 into `notModified`
 *   (the live queue polls with it, M3-P4).
 */

import { readCsrfToken } from "./csrf";
import type { components, paths } from "./schema";

export const REQUEST_ID_HEADER = "X-Request-ID";
export const CSRF_HEADER = "X-CSRF-Token";
export const CLINIC_HEADER = "X-Clinic-ID";

/** The API did not answer: network failure, DNS, refused connection or timeout. */
export const WEB_API_UNREACHABLE = "WEB_API_UNREACHABLE";
/** The API (or something in front of it) answered with a body that is not the contract's. */
export const WEB_API_BAD_RESPONSE = "WEB_API_BAD_RESPONSE";

const DEFAULT_TIMEOUT_MS = 5_000;

type ErrorBody = components["schemas"]["Error"];
type Method = "get" | "post" | "put" | "patch" | "delete";

type PathWith<M extends Method> = {
  [P in keyof paths]: paths[P] extends { readonly [K in M]: object } ? P : never;
}[keyof paths];

/** Paths in the contract that support GET. */
export type GetPath = PathWith<"get">;
/** Paths in the contract that support POST. */
export type PostPath = PathWith<"post">;
/** Paths in the contract that support PUT. */
export type PutPath = PathWith<"put">;
/** Paths in the contract that support PATCH. */
export type PatchPath = PathWith<"patch">;
/** Paths in the contract that support DELETE. */
export type DeletePath = PathWith<"delete">;

type JsonOf<R> = R extends { readonly content: { readonly "application/json": infer B } } ? B : never;

type OperationOf<P extends keyof paths, M extends Method> = paths[P] extends {
  readonly [K in M]: infer Op;
}
  ? Op
  : never;

/** The success body the contract declares: 200/201 JSON, or `undefined` for a 204. */
type SuccessBody<Op> = Op extends { readonly responses: infer R }
  ? R extends { readonly 200: infer A }
    ? JsonOf<A>
    : R extends { readonly 201: infer B }
      ? JsonOf<B>
      : R extends { readonly 204: object }
        ? undefined
        : never
  : never;

type JsonRequestBody<Op> = Op extends {
  readonly requestBody: { readonly content: { readonly "application/json": infer B } };
}
  ? B
  : undefined;

/** The JSON body of the success response the contract declares for `GET path`. */
export type GetResponse<P extends GetPath> = SuccessBody<OperationOf<P, "get">>;
/** The JSON body of the success response the contract declares for `POST path` (`undefined` on 204). */
export type PostResponse<P extends PostPath> = SuccessBody<OperationOf<P, "post">>;
/** The JSON request body for `POST path`; `undefined` when the operation takes none. */
export type PostBody<P extends PostPath> = JsonRequestBody<OperationOf<P, "post">>;
/** The success body for `PUT path`. */
export type PutResponse<P extends PutPath> = SuccessBody<OperationOf<P, "put">>;
/** The JSON request body for `PUT path`. */
export type PutBody<P extends PutPath> = JsonRequestBody<OperationOf<P, "put">>;
/** The success body for `PATCH path`. */
export type PatchResponse<P extends PatchPath> = SuccessBody<OperationOf<P, "patch">>;
/** The JSON request body for `PATCH path`. */
export type PatchBody<P extends PatchPath> = JsonRequestBody<OperationOf<P, "patch">>;
/** The success body for `DELETE path`. */
export type DeleteResponse<P extends DeletePath> = SuccessBody<OperationOf<P, "delete">>;

export interface ApiResult<T> {
  readonly data: T;
  readonly status: number;
  /** The response's `ETag`, when it sent one (the queue, M3-P4). */
  readonly etag?: string;
  /** The request ID the API echoed (or the one we sent, if it echoed none). */
  readonly requestId: string;
}

export interface RequestOptions {
  /** Defaults to a fresh random ID. Pass one to correlate several calls. */
  readonly requestId?: string;
  readonly timeoutMs?: number;
  /** The clinic this request is for; sent as `X-Clinic-ID` (needed with several memberships). */
  readonly clinicId?: string;
  /** Values for `{placeholders}` in the path, e.g. `{ token }`. Each is URL-encoded. */
  readonly pathParams?: Readonly<Record<string, string>>;
  /** Query string values, e.g. `{ q }`. Each is URL-encoded; undefined values are left out. */
  readonly query?: Readonly<Record<string, string | undefined>>;
  /** Cancels the request, e.g. when a newer search replaces it. Combined with the timeout. */
  readonly signal?: AbortSignal;
  /** Injected in tests; defaults to the global fetch. */
  readonly fetchImpl?: typeof fetch;
  /** Extra request headers the contract declares, e.g. the patient page's `X-Link-View` (M4-P5). */
  readonly headers?: Readonly<Record<string, string>>;
  /** Which CSRF cookie to copy into `X-CSRF-Token`: `me_csrf` (staff, default) or `me_pt_csrf`. */
  readonly csrfCookie?: string;
}

export class ApiError extends Error {
  override readonly name = "ApiError";

  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly requestId: string,
    readonly details: Readonly<Record<string, unknown>> = {},
    /** Seconds the API asked us to wait (`Retry-After`, e.g. while an account is locked). */
    readonly retryAfterSeconds: number | undefined = undefined,
  ) {
    super(message);
  }
}

export function newRequestId(): string {
  // randomUUID exists only in secure contexts (HTTPS or localhost). Over plain HTTP on any
  // other host (a LAN address, the compose network in e2e) it is undefined, while
  // getRandomValues works everywhere: build the same RFC 4122 version-4 UUID from it.
  if (typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
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
  return (await send("GET", path, undefined, options)) as ApiResult<GetResponse<P>>;
}

/**
 * `body` is `undefined` for operations that take none (refresh, sign-out); it is
 * required otherwise, and typed from the contract.
 */
/** A conditional GET: unchanged since `etag` → `notModified`, else the new body and its tag. */
export type ConditionalResult<T> =
  | { readonly notModified: true; readonly etag: string; readonly requestId: string }
  | {
      readonly notModified: false;
      readonly data: T;
      readonly etag: string | undefined;
      readonly requestId: string;
    };

export async function apiGetConditional<P extends GetPath>(
  path: P,
  etag: string | undefined,
  options: RequestOptions = {},
): Promise<ConditionalResult<GetResponse<P>>> {
  const result = await send("GET", path, undefined, options, etag);
  if (result.status === 304) {
    return { notModified: true, etag: result.etag ?? etag ?? "", requestId: result.requestId };
  }
  return {
    notModified: false,
    data: result.data as GetResponse<P>,
    etag: result.etag,
    requestId: result.requestId,
  };
}

export async function apiPost<P extends PostPath>(
  path: P,
  body: PostBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PostResponse<P>>> {
  return (await send("POST", path, body, options)) as ApiResult<PostResponse<P>>;
}

export async function apiPut<P extends PutPath>(
  path: P,
  body: PutBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PutResponse<P>>> {
  return (await send("PUT", path, body, options)) as ApiResult<PutResponse<P>>;
}

export async function apiPatch<P extends PatchPath>(
  path: P,
  body: PatchBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PatchResponse<P>>> {
  return (await send("PATCH", path, body, options)) as ApiResult<PatchResponse<P>>;
}

export async function apiDelete<P extends DeletePath>(
  path: P,
  options: RequestOptions = {},
): Promise<ApiResult<DeleteResponse<P>>> {
  return (await send("DELETE", path, undefined, options)) as ApiResult<DeleteResponse<P>>;
}

async function send(
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE",
  template: string,
  body: unknown,
  options: RequestOptions,
  ifNoneMatch?: string,
): Promise<ApiResult<unknown>> {
  const sentRequestId = options.requestId ?? newRequestId();
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  // Outside the try below: a configuration or programming error must surface as
  // itself, not be mistaken for the API being unreachable.
  const url = `${apiBaseUrl()}${fillPath(template, options.pathParams)}${queryString(options.query)}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    [REQUEST_ID_HEADER]: sentRequestId,
  };
  if (options.clinicId !== undefined) {
    headers[CLINIC_HEADER] = options.clinicId;
  }
  Object.assign(headers, options.headers);
  if (ifNoneMatch !== undefined) {
    headers["If-None-Match"] = ifNoneMatch;
  }
  if (method !== "GET") {
    const csrf = readCsrfToken(options.csrfCookie);
    if (csrf !== undefined) {
      headers[CSRF_HEADER] = csrf;
    }
  }
  let payload: string | undefined;
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetchImpl(url, {
      method,
      headers,
      ...(payload === undefined ? {} : { body: payload }),
      credentials: "same-origin",
      cache: "no-store",
      signal:
        options.signal === undefined
          ? AbortSignal.timeout(timeoutMs)
          : AbortSignal.any([options.signal, AbortSignal.timeout(timeoutMs)]),
    });
  } catch (cause) {
    // A caller that cancelled its own request gets the abort back as is, not "unreachable".
    if (options.signal?.aborted === true) {
      throw cause;
    }
    const reason = isTimeout(cause) ? "timeout" : "network";
    throw new ApiError(WEB_API_UNREACHABLE, "The API could not be reached.", 0, sentRequestId, {
      reason,
    });
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER) ?? sentRequestId;
  const etag = response.headers.get("ETag") ?? undefined;

  if (response.status === 204) {
    return { data: undefined, status: 204, requestId };
  }
  if (response.status === 304) {
    // Not modified: no body by definition; the caller keeps what it has.
    return { data: undefined, status: 304, requestId, ...(etag === undefined ? {} : { etag }) };
  }

  const parsed = await readJson(response);

  if (response.ok) {
    if (parsed === undefined) {
      throw badResponse(response.status, requestId);
    }
    return { data: parsed, status: response.status, requestId, ...(etag === undefined ? {} : { etag }) };
  }

  const envelope = asErrorBody(parsed);
  if (envelope === undefined) {
    throw badResponse(response.status, requestId);
  }
  throw new ApiError(
    envelope.code,
    envelope.message,
    response.status,
    envelope.request_id || requestId,
    envelope.details ?? {},
    retryAfterSeconds(response, envelope),
  );
}

function fillPath(template: string, params: RequestOptions["pathParams"]): string {
  const path = template.replace(/\{(\w+)\}/g, (_match, name: string) => {
    const value = params?.[name];
    if (value === undefined) {
      throw new Error(`Missing path parameter "${name}" for ${template}`);
    }
    return encodeURIComponent(value);
  });
  return path;
}

function queryString(query: RequestOptions["query"]): string {
  if (query === undefined) return "";
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined) params.set(name, value);
  }
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
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

/** `Retry-After` in seconds, falling back to `details.retry_after_seconds` (docs/ERRORS.md). */
function retryAfterSeconds(response: Response, envelope: ErrorBody): number | undefined {
  const header = response.headers.get("Retry-After");
  if (header !== null && /^\d+$/.test(header.trim())) {
    return Number(header.trim());
  }
  const fromDetails: unknown = envelope.details?.["retry_after_seconds"];
  return typeof fromDetails === "number" && Number.isFinite(fromDetails) && fromDetails >= 0
    ? fromDetails
    : undefined;
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
