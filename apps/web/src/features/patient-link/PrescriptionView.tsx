import type { components } from "@/lib/api/schema";

import { type PageLanguage, type PageStrings } from "./strings";

type Page = components["schemas"]["PatientPrescriptionPage"];

/**
 * The prescription as the patient reads it (spec §6, R11, R20, AC2). A Server Component with no
 * client code: one card per medicine, advice below, a call button. Every word arrives from the
 * API in the page's language; the doctor's text is shown exactly as written.
 */
export function PrescriptionView({
  page,
  strings,
  switchHref,
  saveHref,
}: Readonly<{ page: Page; strings: PageStrings; switchHref: string; saveHref?: string }>) {
  const lang: PageLanguage = page.language;
  return (
    <main lang={lang} className="mx-auto max-w-xl px-4 pb-10 pt-4 text-base leading-relaxed text-slate-900">
      <header className="border-b border-slate-300 pb-3">
        <p className="text-sm">
          <a className="underline" href={switchHref} hrefLang={lang === "hi" ? "en" : "hi"}>
            {strings.switchTo}
          </a>
        </p>
        <h1 className="mt-2 text-xl font-bold">{page.clinic_name}</h1>
        <p className="font-semibold">{page.doctor_name}</p>
        {page.doctor_lines.map((line) => (
          <p key={line} className="text-sm text-slate-700">
            {line}
          </p>
        ))}
        <p className="mt-1 text-sm">
          <span className="font-semibold">{page.issued_on.label}:</span> {page.issued_on.value}
        </p>
      </header>

      {page.updated_note !== null && (
        <p role="status" className="mt-3 rounded border border-amber-700 bg-amber-50 p-2 font-semibold">
          {page.updated_note}
        </p>
      )}

      {page.medicines.length > 0 && (
        <section aria-labelledby="medicines" className="mt-4">
          <h2 id="medicines" className="text-lg font-bold">
            {page.medicines_heading}
          </h2>
          <ol className="mt-2 space-y-3">
            {page.medicines.map((m) => (
              <li key={m.number} className="rounded-card border border-slate-200 p-3">
                <h3 className="font-bold [overflow-wrap:anywhere]">
                  {m.number}. {m.name}
                  {m.form_strength !== null && <span className="font-normal"> ({m.form_strength})</span>}
                </h3>
                <dl className="mt-1">
                  {m.fields.map((f) => (
                    <div key={f.label} className="mt-1">
                      <dt className="text-sm font-semibold text-slate-700">{f.label}</dt>
                      <dd className="[overflow-wrap:anywhere]">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              </li>
            ))}
          </ol>
        </section>
      )}

      {(page.advice.length > 0 || page.advice_notes !== null) && (
        <section aria-labelledby="advice" className="mt-5">
          <h2 id="advice" className="text-lg font-bold">
            {page.advice_heading}
          </h2>
          {page.advice.map((a) => (
            <div key={a.heading} className="mt-2">
              <h3 className="font-semibold">{a.heading}</h3>
              <ul className="list-disc pl-5">
                {a.entries.map((e) => (
                  <li key={e} className="[overflow-wrap:anywhere]">
                    {e}
                  </li>
                ))}
              </ul>
            </div>
          ))}
          {page.advice_notes !== null && (
            <div className="mt-2">
              <h3 className="font-semibold">{page.advice_notes.label}</h3>
              <p className="whitespace-pre-line [overflow-wrap:anywhere]">{page.advice_notes.value}</p>
            </div>
          )}
        </section>
      )}

      {page.follow_up !== null && (
        <p className="mt-5 font-semibold">
          {page.follow_up.label}: {page.follow_up.value}
        </p>
      )}

      {page.clinic_phone_e164 !== null && (
        <p className="mt-5">
          <a
            href={`tel:${page.clinic_phone_e164}`}
            className="inline-block rounded-lg bg-brand-700 px-4 py-3 font-semibold text-white"
          >
            {page.call_label}
          </a>
        </p>
      )}
      <p className="mt-5 text-sm text-slate-700">{strings.askDoctor}</p>
      {saveHref !== undefined && (
        <p className="mt-5 border-t border-slate-300 pt-4 text-sm">
          {strings.saveHelp}{" "}
          <a href={saveHref} className="font-semibold text-brand-800 underline">
            {strings.saveToAccount}
          </a>
        </p>
      )}
    </main>
  );
}
