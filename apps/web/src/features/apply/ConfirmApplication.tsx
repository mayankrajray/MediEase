"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { isRetryable } from "@/features/auth/messages";
import { ApiError, apiPost } from "@/lib/api/client";

import { REPLY_PROMISE } from "./lists";

/**
 * The page the confirmation email opens (M6c-P1; spec clinic-onboarding R11, R12). Opening it
 * changes nothing: the person presses the button, which POSTs the token, so a mail scanner that
 * fetches the link cannot confirm an application nobody read (as the patient verify page).
 */
export function ConfirmApplication({ token }: Readonly<{ token: string }>) {
  const [state, setState] = useState<"ready" | "sending" | "done" | "invalid">("ready");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<unknown>(null);
  const result = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (state === "done" || state === "invalid") result.current?.focus();
  }, [state]);

  async function confirm() {
    setState("sending");
    setError(null);
    try {
      const { data } = await apiPost("/api/v1/public/applications/confirm", { token });
      setReference(data.reference);
      setState("done");
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "ONB_CONFIRM_INVALID") {
        setState("invalid");
        return;
      }
      setError(failure);
      setState("ready");
    }
  }

  return (
    <section aria-labelledby="confirm-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="confirm-heading" className="text-2xl font-bold tracking-tight">
        Confirm your application
      </h1>
      {state === "done" && (
        <div className="space-y-3">
          <p ref={result} tabIndex={-1} role="status" className="rounded-lg border border-slate-300 bg-slate-50 p-3">
            Thank you. We received application <span className="font-semibold">{reference}</span> and will email you.
          </p>
          <p>{REPLY_PROMISE}</p>
        </div>
      )}
      {state === "invalid" && (
        <p ref={result} tabIndex={-1} role="alert" className="font-medium">
          This link is not valid any more. If you have not confirmed your application, please{" "}
          <a href="/apply" className="text-brand-800 underline">
            apply again
          </a>
          .
        </p>
      )}
      {(state === "ready" || state === "sending") && (
        <>
          <p className="text-slate-700">Press the button to send your application to MediEase for review.</p>
          {error !== null && <ErrorNotice error={error} {...(isRetryable(error) ? { onRetry: () => void confirm() } : {})} />}
          <Button variant="primary" className="w-full" onClick={() => void confirm()} disabled={state === "sending"}>
            {state === "sending" ? "Confirming…" : "Confirm my application"}
          </Button>
        </>
      )}
    </section>
  );
}
