"use client";

import { CalendarDays, CircleUserRound, FileText, House, Languages, Pill } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { Logo } from "@/components/ui/Logo";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";
import { PORTAL_SIGN_IN_PATH, portalGet, portalPatch } from "@/lib/auth/portal-session";
import { parsePortalLanguage, type PortalLanguage, type PortalStrings, portalStrings } from "@/lib/i18n/portal";

import { rememberPortalLanguage } from "./LanguageCookieSwitch";
import { PortalBell } from "./PortalBell";
import { portalReasonForEndedSession } from "./messages";

export type PatientAccount = components["schemas"]["PatientAccount"];

interface Portal {
  readonly account: PatientAccount;
  readonly s: PortalStrings;
  /** Sends an ended session back to sign-in, then to this screen (spec R25). True if it did. */
  readonly leave: (error: unknown) => boolean;
  readonly setLanguage: (language: PortalLanguage) => Promise<void>;
  readonly replaceAccount: (account: PatientAccount) => void;
  /** M6b-P6: a screen marked notifications read; the bell asks for its count again at once. */
  readonly refreshBell: () => void;
}

const PortalContext = createContext<Portal | null>(null);

export function usePortal(): Portal {
  const portal = useContext(PortalContext);
  if (portal === null) throw new Error("usePortal outside PortalShell");
  return portal;
}

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly account: PatientAccount }
  | { readonly status: "failed"; readonly error: unknown }
  | { readonly status: "leaving" };

const TABS = [
  { href: "/portal", key: "home", Icon: House },
  { href: "/portal/appointments", key: "appointments", Icon: CalendarDays },
  // M6b-P3 (spec R36): the medicine plan.
  { href: "/portal/medicines", key: "medicines", Icon: Pill },
  { href: "/portal/prescriptions", key: "prescriptions", Icon: FileText },
  { href: "/portal/account", key: "account", Icon: CircleUserRound },
] as const;

function isCurrent(pathname: string, href: string): boolean {
  return href === "/portal" ? pathname === "/portal" : pathname === href || pathname.startsWith(`${href}/`);
}

/**
 * The signed-in portal (M6b-P2, decision 1A; spec R15, R21, R25): who is signed in, in which
 * language, a header with the switch and the tab bar (bottom below 768 px). Every screen reads the
 * account and the words from here; each loads only its own data.
 */
