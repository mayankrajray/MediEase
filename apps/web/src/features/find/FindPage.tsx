import Link from "next/link";

import { rupees } from "@/lib/format/money";
import type { GetResponse } from "@/lib/api/client";
import { findWords, shortDay } from "@/lib/i18n/find";
import type { PortalLanguage } from "@/lib/i18n/portal";

export type SearchKind = "doctors" | "clinics";
export type DoctorHits = GetResponse<"/api/v1/public/search/doctors">;
export type ClinicHits = GetResponse<"/api/v1/public/search/clinics">;
export type Options = DoctorHits["options"];

export interface FindQuery {
  readonly kind: SearchKind;
  readonly q: string;
  readonly where: string;
  readonly specialty: string;
  readonly language: string;
  readonly available: boolean;
}

export type FindResult =
  | { readonly status: "doctors"; readonly items: DoctorHits["items"] }
  | { readonly status: "clinics"; readonly items: ClinicHits["items"] }
  | { readonly status: "failed" | "limited" | "invalid" };

/** The query string for a search, keeping the language (`lang`) when Hindi. */
export function findHref(query: FindQuery, language: PortalLanguage, kind: SearchKind = query.kind): string {
  const params = new URLSearchParams();
  if (kind !== "doctors") params.set("type", kind);
  if (query.q !== "") params.set("q", query.q);
  if (query.where !== "") params.set("where", query.where);
  if (query.specialty !== "") params.set("specialty", query.specialty);
  if (query.language !== "") params.set("language", query.language);
  if (query.available) params.set("available", "true");
  if (language === "hi") params.set("lang", "hi");
  const text = params.toString();
  return text === "" ? "/find" : `/find?${text}`;
}

const FIELD = "min-h-11 w-full rounded-lg border border-slate-400 bg-white px-3 text-base text-slate-900";
const LABEL = "block font-medium text-slate-900";
const CARD = "space-y-1 rounded-card border border-slate-200 bg-white p-4 shadow-card";
const LINK = "inline-flex min-h-11 items-center font-semibold text-brand-800 underline";

/**
 * Directory search (M6c-P6; FR-DIS-01, 02, 04, 05; spec discovery R1-R10): one plain GET form that
 * works without JavaScript, then doctors or clinics in the API's order. Rendered on the server,
 * English or Hindi, 360 px first. A result opens the profile, where the patient picks a time (P7).
 */
