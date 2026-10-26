"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";

export type AssistantReply = components["schemas"]["AssistantReply"];
export type AssistantMessage = components["schemas"]["AssistantMessage"];

export interface ChatStrings {
  readonly conversation: string;
  readonly empty: string;
  readonly message: string;
  readonly placeholder: string;
  readonly send: string;
  readonly sending: string;
  readonly you: string;
  readonly bot: string;
  readonly confirm: string;
  readonly confirming: string;
  readonly cancel: string;
  readonly cancelled: string;
}

interface Line {
  readonly role: "user" | "assistant";
  readonly content: string;
  readonly kind?: AssistantReply["kind"];
}

/**
 * The conversation (M7a-P4, P5; spec assistant §6), shared by the patient and staff pages.
 *
 * The visible conversation is the whole state: each turn sends it (at most 20 messages, the last
 * the user's) and the reply is appended. A proposal shows its summary with *Confirm* and *Cancel*;
 * only *Confirm* writes anything. `onLeave` lets the page send an ended session to sign-in. The
 * page gives it a `key` per chosen prescription, so choosing another starts a new conversation.
 */
export function Chat({
  s,
  send,
  confirm,
  onLeave,
}: Readonly<{
  s: ChatStrings;
  send: (messages: readonly AssistantMessage[]) => Promise<AssistantReply>;
  confirm: (token: string) => Promise<AssistantReply>;
  onLeave?: (error: unknown) => boolean;
}>) {
  const [lines, setLines] = useState<readonly Line[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<"send" | "confirm" | null>(null);
  const [proposal, setProposal] = useState<AssistantReply["proposal"]>(null);
  const [error, setError] = useState<unknown>(null);
  const end = useRef<HTMLLIElement | null>(null);

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [lines]);

  function failed(failure: unknown) {
    if (!(onLeave?.(failure) ?? false)) setError(failure);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = draft.trim();
    if (text === "" || busy !== null) return;
    const next: Line[] = [...lines, { role: "user", content: text }];
    setLines(next);
    setDraft("");
    setProposal(null);
    setError(null);
    setBusy("send");
    try {
      const history = next.slice(-20).map(({ role, content }) => ({ role, content }));
      const reply = await send(history);
      setLines([...next, { role: "assistant", content: reply.reply, kind: reply.kind }]);
      setProposal(reply.proposal);
    } catch (failure) {
      failed(failure);
    } finally {
      setBusy(null);
    }
  }

  async function accept() {
    if (proposal === null || busy !== null) return;
    setBusy("confirm");
    setError(null);
    try {
      const reply = await confirm(proposal.token);
      setLines((current) => [...current, { role: "assistant", content: reply.reply, kind: reply.kind }]);
      setProposal(null);
    } catch (failure) {
      failed(failure);
    } finally {
      setBusy(null);
    }
  }

  function decline() {
    setProposal(null);
    setLines((current) => [...current, { role: "assistant", content: s.cancelled }]);
  }

  return (
    <div className="space-y-3">
      <h2 className="sr-only">{s.conversation}</h2>
      <ol aria-label={s.conversation} aria-live="polite" className="space-y-2">
        {lines.length === 0 && <li className="text-slate-700">{s.empty}</li>}
        {lines.map((line, index) => (
          <li
            key={index}
            className={
              line.role === "user"
                ? "ml-8 rounded-lg bg-brand-50 p-3"
                : `mr-8 rounded-lg border p-3 ${line.kind === "REFERRAL" ? "border-amber-400 bg-amber-50" : "border-slate-200 bg-white"}`
            }
          >
            <span className="block text-xs font-semibold text-slate-700">{line.role === "user" ? s.you : s.bot}</span>
            <span className="whitespace-pre-line break-words">{line.content}</span>
          </li>
        ))}
        <li ref={end} aria-hidden="true" />
      </ol>

      {proposal !== null && (
        <div role="group" aria-label={s.confirm} className="rounded-lg border border-brand-700 bg-white p-3">
          <p className="font-medium">{proposal.summary}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void accept()}
              disabled={busy !== null}
              className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-4 font-semibold text-white hover:bg-brand-800 disabled:opacity-60"
            >
              {busy === "confirm" ? s.confirming : s.confirm}
            </button>
            <button
              type="button"
              onClick={decline}
              disabled={busy !== null}
              className="inline-flex min-h-11 items-center rounded-lg border border-slate-300 px-4 font-medium"
            >
              {s.cancel}
            </button>
          </div>
        </div>
      )}

      {error !== null && <ErrorNotice error={error} />}

      <form onSubmit={(event) => void submit(event)} className="space-y-2">
        <label htmlFor="assistant-message" className="block font-medium">
          {s.message}
        </label>
        <textarea
          id="assistant-message"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          maxLength={2000}
          rows={2}
          placeholder={s.placeholder}
          className="block w-full rounded-lg border border-slate-300 p-2"
        />
        <button
          type="submit"
          disabled={busy !== null || draft.trim() === ""}
          className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-5 font-semibold text-white hover:bg-brand-800 disabled:opacity-60"
        >
          {busy === "send" ? s.sending : s.send}
        </button>
      </form>
    </div>
  );
}
