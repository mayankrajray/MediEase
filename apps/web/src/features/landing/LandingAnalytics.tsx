"use client";

import { useEffect } from "react";

import { isLandingCta, track } from "@/lib/analytics";

/**
 * The landing page's two events (M6c-P8, FR-LND-03): viewed, and which call to action was used
 * (`data-analytics` on the link). Enums only; nothing about the visitor.
 */
export function LandingAnalytics({ lang }: Readonly<{ lang: "en" | "hi" }>) {
  useEffect(() => {
    track({ event: "landing_viewed", lang });
    const onClick = (event: MouseEvent) => {
      const target = event.target instanceof Element ? event.target.closest<HTMLElement>("[data-analytics]") : null;
      const cta = target?.dataset.analytics;
      if (isLandingCta(cta)) track({ event: "landing_cta_clicked", cta, lang });
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [lang]);
  return null;
}
