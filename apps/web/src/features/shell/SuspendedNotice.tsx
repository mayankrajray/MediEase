import { ErrorNotice } from "@/features/auth/ErrorNotice";

/**
 * The clinic is suspended (`CLN_SUSPENDED`, docs/ERRORS.md). The API's message and
 * Ref are shown as they are; the switcher in the header still lets the person
 * work in another clinic. Nothing here says why: only ops can.
 */
export function SuspendedNotice({ clinicName, error }: { clinicName: string; error: unknown }) {
  return (
    <section aria-labelledby="suspended-heading" className="max-w-xl space-y-3">
      <h1 id="suspended-heading" className="text-2xl font-bold">
        {clinicName} is suspended
      </h1>
      <ErrorNotice error={error} />
      <p>Contact MediEase support to have the clinic reactivated.</p>
    </section>
  );
}
