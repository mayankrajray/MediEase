/**
 * Product analytics events without PII (PRD §11.3, FR-LND-03; M6c-P8).
 *
 * Properties are enums only: never a name, phone, email, search words or anything clinical. No
 * analytics processor is chosen yet (privacy review L-04), so events are queued in the page
 * (`window.__meAnalytics`) and go nowhere; adding a processor is one function here.
 */

export const LANDING_CTAS = ["apply", "find", "patient_sign_in", "staff_sign_in", "pricing", "language"] as const;
export type LandingCta = (typeof LANDING_CTAS)[number];

export interface AnalyticsEvent {
  readonly event: "landing_viewed" | "landing_cta_clicked";
  readonly cta?: LandingCta;
  readonly lang: "en" | "hi";
}

declare global {
  interface Window {
    __meAnalytics?: AnalyticsEvent[];
  }
}

export function track(event: AnalyticsEvent): void {
  if (typeof window === "undefined") return;
  (window.__meAnalytics ??= []).push(event);
}

export function isLandingCta(value: string | undefined): value is LandingCta {
  return value !== undefined && (LANDING_CTAS as readonly string[]).includes(value);
}
