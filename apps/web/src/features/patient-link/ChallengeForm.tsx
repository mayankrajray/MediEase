import { type PageLanguage, type PageStrings } from "./strings";

/**
 * The last-4 check (spec R10) as a plain HTML form: it works without JavaScript and posts to the
 * page's route handler, which keeps the view token in an HttpOnly cookie (decision 3A, 5A).
 */
export function ChallengeForm({
  token,
  clinicName,
  language,
  strings,
  problem,
  locked,
  switchHref,
}: Readonly<{
  token: string;
  clinicName: string;
  language: PageLanguage;
  strings: PageStrings;
  problem?: string;
  locked: boolean;
  switchHref: string;
}>) {
  return (
    <main lang={language} className="mx-auto max-w-md px-4 pb-10 pt-4 text-base leading-relaxed text-slate-900">
      <p className="text-sm">
        <a className="underline" href={switchHref} hrefLang={language === "hi" ? "en" : "hi"}>
          {strings.switchTo}
        </a>
      </p>
      <h1 className="mt-2 text-xl font-bold">{strings.title}</h1>
      <p>{strings.from(clinicName)}</p>
      {problem !== undefined && (
        <p role="alert" id="challenge-problem" className="mt-3 rounded border border-red-700 bg-red-50 p-2 font-semibold text-red-900">
          {problem}
        </p>
      )}
      {!locked && (
        <form method="post" action={`/p/${encodeURIComponent(token)}/verify`} className="mt-4">
          <h2 className="text-lg font-bold">{strings.challengeHeading}</h2>
          <p id="last4-help">{strings.challengeHelp}</p>
          <label htmlFor="phone_last4" className="mt-3 block font-semibold">
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
            className="mt-1 w-32 rounded border border-slate-600 p-2 text-xl tracking-widest"
          />
          <input type="hidden" name="lang" value={language} />
          <button type="submit" className="mt-4 block rounded-lg bg-brand-700 px-4 py-3 font-semibold text-white">
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
    <main lang={language} className="mx-auto max-w-md px-4 pt-6 text-base text-slate-900">
      <p role="alert" className="font-semibold">
        {message}
      </p>
    </main>
  );
}
