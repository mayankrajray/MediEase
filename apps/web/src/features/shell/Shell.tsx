"use client";

import { Menu as MenuIcon, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useId, useState, type ReactNode } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { Logo } from "@/components/ui/Logo";
import { MotionProvider } from "@/components/ui/Motion";

import { SignOutButton } from "./SignOutButton";

export interface ShellLink {
  readonly href: string;
  readonly label: string;
  /** Current only on this exact path (a section whose pages are its siblings' parent, like /ops). */
  readonly exact?: boolean;
  /** M6b-P5 (R45): a count waiting there, shown beside the label and read as words. */
  readonly badge?: number;
  /** M7c-P7 (M3): a decorative icon before the label. */
  readonly icon?: LucideIcon;
  /** M7c-P7 (M3): consecutive links of one group sit under its heading. */
  readonly group?: string;
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

        <aside className="hidden border-r border-line bg-surface lg:sticky lg:top-0 lg:flex lg:h-screen lg:w-64 lg:shrink-0 lg:flex-col lg:overflow-y-auto">
          <div className="px-5 py-4">
            <Brand />
          </div>
          <NavLinks label={navLabel} links={links} />
        </aside>

        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
              <div className="order-1 flex min-w-0 flex-1 items-center gap-x-3 sm:flex-wrap sm:gap-y-2 lg:flex-none">
                <Button
                  variant="secondary"
                  size="sm"
                  className="lg:hidden"
                  aria-haspopup="dialog"
                  aria-expanded={menuOpen}
                  onClick={() => setMenuOpen(true)}
                  icon={<MenuIcon className="size-4" />}
                >
                  Menu
                </Button>
                <span className="shrink-0 lg:hidden">
                  <Brand compact />
                </span>
                {identity}
              </div>

              <div className="order-2 hidden items-center gap-3 sm:flex lg:order-3">
                <span className="max-w-48 truncate text-sm font-medium text-slate-800">{person}</span>
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
  // On a phone the mark alone, so the clinic and role fit on one line.
  return <Logo compact={compact} />;
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
  // Consecutive links of one group share a heading (Hick's law: five short lists, not fifteen
  // links). The order is the workspace's own; grouping never moves a link.
  const groups: { readonly name: string | undefined; readonly items: ShellLink[] }[] = [];
  for (const item of links) {
    const last = groups.at(-1);
    if (last !== undefined && last.name === item.group) last.items.push(item);
    else groups.push({ name: item.group, items: [item] });
  }
  const headingId = useId();
  return (
    <nav aria-label={label} className="px-3 pb-4">
      <ul className="space-y-3">
        {groups.map((group, g) => (
          <li key={`${group.name ?? ""}-${g}`}>
            {group.name !== undefined && groups.length > 1 && (
              <p id={`${headingId}-${g}`} className="px-3 pb-1 text-xs font-semibold text-slate-600">
                {group.name}
              </p>
            )}
            <ul className="space-y-0.5" aria-labelledby={group.name !== undefined && groups.length > 1 ? `${headingId}-${g}` : undefined}>
              {group.items.map((item) => (
                <NavLink key={item.href} item={item} pathname={pathname} {...(onNavigate === undefined ? {} : { onNavigate })} />
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function NavLink({ item, pathname, onNavigate }: { item: ShellLink; pathname: string; onNavigate?: () => void }) {
  const current = pathname === item.href || (item.exact !== true && pathname.startsWith(`${item.href}/`));
  const Icon = item.icon;
  return (
    <li>
      <Link
        href={item.href}
        {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
        aria-current={current ? "page" : undefined}
        className={cx(
          "flex min-h-9 items-center gap-3 rounded-lg px-3 py-1.5 font-medium transition-colors duration-200 ease-brand motion-reduce:transition-none",
          current ? "bg-brand-50 text-brand-900 ring-1 ring-inset ring-brand-200" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
        )}
      >
        {Icon !== undefined && (
          <Icon aria-hidden="true" className={cx("size-[1.125rem] shrink-0", current ? "text-brand-700" : "text-slate-500")} />
        )}
        <span className="min-w-0 flex-1 truncate">{item.label}</span>
        {item.badge !== undefined && item.badge > 0 && (
          <>
            <span className="sr-only">{`, ${item.badge} waiting`}</span>
            {/* The visible count, after the label in the same line; the words above name it. */}
            <span
              aria-hidden="true"
              className="shrink-0 rounded-full bg-amber-100 px-2 text-sm font-semibold tabular-nums text-amber-950 ring-1 ring-inset ring-amber-300"
            >
              {item.badge > 99 ? "99+" : item.badge}
            </span>
          </>
        )}
      </Link>
    </li>
  );
}

/** A small pill naming the role or the console ("Owner", "Ops console"). */
export function RolePill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cx("shrink-0 whitespace-nowrap rounded-full bg-brand-50 px-2.5 py-0.5 text-sm font-medium text-brand-900 ring-1 ring-inset ring-brand-200", className)}>
      {children}
    </span>
  );
}
