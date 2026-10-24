import type { Metadata } from "next";
import { cookies } from "next/headers";

import { ChallengeForm, LinkProblem } from "@/features/patient-link/ChallengeForm";
import { PrescriptionView } from "@/features/patient-link/PrescriptionView";
import { otherLanguage, pageLanguage, stringsFor, type PageLanguage, type PageStrings } from "@/features/patient-link/strings";
import { VIEW_COOKIE, pagePath, problemFor, readProblem, type Problem } from "@/features/patient-link/view-cookie";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";

// R12: nothing clinical in the title, the description or social previews.
export const metadata: Metadata = {
  title: "Prescription · MediEase",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

type Search = Record<string, string | string[] | undefined>;
type Page = GetResponse<"/api/v1/public/links/{token}/prescription">;
type Summary = GetResponse<"/api/v1/public/links/{token}">;

function message(strings: PageStrings, problem: Problem, left: number | undefined): string {
  switch (problem) {
    case "failed":
      return strings.wrong(left);
    case "locked":
      return strings.locked;
    case "rate":
      return strings.rateLimited;
    case "invalid":
      return strings.invalid;
    case "expired":
      return strings.expired;
    case "revoked":
      return strings.revoked;
    default:
      return strings.unavailable;
  }
}

function problemOf(error: unknown): Problem {
  return error instanceof ApiError ? problemFor(error.code) : "unavailable";
}

/** The page's content with this link's view, or why there is none. */
async function loadPage(token: string, view: string, lang: PageLanguage | undefined): Promise<Page | Problem | "ask"> {
  try {
    return (
      await apiGet("/api/v1/public/links/{token}/prescription", {
        pathParams: { token },
        query: { lang },
        headers: { "X-Link-View": view },
      })
    ).data;
  } catch (error) {
    // The 30-minute view ended, or the cookie is not this link's: ask again.
    if (error instanceof ApiError && error.code === "LINK_CHALLENGE_REQUIRED") return "ask";
    return problemOf(error);
  }
}

async function loadSummary(token: string): Promise<Summary | Problem> {
  try {
    return (await apiGet("/api/v1/public/links/{token}", { pathParams: { token } })).data;
  } catch (error) {
    return problemOf(error);
  }
}

/**
 * The patient's prescription page (M4-P5; FR-RX-07, 08; spec R10-R12, R19). Rendered on the
 * server for every request with no client components (decision 5A): first the last-4 check,
 * then, with this link's view cookie, the latest issued version. `?lang=` switches the page
 * only, never the saved preference.
 */
export default async function PatientPrescriptionPage({
  params,
  searchParams,
}: Readonly<{ params: Promise<{ token: string }>; searchParams: Promise<Search> }>) {
  const { token } = await params;
  const query = await searchParams;
  const asked = pageLanguage(query.lang);
  const view = (await cookies()).get(VIEW_COOKIE)?.value;
  const switchTo = (lang: PageLanguage) => `${pagePath(token)}?lang=${otherLanguage(lang)}`;

  if (view !== undefined) {
    const page = await loadPage(token, view, asked);
    if (typeof page === "object") {
      return (
        <PrescriptionView
          page={page}
          strings={stringsFor(page.language)}
          switchHref={switchTo(page.language)}
          saveHref={`/portal/link/prescription/${encodeURIComponent(token)}`}
        />
      );
    }
    if (page !== "ask" && page !== "failed") {
      const lang = asked ?? "en";
      return <LinkProblem language={lang} message={message(stringsFor(lang), page, undefined)} />;
    }
  }

  const summary = await loadSummary(token);
  if (typeof summary !== "object") {
    const lang = asked ?? "en";
    const problem = summary === "failed" ? "invalid" : summary;
    return <LinkProblem language={lang} message={message(stringsFor(lang), problem, undefined)} />;
  }
  const lang = asked ?? summary.language;
  const strings = stringsFor(lang);
  const problem = summary.locked ? "locked" : readProblem(query.e);
  const left = typeof query.left === "string" ? Number.parseInt(query.left, 10) : Number.NaN;
  return (
    <ChallengeForm
      token={token}
      clinicName={summary.clinic_name}
      language={lang}
      strings={strings}
      {...(problem === undefined ? {} : { problem: message(strings, problem, Number.isNaN(left) ? undefined : left) })}
      locked={summary.locked}
      switchHref={switchTo(lang)}
    />
  );
}
