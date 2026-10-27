import type { NextRequest } from "next/server";

import { MAX_UPLOAD_REQUEST_BYTES, proxyWithLimit } from "@/lib/api/limited-proxy";

/**
 * A prescription upload through the web origin (M7b; prescription-uploads R1, R3; issue #30): an
 * oversized upload is a 413 with the API's envelope, never a 500 from the proxy. Only POST is
 * here; `/prescription-uploads/{id}` and the rest still go through the `/api` rewrite.
 */
export async function POST(request: NextRequest): Promise<Response> {
  return proxyWithLimit(request, "/api/v1/portal/prescription-uploads", MAX_UPLOAD_REQUEST_BYTES);
}
