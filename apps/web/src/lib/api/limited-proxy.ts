import { NextResponse, type NextRequest } from "next/server";

import { REQUEST_ID_HEADER, apiBaseUrl } from "./client";

/**
 * A size-checked proxy for the upload routes (issue #30; prescription-uploads R3).
 *
 * Through the `/api` rewrite, an over-limit body could surface as a 500: the API answered 413 and
 * closed the connection while the proxy was still streaming (`write EPIPE`). These routes check
 * the size here instead: a declared `Content-Length` over the limit is answered at once, and the
 * body is otherwise read with a running count and abandoned the moment it passes the limit. Either
 * way the answer is the API's own 413 envelope. A body within the limit is sent on whole, with the
 * headers the API needs (session cookies, CSRF token, content type, request ID); the API's answer
 * comes back unchanged.
 */

const PASSED_TO_API = ["cookie", "content-type", "x-csrf-token", "accept", "accept-language"] as const;
const PASSED_BACK = ["content-type", "cache-control", "retry-after", "set-cookie", "x-request-id"] as const;
const UPSTREAM_TIMEOUT_MS = 60_000;

export const TOO_LARGE_CODE = "REQ_REQUEST_ENTITY_TOO_LARGE";
// The API's limits: a prescription upload is 10 MB plus 64 KB of multipart framing
// (delivery/http/prescription_uploads.py); the ops patient import 2 MB of CSV (delivery/http/ops.py).
export const MAX_UPLOAD_REQUEST_BYTES = 10 * 1024 * 1024 + 64 * 1024;
export const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
// Werkzeug's description, so both origins say the same thing.
const TOO_LARGE_MESSAGE = "The data value transmitted exceeds the capacity limit.";

function requestId(request: NextRequest): string {
  return request.headers.get(REQUEST_ID_HEADER) ?? crypto.randomUUID();
}

export function tooLarge(id: string): NextResponse {
  return NextResponse.json(
    { error: { code: TOO_LARGE_CODE, message: TOO_LARGE_MESSAGE, request_id: id, details: {} } },
    { status: 413, headers: { "Cache-Control": "no-store", [REQUEST_ID_HEADER]: id } },
  );
}

/** The body, or `null` once it is longer than `maxBytes` (the rest is never read). */
async function readCapped(request: NextRequest, maxBytes: number): Promise<Uint8Array<ArrayBuffer> | null> {
  if (request.body === null) return new Uint8Array();
  const reader = request.body.getReader();
  const parts: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel().catch(() => undefined);
      return null;
    }
    parts.push(value);
  }
  const body = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    body.set(part, offset);
    offset += part.byteLength;
  }
  return body;
}

export async function proxyWithLimit(request: NextRequest, apiPath: string, maxBytes: number): Promise<Response> {
  const id = requestId(request);
  const declared = Number(request.headers.get("content-length") ?? "NaN");
  if (Number.isFinite(declared) && declared > maxBytes) return tooLarge(id);
  const body = await readCapped(request, maxBytes);
  if (body === null) return tooLarge(id);

  const headers = new Headers({ [REQUEST_ID_HEADER]: id });
  for (const name of PASSED_TO_API) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}${apiPath}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return NextResponse.json(
      { error: { code: "WEB_API_UNREACHABLE", message: "The service is unavailable.", request_id: id, details: {} } },
      { status: 503, headers: { "Cache-Control": "no-store", [REQUEST_ID_HEADER]: id } },
    );
  }
  const back = new Headers();
  for (const name of PASSED_BACK) {
    const value = upstream.headers.get(name);
    if (value !== null) back.set(name, value);
  }
  return new NextResponse(await upstream.arrayBuffer(), { status: upstream.status, headers: back });
}
