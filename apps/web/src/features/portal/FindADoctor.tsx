"use client";

import Link from "next/link";

import { PortalCard, usePortal } from "./PortalShell";

/**
 * *Find a doctor* until directory search exists (M6b-P2 decision 4A, spec R16; replaced in M6c):
 * says so, and offers the ways to link records today.
 */
export function FindADoctor() {
  const { s } = usePortal();
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.find.title}</h1>
      <PortalCard id="find-soon-heading" title={s.find.soon}>
        <p>{s.find.meanwhile}</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>{s.find.clinicPage}</li>
          <li>{s.find.invitation}</li>
          <li>{s.find.prescription}</li>
        </ul>
      </PortalCard>
      <Link href="/portal" className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
        {s.goHome}
      </Link>
    </div>
  );
}
