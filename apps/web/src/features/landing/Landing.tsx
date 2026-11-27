import {
  ArrowUpRight,
  BellRing,
  CalendarClock,
  Check,
  ClipboardList,
  FileText,
  Inbox,
  Languages,
  LockKeyhole,
  ShieldCheck,
  Stethoscope,
  UserRound,
} from "lucide-react";
import Link from "next/link";
import { Fragment, type ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { buttonClasses } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { Emblem, Logo } from "@/components/ui/Logo";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { PLANS, landingWords, type LandingWords } from "@/lib/i18n/landing";
import type { PortalLanguage } from "@/lib/i18n/portal";

import { LandingAnalytics } from "./LandingAnalytics";
import { LandingMotion } from "./LandingMotion";

// Up to 1440 px wide with a 48 px margin at each side from laptop width up, so the sections use most
// of the screen but keep some breathing room.
const WRAP = "mx-auto w-full max-w-[90rem] px-4 sm:px-6 lg:px-12";
const SECTION = "py-16 sm:py-24";
const CARD = "rounded-2xl border border-line bg-surface p-6 shadow-card";
const NAV_LINK =
  "inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-slate-700 transition-colors duration-200 ease-brand hover:bg-slate-100 hover:text-slate-900";

const LANG_PILL =
  "inline-flex h-10 items-center gap-1.5 rounded-full border border-line px-3.5 text-sm font-medium text-slate-700 transition-colors duration-200 ease-brand hover:bg-slate-100 hover:text-slate-900";
/** Each language's own name, for the language pill (the page switches to this language). */
const LANGUAGE_NAME = { en: "English", hi: "हिंदी" } as const;

const FEATURE_ICONS = [CalendarClock, FileText, Inbox, BellRing] as const;
const ROLE_ICONS = [UserRound, Stethoscope, ClipboardList] as const;
const TRUST_ICONS = [ShieldCheck, LockKeyhole, FileText, Check] as const;

const rupees = new Intl.NumberFormat("en-IN");

/**
 * The landing page for signed-out visitors (M6c-P8; FR-LND-01..03), redesigned in M7c-P7 (M1)
 * with the design system and the landing-page-design skill: one primary action for clinics
 * (*Apply*), the patient path (*Find a doctor*) as its own section, the argument in order (problem,
 * the tagline, benefits, how joining works, a screen per role), then pricing, trust, questions
 * and the final call to action. Server-rendered, English and Hindi, no images and no animation
 * library: motion is a few hundred bytes of client code (`LandingMotion`) and CSS. No clinical
 * claims, no partner names or quotes (PRODUCT.md).
 */
export function Landing({ language }: Readonly<{ language: PortalLanguage }>) {
  const w = landingWords(language);
  const other = language === "hi" ? "en" : "hi";
  const q = language === "hi" ? "?lang=hi" : "";

  return (
    <div lang={language} className={cx(BRAND_FONT, "min-h-screen bg-canvas text-slate-900")}>
      <LandingAnalytics lang={language} />
      <LandingMotion />
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-white focus:p-2">
        {w.skip}
      </a>

      <Header w={w} other={other} />

      <main id="main">
        <Hero w={w} q={q} />

        <section aria-labelledby="problem-heading" className={SECTION} data-reveal>
          <div className={WRAP}>
            <h2 id="problem-heading" className="heading-4 max-w-2xl">
              {w.problem.title}
            </h2>
            <ul className="mt-8 grid gap-4 sm:grid-cols-3">
              {w.problem.points.map((p, i) => (
                <li key={p} className={CARD}>
                  <span aria-hidden="true" className="text-sm font-semibold text-brand-800" data-numeric>
                    0{i + 1}
                  </span>
                  <p className="mt-3 text-pretty text-lg text-slate-800">{p}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section aria-label={w.tagline.join(" ")} className="bg-surface py-20 sm:py-28">
          <div className={WRAP}>
            <p data-words className="heading-2 max-w-[680px]">
              {w.tagline.map((line) => (
                <span key={line} className="block">
                  {line.split(" ").map((word, i) => (
                    <span key={`${word}-${i}`} data-word="">
                      {word}{" "}
                    </span>
                  ))}
                </span>
              ))}
            </p>
          </div>
        </section>

        <section id="clinics" aria-labelledby="clinics-heading" className={SECTION} data-reveal>
          <div className={WRAP}>
            <h2 id="clinics-heading" className="heading-4 max-w-2xl">
              {w.clinics.title}
            </h2>
            <p className="mt-3 max-w-2xl text-pretty text-lg text-slate-700">{w.clinics.promise}</p>
            <ul className="mt-10 grid gap-4 sm:grid-cols-2">
              {w.clinics.features.map((f, i) => {
                const Icon = FEATURE_ICONS[i % FEATURE_ICONS.length] ?? CalendarClock;
                return (
                  <li key={f.title} className={cx(CARD, "transition duration-300 ease-brand hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-pop motion-reduce:hover:translate-y-0")}>
                    <IconTile>
                      <Icon className="size-5" />
                    </IconTile>
                    <h3 className="mt-4 text-lg font-semibold">{f.title}</h3>
                    <p className="mt-1 text-pretty text-slate-700">{f.body}</p>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section aria-labelledby="how-heading" className="bg-surface py-16 sm:py-24" data-reveal>
          <div className={WRAP}>
            <h2 id="how-heading" className="heading-4">
              {w.how.title}
            </h2>
            <ol className="mt-10 grid gap-6 sm:grid-cols-3">
              {w.how.steps.map((step, i) => (
                <li key={step.title} className="relative">
                  <span aria-hidden="true" className="grid size-10 place-items-center rounded-full bg-brand-700 font-semibold text-white" data-numeric>
                    {i + 1}
                  </span>
                  <h3 className="mt-4 text-lg font-semibold">{step.title}</h3>
                  <p className="mt-1 text-pretty text-slate-700">{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section aria-labelledby="roles-heading" className={SECTION} data-reveal>
          <div className={WRAP}>
            <h2 id="roles-heading" className="heading-4">
              {w.clinics.rolesTitle}
            </h2>
            <ul className="mt-8 grid gap-4 sm:grid-cols-3">
              {w.clinics.roles.map((r, i) => {
                const Icon = ROLE_ICONS[i % ROLE_ICONS.length] ?? UserRound;
                return (
                  <li key={r.title} className={CARD}>
                    <IconTile>
                      <Icon className="size-5" />
                    </IconTile>
                    <h3 className="mt-4 text-lg font-semibold">{r.title}</h3>
                    <p className="mt-1 text-pretty text-slate-700">{r.body}</p>
                  </li>
                );
              })}
            </ul>
            <div className="mt-10 flex flex-wrap items-center gap-4">
              <Link prefetch={false} href="/apply" data-analytics="apply" className={buttonClasses("primary", "lg")}>
                {w.clinics.apply}
              </Link>
              <p className="max-w-md text-pretty text-slate-700">{w.clinics.demo}</p>
            </div>
          </div>
        </section>

        <section id="patients" aria-labelledby="patients-heading" className="bg-surface py-16 sm:py-24" data-reveal>
          <div className={cx(WRAP, "grid gap-10 lg:grid-cols-2 lg:items-center")}>
            <div>
              <h2 id="patients-heading" className="heading-4">
                {w.patients.title}
              </h2>
              <p className="mt-3 max-w-xl text-pretty text-lg text-slate-700">{w.patients.body}</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link prefetch={false} href={`/find${q}`} data-analytics="find" className={buttonClasses("primary", "lg")}>
                  {w.patients.find}
                </Link>
                <Link prefetch={false} href="/portal/sign-in" data-analytics="patient_sign_in" className={buttonClasses("secondary", "lg")}>
                  {w.patients.signIn}
                </Link>
              </div>
            </div>
            <p role="note" className="rounded-2xl border border-warning-line bg-warning-soft p-6 text-pretty text-warning">
              <span className="block font-semibold text-slate-900">{language === "hi" ? "ध्यान दें" : "Please note"}</span>
              <span className="mt-1 block text-slate-800">{w.patients.emergency}</span>
            </p>
          </div>
        </section>

        <section id="pricing" aria-labelledby="pricing-heading" className={SECTION} data-reveal>
          <div className={WRAP}>
            <h2 id="pricing-heading" className="heading-4">
              {w.pricing.title}
            </h2>
            <p className="mt-3 max-w-2xl text-pretty text-lg text-slate-700">{w.pricing.note}</p>
            <ul className="mt-10 grid gap-4 md:grid-cols-3">
              {PLANS.map((plan) => (
                <li key={plan.id} className={cx(CARD, "flex flex-col gap-3", plan.id === "clinic" && "border-brand-200 ring-1 ring-brand-200")}>
                  <h3 className="text-lg font-semibold">{w.pricing.names[plan.id]}</h3>
                  <p className="flex items-baseline gap-1.5">
                    <span className="text-4xl font-bold tracking-tight" data-numeric>
                      ₹{rupees.format(plan.rupeesPerMonth)}
                    </span>
                    <span className="text-slate-700">{w.pricing.perMonth}</span>
                  </p>
                  <p className="w-fit">
                    <StatusBadge tone="done">{w.pricing.trial}</StatusBadge>
                  </p>
                  <p className="text-pretty text-slate-700">{w.pricing.includes[plan.id]}</p>
                </li>
              ))}
            </ul>
            <p className="mt-6 max-w-3xl text-pretty text-slate-700">{w.pricing.noCommission}</p>
          </div>
        </section>

        <section aria-labelledby="trust-heading" className="bg-surface py-16 sm:py-24" data-reveal>
          <div className={WRAP}>
            <h2 id="trust-heading" className="heading-4">
              {w.trust.title}
            </h2>
            <ul className="mt-8 grid gap-x-8 gap-y-6 sm:grid-cols-2">
              {w.trust.points.map((p, i) => {
                const Icon = TRUST_ICONS[i % TRUST_ICONS.length] ?? Check;
                return (
                  <li key={p} className="flex gap-4">
                    <IconTile>
                      <Icon className="size-5" />
                    </IconTile>
                    <p className="text-pretty pt-2 text-slate-800">{p}</p>
                  </li>
                );
              })}
            </ul>
          </div>
        </section>

        <section aria-labelledby="faq-heading" className={SECTION} data-reveal>
          <div className={cx(WRAP, "grid gap-10 lg:grid-cols-[1fr_2fr]")}>
            <h2 id="faq-heading" className="heading-4">
              {w.faq.title}
            </h2>
            <div className="divide-y divide-line rounded-2xl border border-line bg-surface">
              {w.faq.items.map((item) => (
                <details key={item.q} className="group px-6 py-1">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between gap-4 font-semibold [&::-webkit-details-marker]:hidden">
                    {item.q}
                    <span aria-hidden="true" className="grid size-7 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-800 transition-transform duration-300 ease-brand group-open:rotate-45 motion-reduce:transition-none">
                      +
                    </span>
                  </summary>
                  <p className="pb-5 text-pretty text-slate-700">{item.a}</p>
                </details>
              ))}
            </div>
          </div>
        </section>

        <section aria-labelledby="final-heading" className="pb-16 sm:pb-24" data-reveal>
          <div className={WRAP}>
            <div className="rounded-3xl bg-brand-900 px-6 py-12 text-center text-white sm:px-12 sm:py-16">
              <h2 id="final-heading" className="heading-4 mx-auto max-w-2xl text-white">
                {w.final.title}
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-pretty text-lg text-brand-100">{w.final.body}</p>
              <div className="mt-8 flex justify-center">
                <Link prefetch={false}
                  href="/apply"
                  data-analytics="apply"
                  className={cx(buttonClasses("secondary", "lg"), "border-white hover:border-white hover:bg-brand-50")}
                >
                  {w.hero.apply}
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <Footer w={w} q={q} />
    </div>
  );
}

/** A title's sentences, each kept with its full stop (English "." or Hindi "।"). */
function sentences(text: string): string[] {
  return text.split(/(?<=[.।])\s+/).filter(Boolean);
}

function IconTile({ children }: { children: ReactNode }) {
  return (
    <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-100">
      {children}
    </span>
  );
}

/**
 * A solid, full-width bar (B7): the logo and section links on the left; the language pill, staff
 * sign-in and Apply on the right. Below desktop width the rest moves into a full-screen menu built
 * on <details> (no script needed to open it); Apply stays in the bar from tablet width up.
 */
function Header({ w, other }: { w: LandingWords; other: "en" | "hi" }) {
  const links = [
    { href: "#clinics", label: w.nav.clinics },
    { href: "#patients", label: w.nav.patients },
    { href: "#pricing", label: w.nav.pricing, analytics: "pricing" },
  ];
  return (
    <header className="sticky top-0 z-40">
      {/* No backdrop-filter on the bar: it would make the bar the containing block of the menu's
          `position: fixed` panel, which would then be clipped to the bar. */}
      <nav aria-label="MediEase" className="me-landing-nav border-b border-line bg-surface">
        {/* The bar and its contents span the viewport: logo at the left edge, actions at the right. */}
        <div className="flex h-16 items-center gap-2 px-4 sm:px-6 lg:px-8">
          <Link prefetch={false} href={other === "hi" ? "/" : "/?lang=hi"} className="inline-flex min-h-11 shrink-0 items-center rounded-lg pr-2">
            <Logo />
          </Link>
          <ul className="ml-4 hidden items-center gap-1 lg:flex">
            {links.map((l) => (
              <li key={l.href}>
                <a href={l.href} {...(l.analytics === undefined ? {} : { "data-analytics": l.analytics })} className={NAV_LINK}>
                  {l.label}
                </a>
              </li>
            ))}
          </ul>
          <div className="ml-auto flex items-center gap-1 sm:gap-2">
            {/* Wrappers hide these on smaller screens: a link's own inline-flex would beat `hidden`
                (cx does not merge classes). The phone menu has all three; on a phone the bar is
                only the logo and Menu (the developer's review, e2e/landing.spec.ts). */}
            <span className="hidden lg:block">
              <Link prefetch={false} href={`/?lang=${other}`} lang={other} aria-label={w.switchLabel} data-analytics="language" className={LANG_PILL}>
                <Languages aria-hidden="true" className="size-4" />
                {LANGUAGE_NAME[other]}
              </Link>
            </span>
            <span className="hidden lg:block">
              <Link prefetch={false} href="/sign-in" data-analytics="staff_sign_in" className={NAV_LINK}>
                <UserRound aria-hidden="true" className="mr-1.5 size-4" />
                {w.nav.signIn}
              </Link>
            </span>
            <span className="hidden sm:block">
              <Link prefetch={false} href="/apply" data-analytics="apply" className={cx(buttonClasses("primary", "sm"), "whitespace-nowrap")}>
                {w.footer.apply}
              </Link>
            </span>
            <details className="lg:hidden">
              <summary
                aria-label={w.menu.label}
                className="flex min-h-11 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-sm font-semibold text-slate-900 hover:bg-slate-100 [&::-webkit-details-marker]:hidden"
              >
                <span aria-hidden="true" className="me-menu-icon flex w-4 flex-col gap-1">
                  <span className="block h-0.5 w-4 rounded bg-current" />
                  <span className="block h-0.5 w-4 rounded bg-current" />
                  <span className="block h-0.5 w-4 rounded bg-current" />
                </span>
                {w.menu.open}
              </summary>
              {/* Starts right under the bar: 4rem tall plus its 1px bottom border. */}
              <div className="me-menu-panel fixed inset-x-0 bottom-0 top-[calc(4rem+1px)] z-30 overflow-y-auto overscroll-contain bg-surface px-4 py-6 sm:px-6">
                <ul className="space-y-1 text-lg">
                  {links.map((l, i) => (
                    <li key={l.href} style={{ ["--i" as string]: i }}>
                      <a href={l.href} className="flex min-h-12 items-center rounded-lg px-3 font-semibold hover:bg-slate-100">
                        {l.label}
                      </a>
                    </li>
                  ))}
                  <li style={{ ["--i" as string]: 3 }}>
                    <Link prefetch={false} href="/sign-in" className="flex min-h-12 items-center rounded-lg px-3 font-semibold hover:bg-slate-100">
                      {w.nav.signIn}
                    </Link>
                  </li>
                  <li style={{ ["--i" as string]: 4 }}>
                    <Link prefetch={false} href={`/?lang=${other}`} lang={other} className="flex min-h-12 items-center rounded-lg px-3 font-semibold hover:bg-slate-100">
                      {w.switchTo}
                    </Link>
                  </li>
                  <li style={{ ["--i" as string]: 5 }} className="pt-4">
                    <Link prefetch={false} href="/apply" className={cx(buttonClasses("primary", "lg"), "w-full")}>
                      {w.hero.apply}
                    </Link>
                  </li>
                </ul>
              </div>
            </details>
          </div>
        </div>
      </nav>
    </header>
  );
}

function Hero({ w, q }: { w: LandingWords; q: string }) {
  const lines = sentences(w.hero.title);
  return (
    <section aria-labelledby="hero-heading" className="overflow-hidden bg-brand-50">
      <div className={cx(WRAP, "pb-16 pt-12 sm:pb-20 sm:pt-16 lg:pt-20")}>
        {/* A small line above the headline, like a magazine's kicker. Letter spacing would break
            Devanagari's joined letters apart, so Hindi keeps normal spacing. */}
        <p className="inline-flex items-center gap-2.5 text-xs font-bold uppercase tracking-[0.18em] text-brand-900 sm:text-sm [&:lang(hi)]:tracking-normal">
          <span aria-hidden="true" className="size-2 rounded-full bg-brand-600" />
          {w.footerMore.tagline}
        </p>
        <div className="mt-6 grid items-end gap-10 lg:mt-8 lg:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)] lg:gap-14">
          {/* B5: one sentence a line, wrapping into balanced halves at display sizes (44 px on a
              phone to 96 px on a wide desktop); Devanagari gets more line height for its marks. */}
          <h1
            id="hero-heading"
            className="text-[clamp(2.75rem,6vw,6rem)] font-extrabold leading-[0.98] tracking-[-0.035em] text-balance text-brand-900 [&:lang(hi)]:leading-[1.25] [&:lang(hi)]:tracking-normal"
          >
            {lines.map((s, i) => (
              <Fragment key={s}>
                {/* Between the lines, so the heading's name reads "organised. Your" with a space. */}
                {i > 0 && " "}
                <span className="block">
                  <HeadlineSentence text={s} last={i === lines.length - 1} />
                </span>
              </Fragment>
            ))}
          </h1>
          <div className="lg:pb-3">
            <p className="max-w-xl text-pretty text-lg text-slate-700 sm:text-xl">{w.hero.body}</p>
            <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-4">
              <Link prefetch={false} href="/apply" data-analytics="apply" className={cx(buttonClasses("primary", "lg"), "gap-2")}>
                {w.hero.apply}
                <ArrowUpRight aria-hidden="true" className="size-5" />
              </Link>
              {/* Feedback: the colour deepens on hover, and on press the link grows and turns a
                  lighter teal (brand-700, 4.7:1 on the mint); no movement with "reduce motion". */}
              <Link
                prefetch={false}
                href={`/find${q}`}
                data-analytics="find"
                className="inline-flex min-h-12 origin-left items-center font-semibold text-brand-800 underline-offset-4 transition duration-150 ease-brand hover:text-brand-950 hover:underline active:scale-110 active:text-brand-700 motion-reduce:transition-none motion-reduce:active:scale-100"
              >
                {w.hero.find}
                <span aria-hidden="true" className="ml-1">
                  →
                </span>
              </Link>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-slate-700">
              {w.proof.map((p) => (
                <li key={p} className="inline-flex items-center gap-2">
                  <Check aria-hidden="true" className="size-4 text-brand-700" />
                  {p}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

/**
 * One headline sentence. An English full stop is drawn as a small square, the last one in the
 * brand's mint. The real "." stays in the text, inline and transparent, so the heading's accessible
 * name is exactly its text ("organised.", not "organised ."); the square sits on the baseline
 * (Manrope's descent is 0.3 em). Hindi keeps its own "।".
 */
function HeadlineSentence({ text, last }: { text: string; last: boolean }) {
  if (!text.endsWith(".")) return <>{text}</>;
  return (
    <>
      {text.slice(0, -1)}
      <span className="relative text-transparent">
        .
        <span
          aria-hidden="true"
          className={cx("absolute bottom-[0.3em] left-[0.05em] size-[0.17em]", last ? "bg-brand-400" : "bg-brand-900")}
        />
      </span>
    </>
  );
}

function Footer({ w, q }: { w: LandingWords; q: string }) {
  const f = w.footerMore;
  const LINK = "inline-flex min-h-10 items-center text-slate-700 underline-offset-4 transition-colors hover:text-brand-800 hover:underline";
  return (
    <footer className="relative overflow-hidden border-t border-line bg-surface">
      <div className={cx(WRAP, "grid gap-10 py-14 sm:grid-cols-2 lg:grid-cols-4")}>
        <div className="space-y-3 lg:col-span-2">
          <Logo size="md" />
          <p className="max-w-xs text-slate-700">{f.tagline}</p>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{f.clinics}</h2>
          <ul className="mt-2">
            <li>
              <Link prefetch={false} href="/apply" data-analytics="apply" className={LINK}>
                {w.footer.apply}
              </Link>
            </li>
            <li>
              <a href="#pricing" className={LINK}>
                {f.pricing}
              </a>
            </li>
            <li>
              <Link prefetch={false} href="/sign-in" data-analytics="staff_sign_in" className={LINK}>
                {w.footer.staff}
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold text-slate-900">{f.patients}</h2>
          <ul className="mt-2">
            <li>
              <Link prefetch={false} href={`/find${q}`} data-analytics="find" className={LINK}>
                {w.footer.find}
              </Link>
            </li>
            <li>
              <Link prefetch={false} href="/portal/sign-in" className={LINK}>
                {f.patientSignIn}
              </Link>
            </li>
          </ul>
        </div>
      </div>
      <div className={cx(WRAP, "relative border-t border-line py-6 text-sm text-slate-700")}>
        <p>{f.rights}</p>
      </div>
      <Emblem className="pointer-events-none absolute -bottom-16 -right-10 size-64 opacity-[0.07]" />
    </footer>
  );
}
