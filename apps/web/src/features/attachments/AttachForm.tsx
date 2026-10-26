"use client";

import { useId, useRef, useState } from "react";

import { buttonClasses } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { ACCEPTED_TYPES, fileProblem, useAttachmentsApi, type Attachment } from "./api";

/**
 * Choose a report and attach it to a visit (M6d-P6; spec visit-attachments R1-R5). Any role may
 * (ATTACHMENTS_ADD, D7): on the consultation screen, or from the queue at the desk.
 */
export function AttachForm({ visitId, onAdded }: Readonly<{ visitId: string; onAdded: (added: Attachment) => void }>) {
  const api = useAttachmentsApi();
  const { endSession } = useSession();
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [saving, setSaving] = useState(false);

  function choose(chosen: File | null) {
    setError(undefined);
    setFile(chosen);
    setProblem(chosen === null ? undefined : fileProblem(chosen));
  }

  async function attach() {
    if (file === null || problem !== undefined || saving) return;
    setSaving(true);
    setError(undefined);
    try {
      const added = await api.upload(visitId, file);
      setFile(null);
      if (input.current !== null) input.current.value = "";
      onAdded(added);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        void attach();
      }}
      className="space-y-2"
    >
      <label htmlFor={id} className="block font-medium">
        Attach a report
      </label>
      <p id={`${id}-help`} className="text-sm text-slate-700">
        A PDF, JPEG or PNG, at most 10 MB.
      </p>
      <input
        ref={input}
        id={id}
        type="file"
        accept={ACCEPTED_TYPES}
        aria-describedby={`${id}-help${problem !== undefined ? ` ${id}-problem` : ""}`}
        aria-invalid={problem !== undefined}
        onChange={(e) => choose(e.target.files?.[0] ?? null)}
        className="block w-full text-sm file:mr-3 file:min-h-10 file:rounded-lg file:border file:border-slate-400 file:bg-white file:px-3 file:py-2 file:font-medium"
      />
      {problem !== undefined && (
        <p id={`${id}-problem`} role="alert" className="text-sm font-medium text-red-800">
          {problem}
        </p>
      )}
      {error !== undefined && <ErrorNotice error={error} />}
      <button type="submit" disabled={file === null || problem !== undefined || saving} className={buttonClasses("primary")}>
        {saving ? "Attaching…" : "Attach"}
      </button>
    </form>
  );
}
