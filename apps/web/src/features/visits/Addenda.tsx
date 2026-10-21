"use client";

import { useId, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useRxApi, type Visit } from "@/features/prescriptions/api";
import { formatDateTime } from "@/lib/format/time";

const ADDENDUM_MAX = 5000;

/**
 * Addenda (FR-VIS-05): once a visit is locked, 24 hours after completion, changes are later
 * notes with their time, kept alongside the record and never edited.
 */
export function Addenda({
  visit,
  canAdd,
  timeZone,
  onAdded,
}: Readonly<{ visit: Visit; canAdd: boolean; timeZone: string; onAdded: () => void }>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const id = useId();
  const [body, setBody] = useState("");
  const [error, setError] = useState<unknown>(undefined);
  const [saving, setSaving] = useState(false);

  if (visit.addenda.length === 0 && !canAdd) return null;

  function add() {
    if (body.trim() === "" || saving) return;
    setSaving(true);
    setError(undefined);
    api.addAddendum(visit.id, body.trim()).then(
      () => {
        setSaving(false);
        setBody("");
        onAdded();
      },
      (failure: unknown) => {
        setSaving(false);
        if (!endSession(failure)) setError(failure);
      },
    );
  }

  return (
    <section aria-labelledby="addenda-heading" className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h2 id="addenda-heading" className="text-lg font-bold">
        Addenda
      </h2>
      {visit.addenda.length > 0 && (
        <ol className="space-y-2">
          {visit.addenda.map((a) => (
            <li key={a.id} className="rounded-card border border-slate-200 bg-white p-2">
              <p className="text-sm text-slate-700">Added {formatDateTime(a.created_at, timeZone)}</p>
              <p className="whitespace-pre-line">{a.body}</p>
            </li>
          ))}
        </ol>
      )}
      {canAdd && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            add();
          }}
          className="space-y-2"
        >
          <label htmlFor={id} className="block font-medium">
            New addendum
          </label>
          <textarea
            id={id}
            rows={3}
            maxLength={ADDENDUM_MAX}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
          />
          {error !== undefined && <ErrorNotice error={error} />}
          <button
            type="submit"
            disabled={body.trim() === "" || saving}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
          >
            {saving ? "Adding…" : "Add addendum"}
          </button>
        </form>
      )}
    </section>
  );
}
