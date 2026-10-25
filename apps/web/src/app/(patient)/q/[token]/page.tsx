import type { Metadata } from "next";
import { cookies } from "next/headers";

import { liveProblemOf, liveProblemText } from "@/features/live-queue/problems";
import { LiveQueueView } from "@/features/live-queue/LiveQueueView";
import { apiGet, type ApiResult, type GetResponse } from "@/lib/api/client";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { liveWords } from "@/lib/i18n/patient-notifications";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

// R71: nothing about the patient in the title or previews; never indexed, never a referrer.
export const metadata: Metadata = {
  title: "Live queue · MediEase",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

type Search = Record<string, string | string[] | undefined>;
type First = ApiResult<GetResponse<"/api/v1/public/queue/{token}">>;

/** The first answer, or the error that stands in for it. */
async function load(token: string): Promise<First | { readonly error: unknown }> {
  try {
    return await apiGet("/api/v1/public/queue/{token}", { pathParams: { token } });
  } catch (error) {
    return { error };
  }
}

/**
 * The live token page (M6b-P6; spec R69-R72, ADR-0019): public, no sign-in and no last-4 check,
 * the signed token in the path being the whole authority, for that one appointment on that one
 * day. Rendered on the server, then the client polls every 20 s. English or Hindi, 360 px first.
 */
export default async function LiveQueuePage({
  params,
  searchParams,
}: Readonly<{ params: Promise<{ token: string }>; searchParams: Promise<Search> }>) {
  const { token } = await params;
  const query = await searchParams;
  const language = pickLanguage(query.lang, (await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  const first = await load(token);
  if ("data" in first) {
    return <LiveQueueView token={token} language={language} initial={first.data} initialEtag={first.etag} />;
  }
  const words = liveWords(language);
  return (
    <main lang={language} className="mx-auto max-w-md px-4 pt-6 text-base text-slate-900">
      <h1 className="text-2xl font-bold tracking-tight">{words.heading}</h1>
      <p role="alert" className="mt-3 font-semibold">
        {liveProblemText(words, liveProblemOf(first.error))}
      </p>
    </main>
  );
}
