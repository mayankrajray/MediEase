import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: "MediEase",
  description: "Clinic operating system",
  // Nothing on this origin should be indexed until public pages exist (M7).
  robots: { index: false, follow: false },
};

// Pages render per request so Next.js can stamp each response's CSP nonce
// (src/proxy.ts) on its scripts; a prerendered page would carry none and its
// scripts would be blocked.
export const dynamic = "force-dynamic";

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
