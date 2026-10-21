"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { MotionProvider } from "@/components/ui/Motion";

import { SignOutButton } from "./SignOutButton";

export interface ShellLink {
  readonly href: string;
  readonly label: string;
  /** Current only on this exact path (a section whose pages are its siblings' parent, like /ops). */
  readonly exact?: boolean;
}

/**
 * The frame shared by the clinic workspace and the ops console (M6-P1 decision 4A, M6-P2
 * decision 7A). Responsive from 360 px: from 1024 px the navigation is a left sidebar; below it a
 * Menu button opens the same links in a drawer (a native `<dialog>`: focus stays inside, Escape
 * closes), which on a phone also holds Sign out. A skip link, one `banner`, one `navigation`
 * named `navLabel` and one `main` for keyboard and screen-reader users. Motion is available to
 * every screen inside.
 */
export function Shell({
  navLabel,
  links,
  identity,
  person,
  tools,
  notice,
  children,
}: {
  navLabel: string;
  links: readonly ShellLink[];
  /** Where you are: the clinic (or its switcher) and your role, or "Ops console". */
  identity: ReactNode;
  /** Who you are, beside Sign out (hidden on a phone, shown in the menu instead). */
  person: string;
  /** Header tools for the screen's work, such as the patient search. */
  tools?: ReactNode;
  /** A line under the header for the whole workspace (a clinic still being set up). */
  notice?: ReactNode;
  children: ReactNode;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <MotionProvider>
      <div className="min-h-screen bg-canvas lg:flex">
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded focus:bg-white focus:p-2"
        >
          Skip to content
        </a>

        <aside className="hidden border-r border-slate-200 bg-white lg:flex lg:w-60 lg:shrink-0 lg:flex-col">
          <div className="px-5 py-4">
            <Brand />
          </div>
          <NavLinks label={navLabel} links={links} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
              <div className="order-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
                <Button
                  variant="secondary"
                  size="sm"
                  className="lg:hidden"
                  aria-haspopup="dialog"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen(true)}
                >
                  Menu
                </Button>
                <span className="lg:hidden">
                  <Brand compact />
                </span>
                {identity}
              </div>

              <div className="order-2 hidden items-center gap-3 sm:flex lg:order-3">
                <span>{person}</span>
                <SignOutButton />
              </div>

              {tools !== undefined && (
                <div className="order-3 flex w-full items-center gap-2 lg:order-2 lg:w-auto lg:flex-1">{tools}</div>
              )}
            </div>
          </header>

          {notice}

          <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
            {children}
          </main>
        </div>
      </div>

      {menuOpen && (
        <Drawer title="Menu" side="left" onClose={() => setMenuOpen(false)}>
          <p className="text-sm text-slate-700">{person}</p>
          <NavLinks label={navLabel} links={links} onNavigate={() => setMenuOpen(false)} />
          {/* On a phone the header has no room for it: Sign out lives here too. */}
          <div className="sm:hidden">
            <SignOutButton />
          </div>
        </Drawer>
      )}
    </MotionProvider>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2 text-lg font-bold text-slate-900">
      <span aria-hidden="true" className="grid size-7 place-items-center rounded-lg bg-brand-700 text-sm text-white">
        M
      </span>
      {/* On a phone the mark alone, so the clinic and role fit on one line. */}
      <span className={compact ? "sr-only sm:not-sr-only" : undefined}>MediEase</span>
    </span>
  );
}

/** The sections, with the one being shown marked as current (a link state, not a colour only). */
function NavLinks({
  label,
  links,
  onNavigate,
}: {
  label: string;
  links: readonly ShellLink[];
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  return (
    <nav aria-label={label} className="px-3 pb-4">
      <ul className="space-y-1">
        {links.map((item) => {
          const current = pathname === item.href || (item.exact !== true && pathname.startsWith(`${item.href}/`));
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
                aria-current={current ? "page" : undefined}
                className={cx(
                  "flex min-h-10 items-center rounded-lg px-3 py-2 font-medium transition-colors motion-reduce:transition-none",
                  current ? "bg-brand-50 text-brand-900 ring-1 ring-inset ring-brand-200" : "text-slate-700 hover:bg-slate-100",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** A small pill naming the role or the console ("Owner", "Ops console"). */
export function RolePill({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-sm font-medium text-brand-900 ring-1 ring-inset ring-brand-200">
      {children}
    </span>
  );
}
