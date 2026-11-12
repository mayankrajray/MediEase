import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "MediEase",
  description: "Clinic operating system",
  // Nothing is indexed unless its page says so (M6c: the landing page, /find and discoverable profiles).
  robots: { index: false, follow: false },
};

// Pages render per request so Next.js can stamp each response's CSP nonce
// (src/proxy.ts) on its scripts; a prerendered page would carry none and its
// scripts would be blocked.
export const dynamic = "force-dynamic";

// M7c-P7: the brand font (Manrope) is applied per surface by its layout (src/app/fonts.ts), so
// patient pages keep the system font and their 200 KB budget.
// M7e-E1: the installable app's tags and service worker are added by the staff and portal
// layouts only (src/lib/pwa/manifest.ts), for the same reason.
export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
