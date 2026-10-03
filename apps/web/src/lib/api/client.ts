/**
 * The only way the web app talks to the MediEase API (apps/web/CLAUDE.md).
 *
 * - Types come from `schema.d.ts`, generated from contracts/openapi.yaml.
 * - Every request carries an `X-Request-ID`, so a problem a user reports with
 *   "Ref: <id>" can be found in the API logs (NFR-12).
 * - Unsafe requests (POST) carry `X-CSRF-Token`, copied from the readable
 *   `me_csrf` cookie (double-submit, ADR-0006). The session tokens themselves
 *   are HttpOnly: this code never sees them.
 * - A clinic request can name its clinic (`clinicId` -> `X-Clinic-ID`, spec R6).
 * - Every failure becomes an `ApiError` with a stable `code`: the API's own
 *   code from its error envelope, or a `WEB_*` code when the API could not be
 *   reached or did not answer in the contract's shape (docs/ERRORS.md).
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
type Method = "get" | "post";

type PathWith<M extends Method> = {
  [P in keyof paths]: paths[P] extends { readonly [K in M]: object } ? P : never;
}[keyof paths];

/** Paths in the contract that support GET. */
export type GetPath = PathWith<"get">;
/** Paths in the contract that support POST. */
export type PostPath = PathWith<"post">;

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
  /** The clinic this request is for; sent as `X-Clinic-ID` (needed with several memberships). */
  readonly clinicId?: string;
  /** Values for `{placeholders}` in the path, e.g. `{ token }`. Each is URL-encoded. */
  readonly pathParams?: Readonly<Record<string, string>>;
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
    /** Seconds the API asked us to wait (`Retry-After`, e.g. while an account is locked). */
    readonly retryAfterSeconds: number | undefined = undefined,
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
  return (await send("GET", path, undefined, options)) as ApiResult<GetResponse<P>>;
}

/**
 * `body` is `undefined` for operations that take none (refresh, sign-out); it is
 * required otherwise, and typed from the contract.
 */
export async function apiPost<P extends PostPath>(
  path: P,
  body: PostBody<P>,
  options: RequestOptions = {},
): Promise<ApiResult<PostResponse<P>>> {
  return (await send("POST", path, body, options)) as ApiResult<PostResponse<P>>;
}

async function send(
  method: "GET" | "POST",
  template: string,
  body: unknown,
  options: RequestOptions,
): Promise<ApiResult<unknown>> {
  const sentRequestId = options.requestId ?? newRequestId();
  const fetchImpl = options.fetchImpl ?? fetch;
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  // Outside the try below: a configuration or programming error must surface as
  // itself, not be mistaken for the API being unreachable.
  const url = `${apiBaseUrl()}${fillPath(template, options.pathParams)}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    [REQUEST_ID_HEADER]: sentRequestId,
  };
  if (options.clinicId !== undefined) {
    headers[CLINIC_HEADER] = options.clinicId;
  }
  if (method === "POST") {
    const csrf = readCsrfToken();
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
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch (cause) {
    const reason = isTimeout(cause) ? "timeout" : "network";
    throw new ApiError(WEB_API_UNREACHABLE, "The API could not be reached.", 0, sentRequestId, {
      reason,
    });
  }

  const requestId = response.headers.get(REQUEST_ID_HEADER) ?? sentRequestId;

  if (response.status === 204) {
    return { data: undefined, status: 204, requestId };
  }

  const parsed = await readJson(response);

  if (response.ok) {
    if (parsed === undefined) {
      throw badResponse(response.status, requestId);
    }
    return { data: parsed, status: response.status, requestId };
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
