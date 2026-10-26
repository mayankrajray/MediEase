import type { Metadata } from "next";
import { cookies } from "next/headers";

import { FindPage, type FindResult, type Options } from "@/features/find/FindPage";
import { apiFilters, readQuery, type Search } from "@/features/find/query";
import { ApiError, apiGet } from "@/lib/api/client";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { findWords } from "@/lib/i18n/find";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

export async function generateMetadata({ searchParams }: Readonly<{ searchParams: Promise<Search> }>): Promise<Metadata> {
  const search = await searchParams;
  const words = findWords(pickLanguage(search.lang, undefined));
  const plain = Object.keys(search).every((k) => k === "lang");
  // The search page itself may be indexed; result pages may not (they change by the hour).
  return {
    title: `${words.title} · MediEase`,
    description: words.intro,
    robots: plain ? { index: true, follow: true } : { index: false, follow: true },
    alternates: { canonical: "/find" },
  };
}

/** `/find` (M6c-P6; FR-DIS-01, 02): server-rendered directory search, public. */
export default async function FindRoute({ searchParams }: Readonly<{ searchParams: Promise<Search> }>) {
  const search = await searchParams;
  const language = pickLanguage(search.lang, (await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  const query = readQuery(search);
  const filters = apiFilters(query);
  let result: FindResult;
  let options: Options | undefined;
  try {
    if (query.kind === "clinics") {
      const { data } = await apiGet("/api/v1/public/search/clinics", { query: filters });
      result = { status: "clinics", items: data.items };
      options = data.options;
    } else {
      const { data } = await apiGet("/api/v1/public/search/doctors", { query: filters });
      result = { status: "doctors", items: data.items };
      options = data.options;
    }
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 0;
    result = { status: status === 429 ? "limited" : status === 422 ? "invalid" : "failed" };
  }
  return <FindPage query={query} result={result} options={options} language={language} />;
}
