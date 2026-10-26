"use client";

import { useEffect, useState } from "react";

import { CheckboxField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { DOCTOR_PROBLEM_WORDS, LISTING_PROBLEM_WORDS, useListingApi, type ClinicListing } from "./api";

/**
 * *Directory* (M6c-P4; FR-ONB-09, 10; spec R50-R55): the owner's *Listed in the MediEase
 * directory* switch and each doctor's *Show on the public page* switch. A switch that cannot be
 * turned on says why (the API decides; this screen only shows its answer). The front desk and
 * doctors may read it; only owners change it.
 */
export function DirectoryListing() {
  const api = useListingApi();
  const { clinic, endSession } = useSession();
  const canManage = clinic.kind === "active" && clinic.membership.permissions.includes("CLINIC_MANAGE");
  const [listing, setListing] = useState<ClinicListing | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get().then(
      (data) => {
        if (!cancelled) setListing(data);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  async function change(run: () => Promise<ClinicListing>, done: (next: ClinicListing) => string) {
    setBusy(true);
    setError(null);
    try {
      const next = await run();
      setListing(next);
      setStatus(done(next));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  if (listing === undefined) {
    return error !== null ? <ErrorNotice error={error} /> : <p role="status">Loading the directory listing…</p>;
  }
  const blocked = listing.problems.length > 0;

  return (
    <section className="max-w-3xl space-y-6">
      <PageHeader title="Directory" />
      <p>Patients find listed clinics in MediEase search. Your clinic&apos;s own page and link work whether or not it is listed.</p>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}

      <div className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
        <CheckboxField
          id="listing-listed"
          label="Listed in the MediEase directory"
          checked={listing.listed}
          disabled={!canManage || busy || (!listing.listed && blocked)}
          onChange={(listed) =>
            void change(
              () => api.setListed(listed),
              (next) => (next.listed ? (next.discoverable ? "Listed. Patients can find the clinic." : "Listed.") : "No longer listed."),
            )
          }
        />
        <p className="font-medium">{listing.discoverable ? "Patients can find this clinic in search." : "Patients cannot find this clinic in search yet."}</p>
        {blocked && (
          <div>
            <p className="font-medium">To be listed:</p>
            <ul className="list-disc pl-6">
              {listing.problems.map((p) => (
                <li key={p}>{LISTING_PROBLEM_WORDS[p]}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <h2 className="text-lg font-semibold">Doctors</h2>
      <ul className="space-y-3">
        {listing.doctors.map((d) => (
          <li key={d.id} className="space-y-1 rounded-card border border-slate-200 bg-white p-4">
            <CheckboxField
              id={`visible-${d.id}`}
              label={`Show ${d.display_name} on the public page and in search`}
              checked={d.visible}
              disabled={!canManage || busy || (!d.visible && !d.can_be_visible)}
              onChange={(visible) =>
                void change(
                  () => api.setVisible(d.id, visible),
                  () => (visible ? `${d.display_name} is shown.` : `${d.display_name} is hidden.`),
                )
              }
            />
            {d.problems.length > 0 && <p className="text-sm text-slate-700">{d.problems.map((p) => DOCTOR_PROBLEM_WORDS[p]).join(" · ")}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}
