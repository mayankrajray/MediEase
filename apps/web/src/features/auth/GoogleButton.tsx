import { buttonClasses } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";

export type GoogleIntent = "staff" | "patient";

export const GOOGLE_START_PATH = "/api/v1/auth/google/start";

/**
 * Where "Continue with Google" goes (M6a-P3, ADR-0015 decision 3). A plain link to the API,
 * which runs the whole OpenID Connect flow: no Google script on our pages, so the CSP is
 * unchanged. An email already typed is passed as `login_hint`, so Google pre-selects that
 * account (and the local fake provider signs that email in).
 */
export function googleStartHref(intent: GoogleIntent, next: string, email?: string): string {
  const query = new URLSearchParams({ intent, next });
  const hint = email?.trim();
  if (hint && hint.includes("@")) {
    query.set("login_hint", hint);
  }
  return `${GOOGLE_START_PATH}?${query.toString()}`;
}

export function GoogleButton({
  intent,
  next,
  email,
}: {
  intent: GoogleIntent;
  next: string;
  email?: string;
}) {
  return (
    <div className="space-y-4">
      <p className="flex items-center gap-3 text-sm text-slate-700" aria-hidden="true">
        <span className="h-px flex-1 bg-slate-200" />
        or
        <span className="h-px flex-1 bg-slate-200" />
      </p>
      {/* Full-page navigation on purpose: the API answers with redirects, not JSON. */}
      <a href={googleStartHref(intent, next, email)} className={cx(buttonClasses("secondary"), "w-full")}>
        <span aria-hidden="true" className="font-bold text-brand-700">
          G
        </span>
        Continue with Google
      </a>
    </div>
  );
}
