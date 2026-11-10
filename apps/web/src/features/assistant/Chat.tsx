"use client";

import { Bot, ClipboardCheck, SendHorizontal, TriangleAlert, UserRound } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { INPUT, LABEL } from "@/components/ui/Field";
import { RichText } from "@/features/assistant/RichText";
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
    if (busy !== null) return;
    // DESIGN.md §8a: Send stays enabled; with nothing typed it puts the cursor in the box.
    if (text === "") {
      document.getElementById("assistant-message")?.focus();
      return;
    }
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
    <div className="overflow-hidden rounded-card border border-line bg-white shadow-card">
      <h2 className="sr-only">{s.conversation}</h2>
      <ol aria-label={s.conversation} aria-live="polite" className="min-h-48 space-y-3 bg-canvas/60 p-3 sm:p-4">
        {lines.length === 0 && (
          <li className="flex flex-col items-center gap-2 px-4 py-8 text-center text-slate-700">
            <span aria-hidden="true" className="grid size-11 place-items-center rounded-full bg-brand-50 text-brand-700">
              <Bot className="size-5" />
            </span>
            <span className="max-w-prose text-pretty">{s.empty}</span>
          </li>
        )}
        {lines.map((line, index) => {
          const mine = line.role === "user";
          const referral = line.kind === "REFERRAL";
          return (
            <li key={index} className={`flex items-end gap-2 ${mine ? "flex-row-reverse" : ""}`}>
              <span
                aria-hidden="true"
                className={`grid size-8 shrink-0 place-items-center rounded-full ${mine ? "bg-brand-700 text-white" : referral ? "bg-warning-soft text-warning" : "bg-white text-brand-700 ring-1 ring-line"}`}
              >
                {mine ? <UserRound className="size-4" /> : referral ? <TriangleAlert className="size-4" /> : <Bot className="size-4" />}
              </span>
              <div
                className={`min-w-0 max-w-[85%] rounded-2xl px-3.5 py-2.5 shadow-xs sm:max-w-[75%] ${
                  mine
                    ? "rounded-br-md bg-brand-700 text-white"
                    : referral
                      ? "rounded-bl-md border border-warning-line bg-warning-soft text-slate-900"
                      : "rounded-bl-md border border-line bg-white text-slate-900"
                }`}
              >
                <span className={`block text-xs font-semibold ${mine ? "text-brand-50" : "text-slate-600"}`}>{mine ? s.you : s.bot}</span>
                {mine ? <span className="whitespace-pre-line break-words">{line.content}</span> : <RichText text={line.content} />}
              </div>
            </li>
          );
        })}
        {busy === "send" && (
          <li aria-hidden="true" className="flex items-end gap-2">
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-white text-brand-700 ring-1 ring-line">
              <Bot className="size-4" />
            </span>
            <span className="inline-flex gap-1 rounded-2xl rounded-bl-md border border-line bg-white px-4 py-3.5">
              {/* Class delays, not a style attribute: the CSP allows no inline styles. */}
              {["[animation-delay:0ms]", "[animation-delay:150ms]", "[animation-delay:300ms]"].map((delay) => (
                <span key={delay} className={`size-1.5 animate-pulse rounded-full bg-slate-400 motion-reduce:animate-none ${delay}`} />
              ))}
            </span>
          </li>
        )}
        <li ref={end} aria-hidden="true" />
      </ol>

      {proposal !== null && (
        <div role="group" aria-label={s.confirm} className="m-3 space-y-3 rounded-xl border border-brand-200 bg-brand-50 p-3 sm:mx-4">
          <p className="flex items-start gap-2 font-medium text-slate-900">
            <ClipboardCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-brand-700" />
            <span>{proposal.summary}</span>
          </p>
          <div className="grid gap-2 min-[400px]:flex min-[400px]:flex-wrap">
            <Button variant="primary" onClick={() => void accept()} disabled={busy !== null} loading={busy === "confirm"} className="min-h-11">
              {busy === "confirm" ? s.confirming : s.confirm}
            </Button>
            <Button onClick={decline} disabled={busy !== null} className="min-h-11">
              {s.cancel}
            </Button>
          </div>
        </div>
      )}

      {error !== null && (
        <div className="px-3 pb-3 sm:px-4">
          <ErrorNotice error={error} />
        </div>
      )}

      <form onSubmit={(event) => void submit(event)} className="space-y-2 border-t border-line bg-white p-3 sm:p-4">
        <label htmlFor="assistant-message" className={LABEL}>
          {s.message}
        </label>
        <div className="flex items-end gap-2">
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
            className={`${INPUT} min-h-12 flex-1 resize-y`}
          />
          <Button type="submit" variant="primary" disabled={busy !== null} loading={busy === "send"} icon={<SendHorizontal className="size-4" />} className="min-h-12 shrink-0">
            {busy === "send" ? s.sending : s.send}
          </Button>
        </div>
      </form>
    </div>
  );
}