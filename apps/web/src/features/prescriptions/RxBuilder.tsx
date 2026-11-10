"use client";

import { useCallback, useEffect, useId, useImperativeHandle, useRef, useState, type KeyboardEvent, type Ref } from "react";

import { ChevronDown, ChevronUp, FileCheck2, Library, Pill, RefreshCw, Save, Star, Trash2, TriangleAlert } from "lucide-react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { INPUT_BASE, LABEL } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { CARD, CARD_TITLE, STALE_BOX } from "@/features/visits/card";
import { saveText, useAutosave } from "@/features/visits/useAutosave";
import { ApiError } from "@/lib/api/client";
import { addDays, formatDay } from "@/lib/format/time";

import { AdviceEditor } from "./AdviceEditor";
import { useRxApi, type Favourite, type LineWarning, type Prescription, type RxTemplate, type Vocabulary } from "./api";
import { EMPTY_BODY, MAX_LINES, draftBody, fromPrescription, fromTemplate, isEmpty, moveLine, type Body, type Line } from "./draft";
import { EntryRow } from "./EntryRow";
import { IssueReview } from "./IssueReview";
import { LibraryDrawer, SaveFavouriteDialog, SaveTemplateDialog } from "./Library";
import { LineEditor } from "./LineEditor";
import { WARNING_TEXT, lineSummary } from "./vocabulary";

/** What the consultation screen may ask of the builder: Repeat adds a past visit's lines. */
export interface BuilderHandle {
  readonly add: (lines: readonly Line[]) => void;
  /** Whether anything is written (the screen asks before completing without issuing). */
  readonly hasContent: () => boolean;
}

type Overlay =
  | { readonly kind: "line"; readonly index: number }
  | { readonly kind: "favourite"; readonly index: number }
  | { readonly kind: "template" }
  | { readonly kind: "library" }
  | { readonly kind: "review" };

/**
 * The keyboard-first prescription builder (FR-RX-01..05, spec §6, M4-P6). The whole draft is
 * saved about a second after each change and when a field is left (decision 2A), with the
 * revision it was loaded at; the draft itself is created on the first save, so opening a
 * consultation never makes an empty prescription.
 */
