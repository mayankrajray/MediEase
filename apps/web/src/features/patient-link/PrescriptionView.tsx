import { CalendarClock, CalendarDays, Info, Languages, ListChecks, Phone, Pill, Stethoscope, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { Emblem, Logo } from "@/components/ui/Logo";
import type { components } from "@/lib/api/schema";

import { type PageLanguage, type PageStrings } from "./strings";

type Page = components["schemas"]["PatientPrescriptionPage"];

/** A section heading with its decorative icon. */
function SectionTitle({ id, icon, children }: Readonly<{ id: string; icon: ReactNode; children: ReactNode }>) {
  return (
    <h2 id={id} className="flex items-center gap-2 text-lg font-bold text-slate-900">
      <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700 [&>svg]:size-4">
        {icon}
      </span>
      {children}
    </h2>
  );
}

const CARD = "rounded-card border border-line bg-white p-4 shadow-card";

/**
 * The prescription as the patient reads it (spec §6, R11, R20, AC2). A Server Component with no
 * client code: one card per medicine, advice below, a call button. Every word arrives from the
 * API in the page's language; the doctor's text is shown exactly as written.
 *
 * M7c-P7 (M8): the logo and the language switch in a top bar (the portal has its own header, so
 * embedded shows the switch only); the clinic and doctor as the first card with the date; each
 * medicine a numbered card; the schedule's times as chips; *Call the clinic* full width on a
 * phone. The icons are inline SVG rendered on the server: still no client code.
 */
export function PrescriptionView({
  page,
  strings,
  switchHref,
  saveHref,
  embedded = false,
}: Readonly<{
  page: Page;
  strings: PageStrings;
  switchHref: string;
  saveHref?: string;
  /** Inside the portal's own `main` (M6b-P2): an `article`, so the page has one main landmark. */
  embedded?: boolean;
}>) {
  const lang: PageLanguage = page.language;
  const Root = embedded ? "article" : "main";
  return (
    <Root lang={lang} className={`mx-auto max-w-xl space-y-5 px-4 pb-10 text-base leading-relaxed text-slate-900 ${embedded ? "pt-4" : "pt-3"}`}>
      <div className={`flex items-center gap-3 ${embedded ? "justify-end" : "justify-between"}`}>
        {!embedded && <Logo />}
        <a
          className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-sm font-semibold text-slate-900 hover:border-brand-300 hover:bg-brand-50"
          href={switchHref}
          hrefLang={lang === "hi" ? "en" : "hi"}
        >
          <Languages aria-hidden="true" className="size-4 text-brand-700" />
          {strings.switchTo}
        </a>
      </div>

      <header className={`${CARD} space-y-2`}>
        <h1 className="text-xl font-bold text-balance">{page.clinic_name}</h1>
        <div className="flex items-start gap-2.5">
          <Stethoscope aria-hidden="true" className="mt-1 size-4 shrink-0 text-brand-700" />
          <div className="min-w-0">
            <p className="font-semibold">{page.doctor_name}</p>
            {page.doctor_lines.map((line) => (
              <p key={line} className="text-sm text-slate-700 [overflow-wrap:anywhere]">
                {line}
              </p>
            ))}
          </div>
        </div>
        <p className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-sm">
          <CalendarDays aria-hidden="true" className="size-4 text-slate-600" />
          <span className="font-semibold">{page.issued_on.label}:</span> {page.issued_on.value}
        </p>
      </header>

      {page.updated_note !== null && (
        <p role="status" className="flex items-start gap-2 rounded-card border border-warning-line bg-warning-soft p-3 font-semibold">
          <TriangleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-warning" />
          <span>{page.updated_note}</span>
        </p>
      )}

      {page.medicines.length > 0 && (
        <section aria-labelledby="medicines" className="space-y-3">
          <SectionTitle id="medicines" icon={<Pill />}>
            {page.medicines_heading}
          </SectionTitle>
          <ol className="space-y-3">
            {page.medicines.map((m) => (
              <li key={m.number} className={CARD}>
                <div className="flex items-start gap-3">
                  <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-full bg-brand-700 text-sm font-bold text-white">
                    {m.number}
                  </span>
                  <h3 className="min-w-0 pt-0.5 text-lg font-bold leading-snug [overflow-wrap:anywhere]">
                    <span className="sr-only">{m.number}. </span>
                    {m.name}
                    {m.form_strength !== null && <span className="font-normal"> ({m.form_strength})</span>}
                  </h3>
                </div>
                <dl className="mt-3 divide-y divide-line border-t border-line">
                  {m.fields.map((f) => (
                    <div key={f.label} className="py-2 last:pb-0">
                      <dt className="text-sm font-semibold text-slate-600">{f.label}</dt>
                      <dd className="[overflow-wrap:anywhere]">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ol>
        </section>
      )}

      {page.schedule.length > 0 && (
        <section aria-labelledby="schedule" className="space-y-3">
          <SectionTitle id="schedule" icon={<CalendarClock />}>
            {page.schedule_heading}
          </SectionTitle>
          {/* M6b-P3 (prescriptions R25): the API's engine marks the times of day; nothing here reads a frequency. */}
          <ul className="space-y-2">
            {page.schedule.map((row) => (
              <li key={row.number} className={`${CARD} space-y-2`}>
                <p className="font-semibold [overflow-wrap:anywhere]">
                  {row.number}. {row.name}
                  {row.dose !== null && <span className="font-normal"> ({row.dose})</span>}
                </p>
                {row.as_written !== null ? (
                  <p>
                    <span className="font-semibold">{page.schedule_as_written}:</span> {row.as_written}
                  </p>
                ) : (
                  <p className="flex flex-wrap gap-1.5">
                    {row.marks.map((marked, i) =>
                      marked ? (
                        <span key={i} className="rounded-full bg-brand-50 px-3 py-1 text-sm font-semibold text-brand-900 ring-1 ring-inset ring-brand-200">
                          {page.schedule_columns[i]}
                        </span>
                      ) : null,
                    )}
                  </p>
                )}
                <p className="text-sm text-slate-700 [overflow-wrap:anywhere]">{[row.timing, row.how, row.duration].filter((n) => n !== null).join(" · ")}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {(page.advice.length > 0 || page.advice_notes !== null) && (
        <section aria-labelledby="advice" className="space-y-3">
          <SectionTitle id="advice" icon={<ListChecks />}>
            {page.advice_heading}
          </SectionTitle>
          <div className={`${CARD} space-y-3`}>
            {page.advice.map((a) => (
              <div key={a.heading}>
                <h3 className="font-semibold">{a.heading}</h3>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 marker:text-brand-600">
                  {a.entries.map((e) => (
                    <li key={e} className="[overflow-wrap:anywhere]">
                      {e}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {page.advice_notes !== null && (
              <div>
                <h3 className="font-semibold">{page.advice_notes.label}</h3>
                <p className="whitespace-pre-line [overflow-wrap:anywhere]">{page.advice_notes.value}</p>
              </div>
            )}
          </div>
        </section>
      )}

      {page.follow_up !== null && (
        <p className="flex items-center gap-2 rounded-card border border-brand-200 bg-brand-50 p-3 font-semibold text-brand-900">
          <CalendarClock aria-hidden="true" className="size-5 shrink-0" />
          <span>
            {page.follow_up.label}: {page.follow_up.value}
          </span>
        </p>
      )}

      {page.clinic_phone_e164 !== null && (
        <p>
          <a
            href={`tel:${page.clinic_phone_e164}`}
            className="flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-brand-700 px-5 font-semibold text-white shadow-sm hover:bg-brand-800 sm:inline-flex sm:w-auto"
          >
            <Phone aria-hidden="true" className="size-5" />
            {page.call_label}
          </a>
        </p>
      )}
      <p className="flex items-start gap-2 text-sm text-slate-700">
        <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
        <span>{strings.askDoctor}</span>
      </p>
      {saveHref !== undefined && (
        <div className={`${CARD} flex items-start gap-3`}>
          <Emblem className="size-9" />
          <p className="text-sm text-slate-800">
            {strings.saveHelp}{" "}
            <a href={saveHref} className="font-semibold text-brand-800 underline underline-offset-4">
              {strings.saveToAccount}
            </a>
          </p>
        </div>
      )}
    </Root>
  );
}
