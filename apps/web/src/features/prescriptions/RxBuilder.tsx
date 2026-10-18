"use client";

import { useCallback, useEffect, useImperativeHandle, useRef, useState, type KeyboardEvent, type Ref } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { saveText, useAutosave } from "@/features/visits/useAutosave";
import { ApiError } from "@/lib/api/client";
import { addDays } from "@/lib/format/time";

import { AdviceEditor } from "./AdviceEditor";
import { useRxApi, type Favourite, type Prescription, type RxTemplate } from "./api";
import { EMPTY_BODY, MAX_LINES, draftBody, fromPrescription, fromTemplate, isEmpty, moveLine, type Body, type Line } from "./draft";
import { EntryRow } from "./EntryRow";
import { IssueReview } from "./IssueReview";
import { LibraryDrawer, SaveFavouriteDialog, SaveTemplateDialog } from "./Library";
import { LineEditor } from "./LineEditor";
import { lineSummary } from "./vocabulary";

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
    },
    [api, visitId],
  );
  const autosave = useAutosave<Body>(save, endSession);
  const { flush, change } = autosave;
  const stale = autosave.state.kind === "stale";

  useEffect(() => register(flush), [register, flush]);

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

  const button = "rounded border border-slate-600 px-2 py-1 text-sm font-medium hover:bg-slate-100 disabled:text-slate-500";

  return (
    <section aria-labelledby="rx-heading" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="rx-heading" className="text-lg font-bold">
          Prescription{draft !== undefined && draft.version > 1 ? ` · version ${draft.version} (revision)` : ""}
        </h2>
        <div className="flex flex-wrap gap-2">
          <button type="button" disabled={stale} onClick={() => setOverlay({ kind: "library" })} className={button}>
            Templates and favourites
          </button>
          <button type="button" disabled={stale || isEmpty(body)} onClick={() => setOverlay({ kind: "template" })} className={button}>
            Save as template
          </button>
        </div>
      </div>

      {stale && (
        <div role="alert" className="rounded border border-amber-700 bg-amber-50 p-3">
          <p className="font-medium">{saveText(autosave.state)}</p>
          <button type="button" onClick={onReload} className="mt-2 rounded border border-amber-900 bg-white px-3 py-1.5 font-medium">
            Reload
          </button>
        </div>
      )}

      {lines.length > 0 && (
        <ol ref={listRef} aria-label="Medicines" className="space-y-1">
          {lines.map((line, index) => (
            <li
              key={line.key}
              data-line-key={line.key}
              onKeyDown={(event) => onLineKey(event, index, line.key)}
              className="flex flex-wrap items-center justify-between gap-2 rounded border border-slate-300 px-3 py-2"
            >
              <span>
                <span className="font-semibold">{index + 1}.</span> {lineSummary(line)}
                {(line.preparation?.length ?? 0) + (line.storage?.length ?? 0) > 0 && (
                  <span className="text-sm text-slate-700"> · with instructions</span>
                )}
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
                  className={button}
                >
                  ↑
                </button>
                <button
                  type="button"
                  data-action="down"
                  disabled={stale || index === lines.length - 1}
                  aria-label={`Move line ${index + 1} down`}
                  onClick={() => setLines(moveLine(lines, index, 1))}
                  className={button}
                >
                  ↓
                </button>
                <button
                  type="button"
                  data-action="favourite"
                  disabled={stale}
                  aria-label={`Save line ${index + 1} as favourite`}
                  onClick={() => setOverlay({ kind: "favourite", index })}
                  className={button}
                >
                  ☆ Favourite
                </button>
                <button
                  type="button"
                  data-action="remove"
                  disabled={stale}
                  aria-label={`Remove line ${index + 1}, ${line.medicine_name}`}
                  onClick={() => remove(index)}
                  className={`${button} border-red-800 text-red-900`}
                >
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {lines.length > 0 && <p className="text-sm text-slate-700">Alt+↑ and Alt+↓ move the line you are on.</p>}

      <EntryRow onAdd={(line) => setLines([...lines, line])} favourites={favourites} disabled={stale || lines.length >= MAX_LINES} />

      <h3 className="font-bold">Advice and follow-up</h3>
      <AdviceEditor
        advice={body.advice}
        followUp={body.followUp}
        today={today}
        disabled={stale}
        onAdvice={(advice) => update({ ...body, advice })}
        onFollowUp={(followUp) => update({ ...body, followUp })}
        onLeave={() => void flush()}
      />

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-300 pt-3">
        <p role="status" aria-live="polite" className="text-sm text-slate-800">
          {stale ? "" : message === "" ? saveText(autosave.state) : `${message} ${saveText(autosave.state)}`}
        </p>
        <button
          type="button"
          disabled={stale || isEmpty(body)}
          onClick={() => setOverlay({ kind: "review" })}
          className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:bg-slate-400"
        >
          Review and issue
        </button>
      </div>
      {autosave.state.kind === "failed" && <ErrorNotice error={autosave.state.error} />}

      {overlay?.kind === "line" && lines[overlay.index] !== undefined && (
        <LineEditor
          line={lines[overlay.index] as Line}
          number={overlay.index + 1}
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
        <IssueReview language={language} prepare={prepare} onIssued={onIssued} onClose={() => setOverlay(undefined)} />
      )}
    </section>
  );
}
