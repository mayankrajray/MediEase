import { NextResponse, type NextRequest } from "next/server";

import { pageLanguage } from "@/features/patient-link/strings";
import { RECEIPT_VIEW_COOKIE, problemFor, receiptPath } from "@/features/patient-link/view-cookie";
import { ApiError, apiPost } from "@/lib/api/client";

/**
 * The receipt page's last-4 form target (M6d-P4, billing R48): the prescription page's flow, with
 * the view token in its own HttpOnly cookie scoped to this receipt page, then a 303 back.
 */
export async function POST(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const form = await request.formData();
  const digits = String(form.get("phone_last4") ?? "").trim();
  const lang = pageLanguage(String(form.get("lang") ?? ""));
  const back = new URLSearchParams();
  if (lang !== undefined) back.set("lang", lang);
  const secure = (request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol).startsWith("https");

  try {
    const { data } = await apiPost("/api/v1/public/links/{token}/verify", { phone_last4: digits }, { pathParams: { token } });
    const response = seeOther(token, back);
    response.cookies.set(RECEIPT_VIEW_COOKIE, data.view_token, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: receiptPath(token),
      expires: new Date(data.view_expires_at),
    });
    return response;
  } catch (error) {
    const problem = error instanceof ApiError ? problemFor(error.code) : "unavailable";
    back.set("e", problem);
    if (problem === "failed" && error instanceof ApiError && typeof error.details.attempts_left === "string") {
      back.set("left", error.details.attempts_left);
    }
    return seeOther(token, back);
  }
}

function seeOther(token: string, query: URLSearchParams): NextResponse {
  const search = query.toString();
  const location = search === "" ? receiptPath(token) : `${receiptPath(token)}?${search}`;
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}
