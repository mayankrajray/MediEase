"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";
import { PORTAL_SIGN_IN_PATH, portalGet, portalPatch } from "@/lib/auth/portal-session";
import { parsePortalLanguage, type PortalLanguage, type PortalStrings, portalStrings } from "@/lib/i18n/portal";

import { rememberPortalLanguage } from "./LanguageCookieSwitch";
import { portalReasonForEndedSession } from "./messages";

export type PatientAccount = components["schemas"]["PatientAccount"];

interface Portal {
  readonly account: PatientAccount;
  readonly s: PortalStrings;
  /** Sends an ended session back to sign-in, then to this screen (spec R25). True if it did. */
  readonly leave: (error: unknown) => boolean;
  readonly setLanguage: (language: PortalLanguage) => Promise<void>;
  readonly replaceAccount: (account: PatientAccount) => void;
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
  { href: "/portal", key: "home" },
  { href: "/portal/appointments", key: "appointments" },
  // M6b-P3 (spec R36): the medicine plan.
  { href: "/portal/medicines", key: "medicines" },
  { href: "/portal/prescriptions", key: "prescriptions" },
  { href: "/portal/account", key: "account" },
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
          },
    [account, s, leave, setLanguage],
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
    <div lang={language} className="min-h-screen bg-canvas pb-20 md:pb-0">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link href="/portal" className="flex min-h-11 items-center gap-2 text-lg font-bold text-slate-900">
            <span aria-hidden="true" className="grid size-8 place-items-center rounded-xl bg-brand-700 text-sm text-white">
              M
            </span>
            MediEase
          </Link>
          {portal !== null && (
            <button
              type="button"
              lang={language === "hi" ? "en" : "hi"}
              aria-label={s.switchLanguageLabel}
              onClick={() => void switchLanguage()}
              disabled={switching}
              className="inline-flex min-h-11 items-center rounded-lg border border-slate-400 bg-white px-3 text-sm font-medium text-slate-900 hover:bg-slate-100"
            >
              {s.switchLanguage}
            </button>
          )}
        </div>
        {portal !== null && (
          <nav aria-label={s.nav.label} className="fixed inset-x-0 bottom-0 z-10 border-t border-slate-200 bg-white md:static md:border-t-0">
            {/* Five tabs at 360 px: each as wide as its word (equal fifths split "Prescriptions"). */}
            <ul className="mx-auto flex max-w-3xl">
              {TABS.map((tab) => {
                const current = isCurrent(pathname, tab.href);
                return (
                  <li key={tab.key} className="flex-auto">
                    <Link
                      href={tab.href}
                      aria-current={current ? "page" : undefined}
                      className={`flex min-h-14 items-center justify-center whitespace-nowrap px-1 text-center text-xs sm:text-sm ${
                        current ? "border-t-4 border-brand-700 font-bold text-brand-800 md:border-b-4 md:border-t-0" : "text-slate-800"
                      }`}
                    >
                      {s.nav[tab.key]}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </nav>
        )}
      </header>
      <main className="mx-auto max-w-3xl px-4 py-5">
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

/** A section card of a portal screen. */
export function PortalCard({ title, children, id }: Readonly<{ title: string; children: ReactNode; id: string }>) {
  return (
    <section aria-labelledby={id} className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id={id} className="text-lg font-bold">
        {title}
      </h2>
      {children}
    </section>
  );
}
