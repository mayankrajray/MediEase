import { CircleAlert, Languages, LockKeyhole } from "lucide-react";

import { Logo } from "@/components/ui/Logo";

import { type PageLanguage, type PageStrings } from "./strings";

/** The logo and the language switch above a patient link page (M7c-P7, M8). */
function TopBar({ language, switchHref, label }: Readonly<{ language: PageLanguage; switchHref: string; label: string }>) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Logo />
      <a
        className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-sm font-semibold text-slate-900 hover:border-brand-300 hover:bg-brand-50"
        href={switchHref}
        hrefLang={language === "hi" ? "en" : "hi"}
      >
        <Languages aria-hidden="true" className="size-4 text-brand-700" />
        {label}
      </a>
    </div>
  );
}

/**
 * The last-4 check (spec R10) as a plain HTML form: it works without JavaScript and posts to the
 * page's route handler, which keeps the view token in an HttpOnly cookie (decision 3A, 5A).
 * M7c-P7 (M8): one card with a lock icon, the four digits in a large centred field and a
 * full-width button; the problem in the danger tone above the form.
 */
export function ChallengeForm({
  token,
  clinicName,
  language,
  strings,
  problem,
  locked,
  switchHref,
  base = "/p",
  title,
}: Readonly<{
  token: string;
  clinicName: string;
  language: PageLanguage;
  strings: PageStrings;
  problem?: string;
  locked: boolean;
  switchHref: string;
  /** M6d-P4: `/r` for a receipt link; the form posts to `<base>/<token>/verify`. */
  base?: string;
  title?: string;
}>) {
  return (
    <main lang={language} className="mx-auto max-w-md space-y-5 px-4 pb-10 pt-3 text-base leading-relaxed text-slate-900">
      <TopBar language={language} switchHref={switchHref} label={strings.switchTo} />
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-balance">{title ?? strings.title}</h1>
        <p className="text-slate-700">{strings.from(clinicName)}</p>
      </div>
      {problem !== undefined && (
        <p role="alert" id="challenge-problem" className="flex items-start gap-2 rounded-card border border-danger-line bg-danger-soft p-3 font-semibold text-slate-900">
          <CircleAlert aria-hidden="true" className="mt-1 size-4 shrink-0 text-danger" />
          <span>{problem}</span>
        </p>
      )}
      {!locked && (
        <form method="post" action={`${base}/${encodeURIComponent(token)}/verify`} className="space-y-4 rounded-card border border-line bg-white p-5 shadow-card">
          <div className="flex items-start gap-3">
            <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700">
              <LockKeyhole className="size-5" />
            </span>
            <div>
              <h2 className="text-lg font-bold">{strings.challengeHeading}</h2>
              <p id="last4-help" className="text-slate-700">
                {strings.challengeHelp}
              </p>
            </div>
          </div>
          <div>
            <label htmlFor="phone_last4" className="block font-semibold">
              {strings.last4Label}
            </label>
            <input
              id="phone_last4"
              name="phone_last4"
              type="text"
              inputMode="numeric"
              autoComplete="off"
              pattern="[0-9]{4}"
              minLength={4}
              maxLength={4}
              required
              aria-describedby={problem === undefined ? "last4-help" : "last4-help challenge-problem"}
              aria-invalid={problem === undefined ? undefined : true}
              className="mt-2 min-h-14 w-40 rounded-lg border border-slate-400 bg-white px-3 text-center font-mono text-2xl tracking-[0.4em] text-slate-900 shadow-xs hover:border-slate-600 focus-visible:border-brand-700 focus-visible:outline-brand-700 aria-[invalid=true]:border-danger"
            />
          </div>
          <input type="hidden" name="lang" value={language} />
          <button type="submit" className="flex min-h-12 w-full items-center justify-center rounded-lg bg-brand-700 px-5 font-semibold text-white shadow-sm hover:bg-brand-800">
            {strings.open}
          </button>
        </form>
      )}
    </main>
  );
}

/** A page that can only say what went wrong (invalid, expired, revoked, unavailable). */
export function LinkProblem({ language, message }: Readonly<{ language: PageLanguage; message: string }>) {
  return (
    <main lang={language} className="mx-auto max-w-md space-y-5 px-4 pb-10 pt-3 text-base text-slate-900">
      <Logo />
      <div className="flex items-start gap-3 rounded-card border border-danger-line bg-white p-5 shadow-card">
        <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-danger-soft text-danger">
          <CircleAlert className="size-5" />
        </span>
        <p role="alert" className="pt-1.5 font-semibold">
          {message}
        </p>
      </div>
    </main>
  );
}