export function PortalShell({ children }: Readonly<{ children: ReactNode }>) {
  const router = useRouter();
  const pathname = usePathname();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [switching, setSwitching] = useState(false);
  const [bellTick, setBellTick] = useState(0);
  const refreshBell = useCallback(() => setBellTick((n) => n + 1), []);

  const leave = useCallback(
    (error: unknown): boolean => {
      const reason = portalReasonForEndedSession(error);
      if (reason === undefined) return false;
      setLoad({ status: "leaving" });
      const query = new URLSearchParams({ reason });
      // Keep the query (M6b-P4): the booking request form's chosen time is in it.
      const here = `${pathname}${typeof window === "undefined" ? "" : window.location.search}`;
      if (pathname !== "/portal") query.set("next", here);
      router.replace(`${PORTAL_SIGN_IN_PATH}?${query.toString()}`);
      return true;
    },
    [router, pathname],
  );

  useEffect(() => {
    let cancelled = false;
    portalGet("/api/v1/portal/me").then(
      ({ data }) => {
        if (cancelled) return;
        rememberPortalLanguage(parsePortalLanguage(data.account.language));
        setLoad({ status: "ready", account: data.account });
      },
      (error: unknown) => {
        if (!cancelled && !leave(error)) setLoad({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
    // The account is read once per visit to the portal, not on every tab change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt]);

  const account = load.status === "ready" ? load.account : undefined;
  const language = parsePortalLanguage(account?.language);
  const s = portalStrings(language);

  const setLanguage = useCallback(
    async (next: PortalLanguage) => {
      const { data } = await portalPatch("/api/v1/portal/me", { language: next });
      rememberPortalLanguage(next);
      setLoad({ status: "ready", account: data.account });
    },
    [],
  );

  const portal = useMemo<Portal | null>(
    () =>
      account === undefined
        ? null
        : {
            account,
            s,
            leave,
            setLanguage,
            replaceAccount: (next) => setLoad({ status: "ready", account: next }),
            refreshBell,
          },
    [account, s, leave, setLanguage, refreshBell],
  );

  async function switchLanguage() {
    if (switching) return;
    setSwitching(true);
    try {
      await setLanguage(language === "hi" ? "en" : "hi");
    } catch (error) {
      if (!leave(error)) setLoad({ status: "failed", error });
    } finally {
      setSwitching(false);
    }
  }

  if (load.status === "leaving") return null;

  return (
    <div lang={language} className="min-h-screen bg-canvas pb-[calc(4.5rem+env(safe-area-inset-bottom))] md:pb-0">
      {/* No backdrop-filter here: it would make the header the containing block of the fixed tab bar. */}
      <header className="sticky top-0 z-20 border-b border-line bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-1.5">
          <Link href="/portal" prefetch={false} className="flex min-h-11 items-center gap-2 text-lg font-bold text-slate-900">
            <Logo />
          </Link>
          {portal !== null && (
            <div className="flex items-center gap-1.5">
              <PortalBell language={language} tick={bellTick} onEnded={leave} />
              <button
                type="button"
                lang={language === "hi" ? "en" : "hi"}
                aria-label={s.switchLanguageLabel}
                onClick={() => void switchLanguage()}
                disabled={switching}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-line bg-white px-3 text-sm font-semibold text-slate-900 transition-colors duration-200 ease-brand hover:border-brand-300 hover:bg-brand-50 disabled:opacity-60 motion-reduce:transition-none"
              >
                <Languages aria-hidden="true" className="size-4 text-brand-700" />
                {s.switchLanguage}
              </button>
            </div>
          )}
        </div>
        {portal !== null && (
          <nav
            aria-label={s.nav.label}
            className="fixed inset-x-0 bottom-0 z-20 border-t border-line bg-white pb-[env(safe-area-inset-bottom)] shadow-[0_-4px_16px_rgb(23_43_53/0.06)] md:static md:border-t md:pb-0 md:shadow-none"
          >
            {/* Five tabs at 320 px: an icon over a short word, each tab as wide as its word. */}
            <ul className="mx-auto flex max-w-3xl md:gap-1 md:px-2">
              {TABS.map(({ key, href, Icon }) => {
                const current = isCurrent(pathname, href);
                return (
                  <li key={key} className="min-w-0 flex-auto md:flex-none">
                    <Link
                      href={href}
                      // M7c-P7 (M7): no viewport prefetch of all five tabs on every page (about
                      // 7 KB of a patient's mobile data, NFR-02); a tap still loads the tab.
                      prefetch={false}
                      aria-current={current ? "page" : undefined}
                      className={`relative flex min-h-14 flex-col items-center justify-center gap-0.5 whitespace-nowrap px-1 text-[0.6875rem] leading-tight transition-colors duration-200 ease-brand motion-reduce:transition-none sm:text-xs md:min-h-12 md:flex-row md:gap-2 md:px-3 md:text-sm ${
                        current ? "font-semibold text-brand-800" : "text-slate-700 hover:text-slate-900"
                      }`}
                    >
                      {current && (
                        <span aria-hidden="true" className="absolute inset-x-3 top-0 h-[3px] rounded-b-full bg-brand-700 md:inset-x-2 md:bottom-0 md:top-auto md:rounded-b-none md:rounded-t-full" />
                      )}
                      <span
                        aria-hidden="true"
                        className={`grid h-7 w-12 place-items-center rounded-full md:h-auto md:w-auto ${current ? "bg-brand-50 md:bg-transparent" : ""}`}
                      >
                        <Icon className="size-5 md:size-[1.125rem]" strokeWidth={current ? 2.25 : 1.75} />
                      </span>
                      {s.nav[key]}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-3xl px-4 py-5 md:py-8">
        {load.status === "failed" && (
          <ErrorNotice
            error={load.error}
            onRetry={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          />
        )}
        {load.status === "loading" && <ScreenLoading label={s.loading} />}
        {portal !== null && <PortalContext.Provider value={portal}>{children}</PortalContext.Provider>}
      </main>
    </div>
  );
}

export function ScreenLoading({ label }: Readonly<{ label: string }>) {
  return (
    <div className="space-y-3" aria-busy="true">
      <p role="status" className="sr-only">
        {label}
      </p>
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-24 w-full" />
    </div>
  );
}

/**
 * A section card of a portal screen. M7c-P7 (M7): an optional decorative `icon` beside the title,
 * an `action` (a link such as *See all*) at the heading's end, and `highlight` for the one card
 * a screen leads with. The title alone names the region.
 */
export function PortalCard({
  title,
  children,
  id,
  icon,
  action,
  highlight = false,
}: Readonly<{ title: string; children: ReactNode; id: string; icon?: ReactNode; action?: ReactNode; highlight?: boolean }>) {
  return (
    <section
      aria-labelledby={id}
      className={`min-w-0 space-y-3 rounded-card border bg-white p-4 shadow-card sm:p-5 ${highlight ? "border-brand-200 ring-1 ring-brand-100" : "border-line"}`}
    >
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
        <h2 id={id} className="flex min-w-0 items-center gap-2.5 text-lg font-bold text-slate-900">
          {icon !== undefined && (
            <span aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700 [&>svg]:size-[1.125rem]">
              {icon}
            </span>
          )}
          <span className="min-w-0 [overflow-wrap:anywhere]">{title}</span>
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

/** A screen's one `h1`, with an optional line under it. */
export function PortalTitle({ children, sub }: Readonly<{ children: ReactNode; sub?: ReactNode }>) {
  return (
    <div className="space-y-1">
      <h1 className="text-2xl font-bold tracking-tight text-slate-900 text-balance">{children}</h1>
      {sub !== undefined && <p className="text-slate-700">{sub}</p>}
    </div>
  );
}

/** A quiet text link with a chevron (*See all*, *Open*); 44 px tall. */
export const PORTAL_LINK =
  "inline-flex min-h-11 shrink-0 items-center gap-1 rounded-md font-semibold text-brand-800 underline-offset-4 hover:underline focus-visible:underline";
