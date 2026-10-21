"use client";

import { useId, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Drawer } from "@/components/Drawer";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { useRxApi, type Favourite, type RxTemplate } from "./api";
import { adviceInput, daysBetween, toInput, type Body, type Line } from "./draft";
import { lineSummary } from "./vocabulary";

/** A name for a favourite or template, with the API's error (RX_NAME_TAKEN, RX_LIBRARY_FULL). */
function NameDialog({
  title,
  initial,
  hint,
  onSubmit,
  onClose,
}: Readonly<{ title: string; initial: string; hint: string; onSubmit: (name: string) => Promise<void>; onClose: () => void }>) {
  const id = useId();
  const { endSession } = useSession();
  const [name, setName] = useState(initial);
  const [error, setError] = useState<unknown>(undefined);
  const [saving, setSaving] = useState(false);

  function submit() {
    if (name.trim() === "" || saving) return;
    setSaving(true);
    setError(undefined);
    onSubmit(name.trim()).catch((failure: unknown) => {
      setSaving(false);
      if (!endSession(failure)) setError(failure);
    });
  }

  return (
    <Dialog title={title} onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
        className="space-y-3"
      >
        <div>
          <label htmlFor={id} className="block font-medium">
            Name
          </label>
          <input
            id={id}
            data-autofocus
            value={name}
            maxLength={100}
            aria-describedby={`${id}-hint`}
            onChange={(e) => setName(e.target.value)}
            className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
          />
          <p id={`${id}-hint`} className="text-sm text-slate-700">
            {hint}
          </p>
        </div>
        {error !== undefined && <ErrorNotice error={error} />}
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-4 py-2 font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none">
            Cancel
          </button>
          <button
            type="submit"
            disabled={name.trim() === "" || saving}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </form>
    </Dialog>
  );
}

export function SaveFavouriteDialog({
  line,
  onSaved,
  onClose,
}: Readonly<{ line: Line; onSaved: (favourite: Favourite) => void; onClose: () => void }>) {
  const api = useRxApi();
  return (
    <NameDialog
      title="Save line as favourite"
      initial={line.medicine_name}
      hint={`${lineSummary(line)}. Typing the name later brings the whole line.`}
      onSubmit={async (name) => onSaved(await api.saveFavourite(name, { ...toInput(line), favourite_id: null }))}
      onClose={onClose}
    />
  );
}

export function SaveTemplateDialog({
  body,
  today,
  onSaved,
  onClose,
}: Readonly<{ body: Body; today: string; onSaved: (template: RxTemplate) => void; onClose: () => void }>) {
  const api = useRxApi();
  return (
    <NameDialog
      title="Save as template"
      initial=""
      hint={`${body.lines.length} ${body.lines.length === 1 ? "medicine" : "medicines"} and the advice${body.followUp === "" ? "" : ", with the follow-up as days from the day it is used"}.`}
      onSubmit={async (name) =>
        onSaved(
          await api.saveTemplate({
            name,
            items: body.lines.map((l) => ({ ...toInput(l), favourite_id: null })),
            advice: adviceInput(body.advice),
            follow_up_days: body.followUp === "" ? null : daysBetween(today, body.followUp),
          }),
        )
      }
      onClose={onClose}
    />
  );
}

/**
 * The doctor's favourites and templates (decision 6A: managed from the builder only): apply a
 * template, rename it, delete either. Deleting never changes a prescription already written.
 */
