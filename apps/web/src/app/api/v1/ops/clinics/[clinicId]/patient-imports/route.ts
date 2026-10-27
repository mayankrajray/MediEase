import type { NextRequest } from "next/server";

import { MAX_IMPORT_BYTES, proxyWithLimit } from "@/lib/api/limited-proxy";

/**
 * The ops patient import through the web origin (M2-P4; issue #30): over 2 MB is the API's 413,
 * answered here, instead of an occasional 500 from the proxy. The query (`dry_run`) is passed on.
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ clinicId: string }> },
): Promise<Response> {
  const { clinicId } = await params;
  return proxyWithLimit(
    request,
    `/api/v1/ops/clinics/${encodeURIComponent(clinicId)}/patient-imports`,
    MAX_IMPORT_BYTES,
  );
}