export function FindPage({
  query,
  result,
  options,
  language,
}: Readonly<{ query: FindQuery; result: FindResult; options: Options | undefined; language: PortalLanguage }>) {
  const w = findWords(language);
  const other = language === "hi" ? "en" : "hi";
  const tab = (kind: SearchKind, label: string) => (
    <Link
      href={findHref(query, language, kind)}
      aria-current={query.kind === kind ? "page" : undefined}
      className={`inline-flex min-h-11 items-center rounded-lg border px-4 font-medium ${query.kind === kind ? "border-brand-700 bg-brand-50 text-brand-900" : "border-slate-400 bg-white text-slate-900"}`}
    >
      {label}
    </Link>
  );
  const switchQuery = new URLSearchParams(findHref(query, other).split("?")[1] ?? "");
  if (other === "en") switchQuery.set("lang", "en");

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link href={language === "hi" ? "/?lang=hi" : "/"} className="flex min-h-11 items-center gap-2 text-lg font-bold text-slate-900">
            <span aria-hidden="true" className="grid size-8 place-items-center rounded-xl bg-brand-700 text-sm text-white">
              M
            </span>
            MediEase
          </Link>
          <Link
            href={`/find?${switchQuery.toString()}`}
            lang={other}
            aria-label={w.switchLabel}
            className="inline-flex min-h-11 items-center rounded-lg border border-slate-400 bg-white px-3 text-sm font-medium"
          >
            {w.switchTo}
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-5 px-4 py-5">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">{w.title}</h1>
          <p className="text-slate-800">{w.intro}</p>
        </div>
        <p role="note" className="rounded-lg border border-amber-700 bg-amber-50 p-3 text-sm text-amber-950">
          {w.emergency}
        </p>

        <form method="get" action="/find" role="search" className={`${CARD} space-y-3`}>
          {query.kind === "clinics" && <input type="hidden" name="type" value="clinics" />}
          {language === "hi" && <input type="hidden" name="lang" value="hi" />}
          <div>
            <label htmlFor="find-q" className={LABEL}>
              {w.what}
            </label>
            <input id="find-q" name="q" type="search" defaultValue={query.q} maxLength={100} aria-describedby="find-q-hint" className={FIELD} />
            <p id="find-q-hint" className="text-sm text-slate-700">
              {w.whatHint}
            </p>
          </div>
          <div>
            <label htmlFor="find-where" className={LABEL}>
              {w.where}
            </label>
            <input id="find-where" name="where" defaultValue={query.where} maxLength={100} aria-describedby="find-where-hint" className={FIELD} />
            <p id="find-where-hint" className="text-sm text-slate-700">
              {w.whereHint}
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label htmlFor="find-specialty" className={LABEL}>
                {w.specialty}
              </label>
              <select id="find-specialty" name="specialty" defaultValue={query.specialty} className={FIELD}>
                <option value="">{w.any}</option>
                {(options?.specialties ?? []).map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="find-language" className={LABEL}>
                {w.language}
              </label>
              <select id="find-language" name="language" defaultValue={query.language} className={FIELD}>
                <option value="">{w.any}</option>
                {(options?.languages ?? []).map((l) => (
                  <option key={l} value={l}>
                    {l}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="flex min-h-11 items-center gap-3">
            <input id="find-available" name="available" type="checkbox" value="true" defaultChecked={query.available} className="size-5 accent-brand-700" />
            <label htmlFor="find-available" className="font-medium">
              {w.available}
            </label>
          </div>
          <button type="submit" className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-5 font-semibold text-white hover:bg-brand-800">
            {w.search}
          </button>
        </form>

        <nav aria-label={w.showing} className="flex gap-2">
          {tab("doctors", w.doctors)}
          {tab("clinics", w.clinics)}
        </nav>

        <section aria-labelledby="results-heading" className="space-y-3">
          <h2 id="results-heading" className="sr-only">
            {w.showing}
          </h2>
          {result.status === "failed" && <p role="alert">{w.failed}</p>}
          {result.status === "limited" && <p role="alert">{w.tooMany}</p>}
          {result.status === "invalid" && <p role="alert">{w.badFilter}</p>}
          {(result.status === "doctors" || result.status === "clinics") && result.items.length === 0 && <p>{w.none}</p>}
          {result.status === "doctors" && (
            <ul className="space-y-3">
              {result.items.map((d) => (
                <li key={d.id} className={CARD}>
                  <p className="text-lg font-semibold">{d.display_name}</p>
                  <p className="text-sm text-slate-800">{[d.qualification, d.specialty].filter((p) => p !== null && p !== "").join(" · ")}</p>
                  <p className="text-sm text-slate-800">{[d.clinic.name, d.clinic.city].filter((p) => p !== null && p !== "").join(", ")}</p>
                  {d.languages.length > 0 && (
                    <p className="text-sm text-slate-700">
                      {w.speaks}: {d.languages.join(", ")}
                    </p>
                  )}
                  {d.fee_paise !== null && <p className="text-sm text-slate-700">{w.fee(rupees(d.fee_paise))}</p>}
                  <p className="text-sm font-medium text-emerald-900">
                    {d.next_available === null ? w.noFreeTime : w.freeFrom(shortDay(d.next_available, language))}
                  </p>
                  <Link
                    href={`/c/${encodeURIComponent(d.clinic.slug)}/doctors/${encodeURIComponent(d.id)}?via=directory${language === "hi" ? "&lang=hi" : ""}`}
                    className={LINK}
                  >
                    {w.viewProfile}
                    <span className="sr-only">: {d.display_name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {result.status === "clinics" && (
            <ul className="space-y-3">
              {result.items.map((c) => (
                <li key={c.slug} className={CARD}>
                  <p className="text-lg font-semibold">{c.name}</p>
                  <p className="text-sm text-slate-800">{[c.address_line, c.city, c.pincode].filter((p) => p !== null && p !== "").join(", ")}</p>
                  {c.specialties.length > 0 && <p className="text-sm text-slate-700">{c.specialties.join(", ")}</p>}
                  {c.doctors.length > 0 && <p className="text-sm text-slate-700">{c.doctors.map((d) => d.display_name).join(", ")}</p>}
                  <p className="text-sm font-medium text-emerald-900">
                    {c.next_available === null ? w.noFreeTime : w.freeFrom(shortDay(c.next_available, language))}
                  </p>
                  <Link href={`/c/${encodeURIComponent(c.slug)}?via=directory${language === "hi" ? "&lang=hi" : ""}`} className={LINK}>
                    {w.viewClinic}
                    <span className="sr-only">: {c.name}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="border-t border-slate-200 pt-4 text-sm">
          <Link href="/apply" className="font-medium text-brand-800 underline">
            {w.applyCta}
          </Link>
        </p>
      </main>
    </div>
  );
}
