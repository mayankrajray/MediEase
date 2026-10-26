import { NextResponse, type NextRequest } from "next/server";

import { RECEIPT_VIEW_COOKIE, receiptPath } from "@/features/patient-link/view-cookie";
import { apiBaseUrl } from "@/lib/api/client";

/**
 * The receipt PDF for the receipt page (M6d-P4, billing R50). The browser cannot send the view
 * token as a header, so this server route reads the page's HttpOnly cookie and asks the API with
 * `X-Link-View`. Without a valid view the patient goes back to the page and its last-4 check.
 */
export async function GET(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const view = request.cookies.get(RECEIPT_VIEW_COOKIE)?.value;
  const back = new NextResponse(null, { status: 303, headers: { Location: receiptPath(token) } });
  if (view === undefined) return back;
  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/api/v1/public/links/${encodeURIComponent(token)}/receipt.pdf`, {
      headers: { "X-Link-View": view, Accept: "application/pdf" },
      cache: "no-store",
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    return back;
  }
  if (!upstream.ok) return back;
  return new NextResponse(await upstream.arrayBuffer(), {
    status: 200,
    headers: {
      "Content-Type": "application/pdf",
      "Content-Disposition": upstream.headers.get("Content-Disposition") ?? 'inline; filename="receipt.pdf"',
      "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex, nofollow",
      "Referrer-Policy": "no-referrer",
    },
  });
}
