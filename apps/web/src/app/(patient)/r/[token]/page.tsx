import type { Metadata } from "next";
import { cookies } from "next/headers";

import { ChallengeForm, LinkProblem } from "@/features/patient-link/ChallengeForm";
import { ReceiptView } from "@/features/patient-link/ReceiptView";
import { otherLanguage, pageLanguage, stringsFor, type PageLanguage, type PageStrings } from "@/features/patient-link/strings";
import { RECEIPT_VIEW_COOKIE, problemFor, readProblem, receiptPath, type Problem } from "@/features/patient-link/view-cookie";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";

// Nothing about the patient or the amount in the title or social previews (billing R49).
export const metadata: Metadata = {
  title: "Receipt · MediEase",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

type Search = Record<string, string | string[] | undefined>;
type Summary = GetResponse<"/api/v1/public/links/{token}">;
type Receipt = GetResponse<"/api/v1/public/links/{token}/receipt">;

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

const problemOf = (error: unknown): Problem => (error instanceof ApiError ? problemFor(error.code) : "unavailable");

async function loadReceipt(token: string, view: string): Promise<Receipt | Problem | "ask"> {
  try {
    return (await apiGet("/api/v1/public/links/{token}/receipt", { pathParams: { token }, headers: { "X-Link-View": view } })).data;
  } catch (error) {
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
 * A bill's receipt page (M6d-P4; FR-BIL-04; billing R48-R50): the prescription page's last-4
 * check, then the bill's number, date and amounts with its PDF. Server-rendered, no client code.
 */
export default async function ReceiptPage({ params, searchParams }: Readonly<{ params: Promise<{ token: string }>; searchParams: Promise<Search> }>) {
  const { token } = await params;
  const query = await searchParams;
  const asked = pageLanguage(query.lang);
  const view = (await cookies()).get(RECEIPT_VIEW_COOKIE)?.value;
  const switchTo = (lang: PageLanguage) => `${receiptPath(token)}?lang=${otherLanguage(lang)}`;

  if (view !== undefined) {
    const receipt = await loadReceipt(token, view);
    if (typeof receipt === "object") {
      return <ReceiptView receipt={receipt} pdfHref={`${receiptPath(token)}/receipt.pdf`} />;
    }
    if (receipt !== "ask" && receipt !== "failed") {
      const lang = asked ?? "en";
      return <LinkProblem language={lang} message={message(stringsFor(lang), receipt, undefined)} />;
    }
  }

  const summary = await loadSummary(token);
  if (typeof summary !== "object" || summary.purpose !== "RECEIPT") {
    const lang = asked ?? "en";
    const problem = typeof summary !== "object" && summary !== "failed" ? summary : "invalid";
    return <LinkProblem language={lang} message={message(stringsFor(lang), problem, undefined)} />;
  }
  const lang = asked ?? summary.language;
  const strings = stringsFor(lang);
  const problem = summary.locked ? "locked" : readProblem(query.e);
  const left = typeof query.left === "string" ? Number.parseInt(query.left, 10) : Number.NaN;
  return (
    <ChallengeForm
      token={token}
      base="/r"
      title={lang === "hi" ? "आपका बिल" : "Your bill"}
      clinicName={summary.clinic_name}
      language={lang}
      strings={strings}
      {...(problem === undefined ? {} : { problem: message(strings, problem, Number.isNaN(left) ? undefined : left) })}
      locked={summary.locked}
      switchHref={switchTo(lang)}
    />
  );
}
