import { NextResponse, type NextRequest } from "next/server";

import { pageLanguage } from "@/features/patient-link/strings";
import { VIEW_COOKIE, pagePath, problemFor } from "@/features/patient-link/view-cookie";
import { ApiError, apiPost } from "@/lib/api/client";

/**
 * The last-4 form's target (M4-P5 decision 5A): asks the API, keeps the view token in an HttpOnly
 * cookie scoped to this link's page (decision 3A) and sends the browser back to the page with a
 * 303, so a refresh never re-posts the digits. The digits are never logged or put in a URL.
 */
export async function POST(request: NextRequest, { params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const form = await request.formData();
  const digits = String(form.get("phone_last4") ?? "").trim();
  const lang = pageLanguage(String(form.get("lang") ?? ""));
  // A relative Location (RFC 9110): behind compose or a proxy the server's own idea of its host
  // is not the one the browser used.
  const back = new URLSearchParams();
  if (lang !== undefined) back.set("lang", lang);
  const secure = (request.headers.get("x-forwarded-proto") ?? request.nextUrl.protocol).startsWith("https");

  try {
    const { data } = await apiPost(
      "/api/v1/public/links/{token}/verify",
      { phone_last4: digits },
      { pathParams: { token } },
    );
    const response = seeOther(token, back);
    response.cookies.set(VIEW_COOKIE, data.view_token, {
      httpOnly: true,
      secure,
      sameSite: "lax",
      path: pagePath(token),
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
  const location = search === "" ? pagePath(token) : `${pagePath(token)}?${search}`;
  return new NextResponse(null, { status: 303, headers: { Location: location } });
}
