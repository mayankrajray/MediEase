import Link from "next/link";

import { PLANS, landingWords } from "@/lib/i18n/landing";
import type { PortalLanguage } from "@/lib/i18n/portal";

import { LandingAnalytics } from "./LandingAnalytics";

const SECTION = "mx-auto max-w-5xl space-y-4 px-4 py-10";
const H2 = "text-2xl font-bold tracking-tight text-slate-900";
const CARD = "rounded-card border border-slate-200 bg-white p-5 shadow-card";
const PRIMARY = "inline-flex min-h-12 items-center justify-center rounded-lg bg-brand-700 px-5 text-base font-semibold text-white hover:bg-brand-800";
const SECONDARY =
  "inline-flex min-h-12 items-center justify-center rounded-lg border border-brand-700 bg-white px-5 text-base font-semibold text-brand-900 hover:bg-brand-50";

const rupees = new Intl.NumberFormat("en-IN");

/**
 * The landing page for signed-out visitors (M6c-P8; FR-LND-01..03): the clinic path (problem,
 * features, a screen per role, the 5-minute promise, pricing, *Apply*) and the patient path
 * (*Find a doctor*, the patient app's sign-in with Google). Server-rendered text and links only,
 * with one tiny client component for the PII-free analytics events; English and Hindi; no images,
 * so nothing delays the largest paint. No clinical claims.
 */