export function RxBuilder({
  visitId,
  draft,
  today,
  language,
  handle,
  register,
  onIssued,
  onReload,
}: Readonly<{
  visitId: string;
  /** The chain's draft (a first version or a revision), if there is one. */
  draft: Prescription | undefined;
  today: string;
  language: "en" | "hi";
  handle: Ref<BuilderHandle>;
  /** Lets the screen save everything before it completes the visit. */
  register: (flush: () => Promise<boolean>) => () => void;
  onIssued: (rx: Prescription) => void;
  onReload: () => void;
}>) {
  const api = useRxApi();
  const { endSession } = useSession();
  const [body, setBody] = useState<Body>(() => (draft === undefined ? EMPTY_BODY : fromPrescription(draft)));
  const [favourites, setFavourites] = useState<readonly Favourite[]>([]);
  const [templates, setTemplates] = useState<readonly RxTemplate[]>([]);
  // M6b-P3: the engine's slot sets (R21) and the API's notes on each saved line (R22).
  const [vocabulary, setVocabulary] = useState<Vocabulary | undefined>(undefined);
  const [warnings, setWarnings] = useState<readonly (readonly LineWarning[])[]>(() => draft?.items.map((i) => i.line_warnings) ?? []);
  const startId = useId();
  const [library, setLibrary] = useState(0);
  const [overlay, setOverlay] = useState<Overlay | undefined>(undefined);
  const [message, setMessage] = useState("");
  const pendingFocus = useRef<{ key: string; action: string } | undefined>(undefined);
  const rxId = useRef<string | undefined>(draft?.id);
  const revision = useRef<number>(draft?.revision ?? 0);
  const listRef = useRef<HTMLOListElement>(null);
  const latest = useRef(body);
  useEffect(() => {
    latest.current = body;
  }, [body]);

  const save = useCallback(
    async (next: Body) => {
      if (rxId.current === undefined) {
        try {
          const created = await api.createDraft(visitId);
          rxId.current = created.id;
          revision.current = created.revision;
        } catch (failure) {
          // Another tab started this visit's prescription first: the same as a stale save.
          if (failure instanceof ApiError && failure.code === "RX_ALREADY_EXISTS") {
            throw new ApiError("RX_STALE", failure.message, 409, failure.requestId, failure.details);
          }
          throw failure;
        }
      }
      const saved = await api.saveDraft(rxId.current, draftBody(next, revision.current));
      revision.current = saved.revision;
      setWarnings(saved.items.map((i) => i.line_warnings));
    },
    [api, visitId],
  );
  const autosave = useAutosave<Body>(save, endSession);
  const { flush, change } = autosave;
  const stale = autosave.state.kind === "stale";

  useEffect(() => register(flush), [register, flush]);

  useEffect(() => {
    let cancelled = false;
    api.vocabulary().then(
      (found) => {
        if (!cancelled) setVocabulary(found);
      },
      (failure: unknown) => {
        if (!cancelled) endSession(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.favourites(), api.templates()]).then(
      ([f, t]) => {
        if (cancelled) return;
        setFavourites(f);
        setTemplates(t);
      },
      (failure: unknown) => {
        // The library is a help: without it the builder still works, by typing.
        if (!cancelled) endSession(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, library, endSession]);

  const update = useCallback(
    (next: Body) => {
      setBody(next);
      change(next);
    },
    [change],
  );

  useImperativeHandle(
    handle,
    () => ({
      add: (lines) => {
        const current = latest.current;
        const room = MAX_LINES - current.lines.length;
        const added = Math.min(lines.length, room);
        update({ ...current, lines: [...current.lines, ...lines.slice(0, room)] });
        setMessage(`${added} ${added === 1 ? "medicine" : "medicines"} copied from the earlier visit.`);
      },
      hasContent: () => !isEmpty(latest.current),
    }),
    [update],
  );

  // After Alt+↑/↓ the moved line keeps the focus on the same button (it is a new DOM position).
  useEffect(() => {
    const target = pendingFocus.current;
    if (target === undefined) return;
    pendingFocus.current = undefined;
    listRef.current?.querySelector<HTMLElement>(`[data-line-key="${target.key}"] [data-action="${target.action}"]`)?.focus();
  });

  const prepare = useCallback(async () => {
    const ok = await flush();
    return ok && rxId.current !== undefined ? { rxId: rxId.current, revision: revision.current } : undefined;
  }, [flush]);

  const lines = body.lines;
  const setLines = (next: readonly Line[]) => update({ ...body, lines: next });

  function onLineKey(event: KeyboardEvent<HTMLLIElement>, index: number, key: string) {
    if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
    event.preventDefault();
    const by = event.key === "ArrowUp" ? -1 : 1;
    const moved = moveLine(lines, index, by);
    if (moved === lines) return;
    setLines(moved);
    const action = (event.target as HTMLElement).dataset["action"] ?? "more";
    pendingFocus.current = { key, action };
    setMessage(`${lines[index]?.medicine_name ?? "Line"} moved to line ${index + by + 1}.`);
  }

  function remove(index: number) {
    const gone = lines[index];
    setLines(lines.filter((_, i) => i !== index));
    setMessage(`${gone?.medicine_name ?? "Line"} removed.`);
  }

  function applyTemplate(template: RxTemplate) {
    update(fromTemplate(template, today, addDays));
    setOverlay(undefined);
    setMessage(`Template ${template.name} applied.`);
  }

  const button = `${buttonClasses("secondary", "sm")} min-h-8`;
  const icon = `${button} w-8 px-0`;

  return (
    <section aria-labelledby="rx-heading" className={CARD}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="rx-heading" className={CARD_TITLE}>
          <Pill aria-hidden="true" className="size-5 text-brand-700" />
          Prescription{draft !== undefined && draft.version > 1 ? ` · version ${draft.version} (revision)` : ""}
        </h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={stale} onClick={() => setOverlay({ kind: "library" })} className={button}>
            <Library aria-hidden="true" className="size-4" />
            Templates and favourites
          </button>
          <button type="button" disabled={stale || isEmpty(body)} onClick={() => setOverlay({ kind: "template" })} className={button}>
            <Save aria-hidden="true" className="size-4" />
            Save as template
          </button>
        </div>
      </div>

      {stale && (
        <div role="alert" className={STALE_BOX}>
          <p className="font-medium">{saveText(autosave.state)}</p>
          <Button onClick={onReload} icon={<RefreshCw className="size-4" />}>
            Reload
          </Button>
        </div>
      )}

      {lines.length > 0 && (
        <ol ref={listRef} aria-label="Medicines" className="divide-y divide-line overflow-hidden rounded-lg border border-line">
          {lines.map((line, index) => (
            <li
              key={line.key}
              data-line-key={line.key}
              onKeyDown={(event) => onLineKey(event, index, line.key)}
              className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 bg-white px-3 py-2.5 transition-colors duration-200 ease-brand focus-within:bg-brand-50/50 hover:bg-slate-50 motion-reduce:transition-none"
            >
              <span className="flex min-w-0 flex-1 gap-2.5">
                <span aria-hidden="true" className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full bg-brand-50 text-xs font-bold text-brand-800">
                  {index + 1}
                </span>
                <span className="min-w-0 [overflow-wrap:anywhere]">
                  <span className="sr-only">{index + 1}.</span> {lineSummary(line)}
                  {(line.preparation?.length ?? 0) + (line.storage?.length ?? 0) > 0 && (
                    <span className="text-sm text-slate-700"> · with instructions</span>
                  )}
                  {(warnings[index] ?? []).map((w) => (
                    <span key={w} className="mt-1 flex items-start gap-1.5 rounded-md border border-warning-line bg-warning-soft px-2 py-1 text-sm text-slate-900">
                      <TriangleAlert aria-hidden="true" className="mt-0.5 size-3.5 shrink-0 text-warning" />
                      <span>Check: {WARNING_TEXT[w]}</span>
                    </span>
                  ))}
                </span>
              </span>
              <span className="flex flex-wrap gap-1">
                <button
                  type="button"
                  data-action="more"
                  disabled={stale}
                  aria-label={`More for line ${index + 1}, ${line.medicine_name}`}
                  aria-keyshortcuts="Alt+ArrowUp Alt+ArrowDown"
                  onClick={() => setOverlay({ kind: "line", index })}
                  className={button}
                >
                  More
                </button>
                <button
                  type="button"
                  data-action="up"
                  disabled={stale || index === 0}
                  aria-label={`Move line ${index + 1} up`}
                  onClick={() => setLines(moveLine(lines, index, -1))}
                  className={icon}
                >
                  <ChevronUp aria-hidden="true" className="size-4" />
                </button>
                <button
                  type="button"
                  data-action="down"
                  disabled={stale || index === lines.length - 1}
                  aria-label={`Move line ${index + 1} down`}
                  onClick={() => setLines(moveLine(lines, index, 1))}
                  className={icon}
                >
                  <ChevronDown aria-hidden="true" className="size-4" />
                </button>
                <button
                  type="button"
                  data-action="favourite"
                  disabled={stale}
                  aria-label={`Save line ${index + 1} as favourite`}
                  onClick={() => setOverlay({ kind: "favourite", index })}
                  className={button}
                >
                  <Star aria-hidden="true" className="size-3.5" />
                  Favourite
                </button>
                <button
                  type="button"
                  data-action="remove"
                  disabled={stale}
                  aria-label={`Remove line ${index + 1}, ${line.medicine_name}`}
                  onClick={() => remove(index)}
                  className={`${button} text-danger hover:border-danger-line hover:bg-danger-soft hover:text-danger`}
                >
                  <Trash2 aria-hidden="true" className="size-3.5" />
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {lines.length > 0 && (
        <p className="text-sm text-slate-700">
          <kbd className="rounded border border-line bg-slate-50 px-1 font-sans text-xs">Alt+↑</kbd> and{" "}
          <kbd className="rounded border border-line bg-slate-50 px-1 font-sans text-xs">Alt+↓</kbd> move the line you are on.
        </p>
      )}

      <EntryRow
        onAdd={(line) => setLines([...lines, line])}
        favourites={favourites}
        vocabulary={vocabulary}
        // Not held for the vocabulary: until it loads a typed pattern only shows the field's hint.
        disabled={stale || lines.length >= MAX_LINES}
      />

      <h3 className="border-t border-line pt-4 font-bold text-slate-900">Advice and follow-up</h3>
      <AdviceEditor
        advice={body.advice}
        followUp={body.followUp}
        today={today}
        disabled={stale}
        onAdvice={(advice) => update({ ...body, advice })}
        onFollowUp={(followUp) => update({ ...body, followUp })}
        onLeave={() => void flush()}
      />
      <div>
        <label htmlFor={startId} className={LABEL}>
          Course starts on
        </label>
        <input
          id={startId}
          type="date"
          value={body.startsOn}
          min={addDays(today, -(vocabulary?.start_window_days ?? 30))}
          max={addDays(today, vocabulary?.start_window_days ?? 30)}
          disabled={stale}
          aria-describedby={`${startId}-hint`}
          onChange={(e) => update({ ...body, startsOn: e.target.value })}
          onBlur={() => void flush()}
          className={`${INPUT_BASE} mt-1`}
        />
        <p id={`${startId}-hint`} className="mt-1 text-sm text-slate-700">
          Leave it empty to start on the day it is issued.
          {draft?.previous_starts_on !== null && draft?.previous_starts_on !== undefined
            ? ` The version this revises started on ${formatDay(draft.previous_starts_on)}.`
            : ""}
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p role="status" aria-live="polite" className="text-sm text-slate-700">
          {stale ? "" : message === "" ? saveText(autosave.state) : `${message} ${saveText(autosave.state)}`}
        </p>
        <Button variant="primary" disabled={stale || isEmpty(body)} onClick={() => setOverlay({ kind: "review" })} icon={<FileCheck2 className="size-4" />}>
          Review and issue
        </Button>
      </div>
      {autosave.state.kind === "failed" && <ErrorNotice error={autosave.state.error} />}

      {overlay?.kind === "line" && lines[overlay.index] !== undefined && (
        <LineEditor
          line={lines[overlay.index] as Line}
          number={overlay.index + 1}
          vocabulary={vocabulary}
          onDone={(edited) => {
            setLines(lines.map((l, i) => (i === overlay.index ? edited : l)));
            setOverlay(undefined);
          }}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "favourite" && lines[overlay.index] !== undefined && (
        <SaveFavouriteDialog
          line={lines[overlay.index] as Line}
          onSaved={(f) => {
            setOverlay(undefined);
            setMessage(`Saved as favourite ${f.name}.`);
            setLibrary((n) => n + 1);
          }}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "template" && (
        <SaveTemplateDialog
          body={body}
          today={today}
          onSaved={(t) => {
            setOverlay(undefined);
            setMessage(`Saved as template ${t.name}.`);
            setLibrary((n) => n + 1);
          }}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "library" && (
        <LibraryDrawer
          favourites={favourites}
          templates={templates}
          onApply={applyTemplate}
          onChanged={() => setLibrary((n) => n + 1)}
          onClose={() => setOverlay(undefined)}
        />
      )}
      {overlay?.kind === "review" && (
        <IssueReview
          language={language}
          prepare={prepare}
          notes={lines.flatMap((line, i) => (warnings[i] ?? []).map((w) => `Line ${i + 1}, ${line.medicine_name}: ${WARNING_TEXT[w]}`))}
          onIssued={onIssued}
          onClose={() => setOverlay(undefined)}
        />
      )}
    </section>
  );
}
