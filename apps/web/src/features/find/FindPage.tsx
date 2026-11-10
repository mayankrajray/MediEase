import { CalendarCheck, ChevronRight, CircleAlert, Languages, MapPin, Search, SearchX, TriangleAlert } from "lucide-react";
import Link from "next/link";

import { Avatar } from "@/components/ui/Avatar";
import { Logo } from "@/components/ui/Logo";
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

// Server-rendered: the field styles are written here (the client `Field` module's constants are
// client references in a Server Component). They match `INPUT` and `LABEL` (M7c-P7, M6).
const FIELD =
  "mt-1.5 min-h-11 w-full rounded-lg border border-slate-400 bg-white px-3 text-base text-slate-900 transition-colors hover:border-slate-600 focus-visible:border-brand-700 focus-visible:outline-brand-700";
const LABEL = "block text-sm font-semibold text-slate-900";
const CARD = "rounded-card border border-line bg-surface p-4 shadow-card sm:p-5";
const LINK =
  "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-brand-300 bg-brand-50 px-4 font-semibold text-brand-900 transition-colors hover:border-brand-700 hover:bg-brand-100 max-sm:w-full";

/**
 * Directory search (M6c-P6; FR-DIS-01, 02, 04, 05; spec discovery R1-R10): one plain GET form that
 * works without JavaScript, then doctors or clinics in the API's order. Rendered on the server,
 * English or Hindi, 360 px first. A result opens the profile, where the patient picks a time (P7).
 *
 * M7c-P7 (M6): the form as one card with the main search first and the filters under it; Doctors
 * and Clinics as a segmented switch; each result a card with initials, the clinic and place, a
 * "free from" line with an icon, and the profile as a full-width button on a phone.
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
      className={`inline-flex min-h-11 flex-1 items-center justify-center rounded-md px-4 font-semibold transition-colors sm:flex-none ${query.kind === kind ? "bg-brand-700 text-white" : "text-slate-700 hover:bg-slate-100"}`}
    >
      {label}
    </Link>
  );
  const switchQuery = new URLSearchParams(findHref(query, other).split("?")[1] ?? "");
  if (other === "en") switchQuery.set("lang", "en");
  const free = (next: string | null) => (
    <p className={`flex items-center gap-1.5 text-sm font-medium ${next === null ? "text-slate-700" : "text-success"}`}>
      <CalendarCheck aria-hidden="true" className="size-4 shrink-0" />
      {next === null ? w.noFreeTime : w.freeFrom(shortDay(next, language))}
    </p>
  );

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link href={language === "hi" ? "/?lang=hi" : "/"} className="flex min-h-11 items-center">
            <Logo />
          </Link>
          <Link
            href={`/find?${switchQuery.toString()}`}
            lang={other}
            aria-label={w.switchLabel}
            className="inline-flex min-h-11 items-center gap-2 rounded-lg border border-slate-300 bg-surface px-3 text-sm font-semibold text-slate-900 transition-colors hover:border-brand-300 hover:bg-brand-50"
          >
            <Languages aria-hidden="true" className="size-4" />
            {w.switchTo}
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-10 pt-5">
        <div className="space-y-1">
          <h1 className="heading-4 text-slate-900">{w.title}</h1>
          <p className="text-pretty text-slate-700">{w.intro}</p>
        </div>
        <p role="note" className="flex gap-2 rounded-xl border border-warning-line bg-warning-soft p-3 text-sm text-slate-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>{w.emergency}</span>
        </p>

        <form method="get" action="/find" role="search" className={`${CARD} space-y-4`}>
          {query.kind === "clinics" && <input type="hidden" name="type" value="clinics" />}
          {language === "hi" && <input type="hidden" name="lang" value="hi" />}
          <div>
            <label htmlFor="find-q" className={LABEL}>
              {w.what}
            </label>
            <div className="relative">
              <input id="find-q" name="q" type="search" defaultValue={query.q} maxLength={100} aria-describedby="find-q-hint" className={`${FIELD} pl-9`} />
              <Search aria-hidden="true" className="pointer-events-none absolute left-3 top-[1.6rem] size-4 text-slate-500" />
            </div>
            <p id="find-q-hint" className="mt-1 text-sm text-slate-700">
              {w.whatHint}
            </p>
          </div>
          <div>
            <label htmlFor="find-where" className={LABEL}>
              {w.where}
            </label>
            <div className="relative">
              <input id="find-where" name="where" defaultValue={query.where} maxLength={100} aria-describedby="find-where-hint" className={`${FIELD} pl-9`} />
              <MapPin aria-hidden="true" className="pointer-events-none absolute left-3 top-[1.6rem] size-4 text-slate-500" />
            </div>
            <p id="find-where-hint" className="mt-1 text-sm text-slate-700">
              {w.whereHint}
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="find-specialty" className={LABEL}>
                {w.specialty}
              </label>
              <select id="find-specialty" name="specialty" defaultValue={query.specialty} className={`${FIELD} cursor-pointer`}>
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
              <select id="find-language" name="language" defaultValue={query.language} className={`${FIELD} cursor-pointer`}>
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
            <input id="find-available" name="available" type="checkbox" value="true" defaultChecked={query.available} className="size-5 cursor-pointer accent-brand-700" />
            <label htmlFor="find-available" className="cursor-pointer font-medium text-slate-900">
              {w.available}
            </label>
          </div>
          <button
            type="submit"
            className="inline-flex min-h-12 w-full cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand-700 px-5 font-semibold text-white transition-colors hover:bg-brand-800 sm:w-auto"
          >
            <Search aria-hidden="true" className="size-4" />
            {w.search}
          </button>
        </form>

        <nav aria-label={w.showing} className="flex gap-1 rounded-lg border border-line bg-surface p-1 shadow-card sm:inline-flex">
          {tab("doctors", w.doctors)}
          {tab("clinics", w.clinics)}
        </nav>

        <section aria-labelledby="results-heading" className="space-y-3">
          <h2 id="results-heading" className="sr-only">
            {w.showing}
          </h2>
          {result.status === "failed" && <Problem>{w.failed}</Problem>}
          {result.status === "limited" && <Problem>{w.tooMany}</Problem>}
          {result.status === "invalid" && <Problem>{w.badFilter}</Problem>}
          {(result.status === "doctors" || result.status === "clinics") && result.items.length === 0 && (
            <p className="flex flex-col items-center gap-2 rounded-card border border-dashed border-slate-300 bg-surface px-4 py-8 text-center text-slate-700">
              <SearchX aria-hidden="true" className="size-6 text-slate-500" />
              {w.none}
            </p>
          )}
          {result.status === "doctors" && (
            <ul className="space-y-3">
              {result.items.map((d) => (
                <li key={d.id} className={`${CARD} space-y-3`}>
                  <div className="flex items-start gap-3">
                    <Avatar name={d.display_name} />
                    <div className="min-w-0 flex-1 space-y-0.5">
                      <p className="break-words text-lg font-semibold text-slate-900">{d.display_name}</p>
                      <p className="text-sm text-slate-800">{[d.qualification, d.specialty].filter((p) => p !== null && p !== "").join(" · ")}</p>
                      <p className="text-sm text-slate-800">{[d.clinic.name, d.clinic.city].filter((p) => p !== null && p !== "").join(", ")}</p>
                    </div>
                  </div>
                  <div className="space-y-1">
                    {d.languages.length > 0 && (
                      <p className="text-sm text-slate-700">
                        {w.speaks}: {d.languages.join(", ")}
                      </p>
                    )}
                    {d.fee_paise !== null && <p className="text-sm text-slate-700">{w.fee(rupees(d.fee_paise))}</p>}
                    {free(d.next_available)}
                  </div>
                  <Link
                    href={`/c/${encodeURIComponent(d.clinic.slug)}/doctors/${encodeURIComponent(d.id)}?via=directory${language === "hi" ? "&lang=hi" : ""}`}
                    className={LINK}
                  >
                    {w.viewProfile}
                    <span className="sr-only">: {d.display_name}</span>
                    <ChevronRight aria-hidden="true" className="size-4" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {result.status === "clinics" && (
            <ul className="space-y-3">
              {result.items.map((c) => (
                <li key={c.slug} className={`${CARD} space-y-3`}>
                  <div className="space-y-0.5">
                    <p className="break-words text-lg font-semibold text-slate-900">{c.name}</p>
                    <p className="text-sm text-slate-800">{[c.address_line, c.city, c.pincode].filter((p) => p !== null && p !== "").join(", ")}</p>
                    {c.specialties.length > 0 && <p className="text-sm text-slate-700">{c.specialties.join(", ")}</p>}
                    {c.doctors.length > 0 && <p className="text-sm text-slate-700">{c.doctors.map((d) => d.display_name).join(", ")}</p>}
                  </div>
                  {free(c.next_available)}
                  <Link href={`/c/${encodeURIComponent(c.slug)}?via=directory${language === "hi" ? "&lang=hi" : ""}`} className={LINK}>
                    {w.viewClinic}
                    <span className="sr-only">: {c.name}</span>
                    <ChevronRight aria-hidden="true" className="size-4" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>

        <p className="border-t border-line pt-4 text-sm">
          <Link href="/apply" className="inline-flex min-h-11 items-center font-semibold text-brand-800 underline underline-offset-2">
            {w.applyCta}
          </Link>
        </p>
      </main>
    </div>
  );
}

/** A search that could not run, in the danger tone; the words say what to do. */
function Problem({ children }: Readonly<{ children: string }>) {
  return (
    <p role="alert" className="flex gap-2 rounded-xl border border-danger-line bg-danger-soft p-3 font-medium text-slate-900">
      <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
      <span>{children}</span>
    </p>
  );
}