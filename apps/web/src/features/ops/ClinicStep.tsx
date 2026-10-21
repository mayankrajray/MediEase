"use client";

import { useRef, useState, type FormEvent } from "react";

import { TextField } from "@/components/ui/Field";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError, type PostResponse } from "@/lib/api/client";
import { fieldErrors } from "@/lib/api/field-errors";
import { sessionPost } from "@/lib/auth/refresh";

import { emptyToNull, parseSpecialties, suggestSlug } from "./fields";

export type NewClinicResult = PostResponse<"/api/v1/ops/clinics">;

const CLN_SLUG_TAKEN = "CLN_SLUG_TAKEN";

/** Step 1: create the clinic (`POST /ops/clinics`). FR-ORG-01, FR-OPS-01. */
export function ClinicStep({ onCreated }: { onCreated: (clinic: NewClinicResult) => void }) {
  const { endSession } = useSession();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [phone, setPhone] = useState("");
  const [addressLine, setAddressLine] = useState("");
  const [city, setCity] = useState("");
  const [state, setState] = useState("");
  const [pincode, setPincode] = useState("");
  const [specialties, setSpecialties] = useState("");
  const [codePrefix, setCodePrefix] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error, container);

  const problems = fieldErrors(error);
  const slugTaken = error instanceof ApiError && error.code === CLN_SLUG_TAKEN;
  const alertError = error !== null && !slugTaken && Object.keys(problems).length === 0;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await sessionPost("/api/v1/ops/clinics", {
        name: name.trim(),
        slug: slug.trim(),
        timezone: emptyToNull(timezone),
        phone: emptyToNull(phone),
        address_line: emptyToNull(addressLine),
        city: emptyToNull(city),
        state: emptyToNull(state),
        pincode: emptyToNull(pincode),
        specialties: parseSpecialties(specialties),
        patient_code_prefix: emptyToNull(codePrefix),
      });
      onCreated(data);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
      setSubmitting(false);
    }
  }

  return (
    <div ref={container} className="max-w-2xl space-y-4">
      {alertError && <ErrorNotice error={error} />}
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
        <TextField
          id="clinic-name"
          label="Clinic name"
          required
          value={name}
          maxLength={200}
          error={problems["name"]}
          onChange={(value) => {
            setName(value);
            if (!slugEdited) setSlug(suggestSlug(value));
          }}
        />
        <TextField
          id="clinic-slug"
          label="Clinic URL name"
          required
          value={slug}
          maxLength={63}
          hint="Lower-case words joined by hyphens. It appears in public links later, so it cannot be changed."
          error={slugTaken && error instanceof ApiError ? error.message : problems["slug"]}
          onChange={(value) => {
            setSlug(value);
            setSlugEdited(true);
          }}
        />
        <TextField
          id="clinic-timezone"
          label="Time zone"
          value={timezone}
          hint="An IANA name such as Asia/Kolkata. Leave empty for Asia/Kolkata."
          error={problems["timezone"]}
          onChange={setTimezone}
        />
        <TextField
          id="clinic-phone"
          label="Clinic phone"
          type="tel"
          inputMode="tel"
          maxLength={20}
          value={phone}
          error={problems["phone"]}
          onChange={setPhone}
        />
        <TextField
          id="clinic-address"
          label="Address"
          maxLength={300}
          value={addressLine}
          error={problems["address_line"]}
          onChange={setAddressLine}
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <TextField
            id="clinic-city"
            label="City"
            maxLength={100}
            value={city}
            error={problems["city"]}
            onChange={setCity}
          />
          <TextField
            id="clinic-state"
            label="State"
            maxLength={100}
            value={state}
            error={problems["state"]}
            onChange={setState}
          />
          <TextField
            id="clinic-pincode"
            label="Pincode"
            inputMode="numeric"
            maxLength={6}
            value={pincode}
            error={problems["pincode"]}
            onChange={setPincode}
          />
        </div>
        <TextField
          id="clinic-specialties"
          label="Specialties"
          hint="Separate with commas, for example General Medicine, Paediatrics."
          value={specialties}
          error={problems["specialties"]}
          onChange={setSpecialties}
        />
        <TextField
          id="clinic-code-prefix"
          label="Patient code prefix"
          maxLength={4}
          value={codePrefix}
          hint="2 to 4 capital letters, as in SC-0001. Leave empty to derive it from the clinic name. It cannot change once the clinic has patients."
          error={problems["patient_code_prefix"]}
          onChange={(value) => setCodePrefix(value.toUpperCase())}
        />

        <button
          type="submit"
          disabled={submitting}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
        >
          {submitting ? "Creating…" : "Create clinic and continue"}
        </button>
      </form>
    </div>
  );
}
