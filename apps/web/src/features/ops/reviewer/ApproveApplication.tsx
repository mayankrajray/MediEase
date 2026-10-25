"use client";

import { useState, type FormEvent } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError } from "@/lib/api/client";
import { fieldErrors } from "@/lib/api/field-errors";
import { sessionPost } from "@/lib/auth/refresh";

import { suggestSlug } from "../fields";
import type { ApplicationDetail } from "./api";

type BookingMode = "SLOTS" | "TOKENS";

/** `""` stays the application's value (the API keeps it when the field is null). */
function changed(value: string, original: string): string | null {
  const trimmed = value.trim();
  return trimmed === "" || trimmed === original ? null : trimmed;
}

/**
 * Approve (M6c-P3; spec clinic-onboarding R41-R44): the reviewer chooses the clinic's URL name,
 * booking mode and time zone, may correct its details, and approves. One request creates the
 * clinic and its verified doctors and emails the owner's invitation; the clinic goes live when
 * the owner accepts it (D1).
 */
export function ApproveApplication({
  detail,
  onClose,
  onDone,
}: Readonly<{
  detail: ApplicationDetail;
  onClose: () => void;
  onDone: (next: ApplicationDetail, text: string) => void;
}>) {
  const { endSession } = useSession();
  const [slug, setSlug] = useState(() => suggestSlug(detail.clinic_name));
  const [mode, setMode] = useState<BookingMode>("TOKENS");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [name, setName] = useState(detail.clinic_name);
  const [address, setAddress] = useState(detail.address_line);
  const [city, setCity] = useState(detail.city);
  const [state, setState] = useState(detail.state);
  const [pincode, setPincode] = useState(detail.pincode);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const problems = fieldErrors(error);
  const slugTaken = error instanceof ApiError && error.code === "CLN_SLUG_TAKEN";

  async function approve(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await sessionPost(
        "/api/v1/ops/applications/{application_id}/approve",
        {
          slug: slug.trim(),
          booking_mode: mode,
          timezone: timezone.trim() === "" ? "Asia/Kolkata" : timezone.trim(),
          clinic_name: changed(name, detail.clinic_name),
          address_line: changed(address, detail.address_line),
          city: changed(city, detail.city),
          state: changed(state, detail.state),
          pincode: changed(pincode, detail.pincode),
        },
        { pathParams: { application_id: detail.id } },
      );
      onDone(data.application, `Approved. ${data.clinic.name} is created and ${detail.owner_name} has been emailed the invitation.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog title="Approve and create the clinic" onClose={onClose}>
      <form onSubmit={(event) => void approve(event)} className="space-y-4" noValidate>
        <p>
          Every doctor is verified. Approving creates the clinic with its {detail.doctors.length} doctor
          {detail.doctors.length === 1 ? "" : "s"} and emails {detail.owner_email} an invitation. The clinic&apos;s page goes live when the owner accepts.
        </p>
        <TextField
          id="approve-slug"
          label="Clinic URL name"
          required
          value={slug}
          maxLength={63}
          hint="Lower-case words joined by hyphens. It appears in the clinic's public link and cannot be changed."
          error={slugTaken && error instanceof ApiError ? error.message : problems["slug"]}
          onChange={setSlug}
        />
        <SelectField
          id="approve-mode"
          label="Booking mode"
          value={mode}
          onChange={(v) => setMode(v as BookingMode)}
          options={[
            { value: "TOKENS", label: "Tokens per session" },
            { value: "SLOTS", label: "Fixed time slots" },
          ]}
        />
        <TextField id="approve-timezone" label="Time zone" value={timezone} error={problems["timezone"]} onChange={setTimezone} />
        <fieldset className="space-y-3">
          <legend className="font-medium">Clinic details (correct them if needed)</legend>
          <TextField id="approve-name" label="Clinic name" value={name} maxLength={200} error={problems["clinic_name"]} onChange={setName} />
          <TextField id="approve-address" label="Address" value={address} maxLength={300} error={problems["address_line"]} onChange={setAddress} />
          <div className="grid gap-3 sm:grid-cols-3">
            <TextField id="approve-city" label="City" value={city} maxLength={100} error={problems["city"]} onChange={setCity} />
            <TextField id="approve-state" label="State" value={state} maxLength={100} error={problems["state"]} onChange={setState} />
            <TextField
              id="approve-pincode"
              label="Pincode"
              inputMode="numeric"
              value={pincode}
              maxLength={6}
              error={problems["pincode"]}
              onChange={setPincode}
            />
          </div>
        </fieldset>
        {error !== null && !slugTaken && Object.keys(problems).length === 0 && <ErrorNotice error={error} />}
        <div className="flex flex-wrap justify-end gap-2">
          <Button type="button" onClick={onClose}>
            Go back
          </Button>
          <Button type="submit" variant="primary" disabled={busy || slug.trim().length < 3}>
            {busy ? "Approving…" : "Approve and email the owner"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