export function LibraryDrawer({
  favourites,
  templates,
  onApply,
  onChanged,
  onClose,
}: Readonly<{
  favourites: readonly Favourite[];
  templates: readonly RxTemplate[];
  onApply: (template: RxTemplate) => void;
  onChanged: () => void;
  onClose: () => void;
}>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const [renaming, setRenaming] = useState<RxTemplate | undefined>(undefined);
  const [confirming, setConfirming] = useState<string | undefined>(undefined);
  const [error, setError] = useState<unknown>(undefined);
  const [message, setMessage] = useState("");

  /** Deleting asks once more on the same button: the first press only arms it. */
  function remove(id: string, label: string, work: () => Promise<unknown>) {
    if (confirming !== id) {
      setConfirming(id);
      setMessage(`Press Delete again to delete ${label}.`);
      return;
    }
    setConfirming(undefined);
    act(work(), `${label} deleted.`);
  }

  function act(work: Promise<unknown>, done: string) {
    setError(undefined);
    work.then(
      () => {
        setMessage(done);
        onChanged();
      },
      (failure: unknown) => {
        if (!endSession(failure)) setError(failure);
      },
    );
  }

  return (
    <Drawer title="Templates and favourites" onClose={onClose}>
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>
      {error !== undefined && <ErrorNotice error={error} />}
      <section aria-labelledby="templates-heading" className="space-y-2">
        <h3 id="templates-heading" className="text-lg font-bold">
          Templates
        </h3>
        {templates.length === 0 && <p className="text-slate-700">None yet. Use Save as template on a prescription.</p>}
        {templates.length > 0 && <p className="text-sm text-slate-700">Apply replaces the medicines, advice and follow-up being written.</p>}
        <ul className="space-y-2">
          {templates.map((t) => (
            <li key={t.id} className="flex flex-wrap items-center justify-between gap-2 rounded-card border border-slate-200 bg-white p-2">
              <span>
                <span className="font-medium">{t.name}</span>
                <span className="block text-sm text-slate-700">
                  {t.items.length} {t.items.length === 1 ? "medicine" : "medicines"}
                  {t.follow_up_days === null ? "" : ` · follow-up in ${t.follow_up_days} days`}
                </span>
              </span>
              <span className="flex gap-2">
                <button
                  type="button"
                  aria-label={`Apply template ${t.name}`}
                  onClick={() => onApply(t)}
                  className="rounded-lg bg-brand-700 px-3 py-1 font-semibold text-white hover:bg-brand-800"
                >
                  Apply
                </button>
                <button
                  type="button"
                  aria-label={`Rename template ${t.name}`}
                  onClick={() => setRenaming(t)}
                  className="rounded-lg border border-slate-400 px-3 py-1 hover:bg-slate-100"
                >
                  Rename
                </button>
                <button
                  type="button"
                  aria-label={`Delete template ${t.name}`}
                  onClick={() => remove(t.id, `Template ${t.name}`, () => api.deleteTemplate(t.id))}
                  className="inline-flex min-h-8 items-center rounded-lg border border-red-700 bg-white px-3 py-1 text-sm font-medium text-red-900 hover:bg-red-50"
                >
                  {confirming === t.id ? "Delete?" : "Delete"}
                </button>
              </span>
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="favourites-heading" className="space-y-2">
        <h3 id="favourites-heading" className="text-lg font-bold">
          Favourites
        </h3>
        {favourites.length === 0 && <p className="text-slate-700">None yet. Use Save as favourite on a line.</p>}
        <ul className="space-y-2">
          {favourites.map((f) => (
            <li key={f.id} className="flex items-center justify-between gap-2 rounded-card border border-slate-200 bg-white p-2">
              <span>
                <span className="font-medium">{f.name}</span>
                <span className="block text-sm text-slate-700">{lineSummary(f.item)}</span>
              </span>
              <button
                type="button"
                aria-label={`Delete favourite ${f.name}`}
                onClick={() => remove(f.id, `Favourite ${f.name}`, () => api.deleteFavourite(f.id))}
                className="inline-flex min-h-8 items-center rounded-lg border border-red-700 bg-white px-3 py-1 text-sm font-medium text-red-900 hover:bg-red-50"
              >
                {confirming === f.id ? "Delete?" : "Delete"}
              </button>
            </li>
          ))}
        </ul>
      </section>
      {renaming !== undefined && (
        <NameDialog
          title={`Rename template ${renaming.name}`}
          initial={renaming.name}
          hint="The template's lines and advice stay as they are."
          onSubmit={async (name) => {
            await api.renameTemplate(renaming, name);
            setRenaming(undefined);
            setMessage(`Template renamed to ${name}.`);
            onChanged();
          }}
          onClose={() => setRenaming(undefined)}
        />
      )}
    </Drawer>
  );
}
