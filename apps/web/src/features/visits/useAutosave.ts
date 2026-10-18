"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/client";

export const SAVE_DELAY_MS = 1000;
/** The codes that mean "another tab saved first": stop saving, offer a reload (decision 2A). */
export const STALE_CODES: readonly string[] = ["VIS_STALE", "RX_STALE"];

export type SaveState =
  | { readonly kind: "idle" }
  | { readonly kind: "pending" }
  | { readonly kind: "saving" }
  | { readonly kind: "saved"; readonly at: number }
  | { readonly kind: "stale" }
  | { readonly kind: "failed"; readonly error: unknown };

export interface Autosave<T> {
  readonly state: SaveState;
  /** Saves `value` about a second after the last change. */
  readonly change: (value: T) => void;
  /** Saves now what is waiting (leaving a field, or before issuing); resolves when all is saved. */
  readonly flush: () => Promise<boolean>;
}

/**
 * Autosave (M4-P6 decision 2A): a second after typing stops, and at once on `flush()`. Saves never
 * overlap: a change made while one is in flight is saved straight after it, so each save sends
 * the revision the previous one returned. A stale revision stops saving until the page reloads;
 * any other failure keeps the change and tries again on the next edit or flush.
 */
export function useAutosave<T>(save: (value: T) => Promise<void>, onEnd: (error: unknown) => boolean): Autosave<T> {
  const [state, setState] = useState<SaveState>({ kind: "idle" });
  const waiting = useRef<{ value: T } | undefined>(undefined);
  const running = useRef<Promise<boolean> | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const stale = useRef(false);
  const saveRef = useRef(save);
  const endRef = useRef(onEnd);
  useEffect(() => {
    saveRef.current = save;
    endRef.current = onEnd;
  });

  const run = useCallback((): Promise<boolean> => {
    const step = (): Promise<boolean> => {
      if (running.current !== undefined) return running.current.then(() => (waiting.current === undefined ? true : step()));
      const next = waiting.current;
      if (next === undefined || stale.current) return Promise.resolve(!stale.current);
      waiting.current = undefined;
      setState({ kind: "saving" });
      const attempt = saveRef.current(next.value).then(
        () => true,
        (error: unknown) => {
          if (error instanceof ApiError && STALE_CODES.includes(error.code)) {
            stale.current = true;
            setState({ kind: "stale" });
          } else {
            // Keep the change unless a newer one has come in since.
            waiting.current ??= next;
            if (!endRef.current(error)) setState({ kind: "failed", error });
          }
          return false;
        },
      );
      running.current = attempt.then((ok) => {
        running.current = undefined;
        if (ok) {
          if (waiting.current !== undefined) return step();
          setState({ kind: "saved", at: Date.now() });
        }
        return ok;
      });
      return running.current;
    };
    return step();
  }, []);

  const change = useCallback(
    (value: T) => {
      if (stale.current) return;
      waiting.current = { value };
      setState((s) => (s.kind === "saving" ? s : { kind: "pending" }));
      clearTimeout(timer.current);
      timer.current = setTimeout(() => void run(), SAVE_DELAY_MS);
    },
    [run],
  );

  const flush = useCallback(() => {
    clearTimeout(timer.current);
    return run();
  }, [run]);

  useEffect(() => () => clearTimeout(timer.current), []);

  return { state, change, flush };
}

/** The status line under a section: what autosave is doing, as text (never colour alone). */
export function saveText(state: SaveState): string {
  switch (state.kind) {
    case "idle":
      return "";
    case "pending":
      return "Unsaved changes…";
    case "saving":
      return "Saving…";
    case "saved":
      return "Saved";
    case "stale":
      return "Changed in another tab or by someone else. Reload to see the latest; nothing more is saved here.";
    case "failed":
      return "Not saved. It will try again when you next change something.";
  }
}
