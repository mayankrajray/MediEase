import type { Metadata } from "next";

export const metadata: Metadata = { title: "Ops console · MediEase" };

/** Placeholder: the Create clinic wizard is planned separately (M1-P6 design, option 2A). */
export default function OpsHomePage() {
  return (
    <section aria-labelledby="ops-heading" className="max-w-xl space-y-3">
      <h1 id="ops-heading" className="text-2xl font-bold">
        Ops console
      </h1>
      <p>You are signed in as platform staff. The clinic onboarding screens arrive in a later release.</p>
    </section>
  );
}