export function Landing({ language }: Readonly<{ language: PortalLanguage }>) {
  const w = landingWords(language);
  const other = language === "hi" ? "en" : "hi";
  const q = language === "hi" ? "?lang=hi" : "";

  return (
    <div lang={language} className="min-h-screen bg-canvas text-slate-900">
      <LandingAnalytics lang={language} />
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:rounded focus:bg-white focus:p-2">
        {language === "hi" ? "मुख्य सामग्री पर जाएँ" : "Skip to main content"}
      </a>
      <header className="border-b border-slate-200 bg-white">
        <nav aria-label="MediEase" className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <span className="flex min-h-11 items-center gap-2 text-lg font-bold">
            <span aria-hidden="true" className="grid size-8 place-items-center rounded-xl bg-brand-700 text-sm text-white">
              M
            </span>
            MediEase
          </span>
          <ul className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm font-medium">
            <li>
              <a href="#clinics" className="inline-flex min-h-11 items-center underline-offset-4 hover:underline">
                {w.nav.clinics}
              </a>
            </li>
            <li>
              <a href="#patients" className="inline-flex min-h-11 items-center underline-offset-4 hover:underline">
                {w.nav.patients}
              </a>
            </li>
            <li>
              <a href="#pricing" data-analytics="pricing" className="inline-flex min-h-11 items-center underline-offset-4 hover:underline">
                {w.nav.pricing}
              </a>
            </li>
            <li>
              <Link href="/sign-in" data-analytics="staff_sign_in" className="inline-flex min-h-11 items-center underline-offset-4 hover:underline">
                {w.nav.signIn}
              </Link>
            </li>
            <li>
              <Link
                href={`/?lang=${other}`}
                lang={other}
                aria-label={w.switchLabel}
                data-analytics="language"
                className="inline-flex min-h-11 items-center rounded-lg border border-slate-400 px-3"
              >
                {w.switchTo}
              </Link>
            </li>
          </ul>
        </nav>
      </header>

      <main id="main">
        <section aria-labelledby="hero-heading" className="bg-white">
          <div className="mx-auto max-w-5xl space-y-5 px-4 py-12">
            <h1 id="hero-heading" className="max-w-3xl text-3xl font-bold tracking-tight sm:text-4xl">
              {w.hero.title}
            </h1>
            <p className="max-w-2xl text-lg text-slate-800">{w.hero.body}</p>
            <div className="flex flex-wrap gap-3">
              <Link href="/apply" data-analytics="apply" className={PRIMARY}>
                {w.hero.apply}
              </Link>
              <Link href={`/find${q}`} data-analytics="find" className={SECONDARY}>
                {w.hero.find}
              </Link>
            </div>
          </div>
        </section>

        <section aria-labelledby="problem-heading" className={SECTION}>
          <h2 id="problem-heading" className={H2}>
            {w.problem.title}
          </h2>
          <ul className="grid gap-3 sm:grid-cols-3">
            {w.problem.points.map((p) => (
              <li key={p} className={CARD}>
                {p}
              </li>
            ))}
          </ul>
        </section>

        <section id="clinics" aria-labelledby="clinics-heading" className={SECTION}>
          <h2 id="clinics-heading" className={H2}>
            {w.clinics.title}
          </h2>
          <p className="text-lg font-medium text-emerald-900">{w.clinics.promise}</p>
          <ul className="grid gap-3 sm:grid-cols-2">
            {w.clinics.features.map((f) => (
              <li key={f.title} className={CARD}>
                <h3 className="font-semibold">{f.title}</h3>
                <p className="text-slate-800">{f.body}</p>
              </li>
            ))}
          </ul>
          <h3 className="pt-2 text-xl font-semibold">{w.clinics.rolesTitle}</h3>
          <ul className="grid gap-3 sm:grid-cols-3">
            {w.clinics.roles.map((r) => (
              <li key={r.title} className={`${CARD} border-l-4 border-l-brand-700`}>
                <h4 className="font-semibold">{r.title}</h4>
                <p className="text-slate-800">{r.body}</p>
              </li>
            ))}
          </ul>
          <div className="space-y-2 pt-2">
            <Link href="/apply" data-analytics="apply" className={PRIMARY}>
              {w.clinics.apply}
            </Link>
            <p className="text-slate-800">{w.clinics.demo}</p>
          </div>
        </section>

        <section id="patients" aria-labelledby="patients-heading" className="bg-white">
          <div className={SECTION}>
            <h2 id="patients-heading" className={H2}>
              {w.patients.title}
            </h2>
            <p className="max-w-2xl text-lg text-slate-800">{w.patients.body}</p>
            <div className="flex flex-wrap gap-3">
              <Link href={`/find${q}`} data-analytics="find" className={PRIMARY}>
                {w.patients.find}
              </Link>
              <Link href="/portal/sign-in" data-analytics="patient_sign_in" className={SECONDARY}>
                {w.patients.signIn}
              </Link>
            </div>
            <p role="note" className="max-w-2xl rounded-lg border border-amber-700 bg-amber-50 p-3 text-sm text-amber-950">
              {w.patients.emergency}
            </p>
          </div>
        </section>

        <section id="pricing" aria-labelledby="pricing-heading" className={SECTION}>
          <h2 id="pricing-heading" className={H2}>
            {w.pricing.title}
          </h2>
          <p className="text-slate-800">{w.pricing.note}</p>
          <ul className="grid gap-3 sm:grid-cols-3">
            {PLANS.map((plan) => (
              <li key={plan.id} className={`${CARD} space-y-2`}>
                <h3 className="text-lg font-semibold">{w.pricing.names[plan.id]}</h3>
                <p>
                  <span className="text-3xl font-bold">₹{rupees.format(plan.rupeesPerMonth)}</span> <span className="text-slate-700">{w.pricing.perMonth}</span>
                </p>
                <p className="text-sm font-medium text-emerald-900">{w.pricing.trial}</p>
                <p className="text-slate-800">{w.pricing.includes[plan.id]}</p>
              </li>
            ))}
          </ul>
          <p className="text-slate-800">{w.pricing.noCommission}</p>
        </section>

        <section aria-labelledby="trust-heading" className="bg-white">
          <div className={SECTION}>
            <h2 id="trust-heading" className={H2}>
              {w.trust.title}
            </h2>
            <ul className="list-disc space-y-2 pl-6 text-slate-800">
              {w.trust.points.map((p) => (
                <li key={p}>{p}</li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-labelledby="faq-heading" className={SECTION}>
          <h2 id="faq-heading" className={H2}>
            {w.faq.title}
          </h2>
          <div className="space-y-2">
            {w.faq.items.map((item) => (
              <details key={item.q} className={CARD}>
                <summary className="min-h-6 cursor-pointer font-semibold">{item.q}</summary>
                <p className="pt-2 text-slate-800">{item.a}</p>
              </details>
            ))}
          </div>
        </section>
      </main>

      <footer className="border-t border-slate-200 bg-white">
        <div className="mx-auto flex max-w-5xl flex-wrap gap-x-6 gap-y-2 px-4 py-6 text-sm font-medium">
          <Link href="/apply" data-analytics="apply" className="inline-flex min-h-11 items-center underline">
            {w.footer.apply}
          </Link>
          <Link href={`/find${q}`} data-analytics="find" className="inline-flex min-h-11 items-center underline">
            {w.footer.find}
          </Link>
          <Link href="/sign-in" data-analytics="staff_sign_in" className="inline-flex min-h-11 items-center underline">
            {w.footer.staff}
          </Link>
        </div>
      </footer>
    </div>
  );
}
