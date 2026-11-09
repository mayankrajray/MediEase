"use client";

import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { isRetryable } from "@/features/auth/messages";
import { apiPost } from "@/lib/api/client";
import { type PortalLanguage, verifyWords } from "@/lib/i18n/portal";

/**
 * The page the verification email opens (M6a-P4, FR-AUTH-08, ADR-0016 decision 6). Opening it
 * changes nothing: the person presses the button, which POSTs the token, so a mail scanner that
 * pre-fetches the link cannot verify an address nobody read.
 */
export function VerifyEmail({ token, language = "en" }: { token: string; language?: PortalLanguage }) {
  const words = verifyWords(language);
  const [state, setState] = useState<"ready" | "sending" | "done">("ready");
  const [error, setError] = useState<unknown>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (state === "done") doneRef.current?.focus();
  }, [state]);

  async function verify() {
    setState("sending");
    setError(null);
    try {
      await apiPost("/api/v1/portal/auth/verify-email", { token });
      setState("done");
    } catch (failure) {
      setError(failure);
      setState("ready");
    }
  }

  return (
    <section aria-labelledby="verify-heading" className="space-y-6 p-6 sm:p-8">
      <h1 id="verify-heading" className="heading-5">
        {words.heading}
      </h1>
      {state === "done" ? (
        <p
          ref={doneRef}
          tabIndex={-1}
          role="status"
          className="flex gap-3 rounded-xl border border-success-line bg-success-soft p-4 text-pretty text-slate-900"
        >
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-success" />
          <span>{words.done}</span>
        </p>
      ) : (
        <>
          <p className="text-pretty text-slate-700">{words.help}</p>
          {error !== null && (
            <ErrorNotice
              id="verify-error"
              ref={alertRef}
              error={error}
              {...(isRetryable(error) ? { onRetry: () => void verify() } : {})}
            />
          )}
          <Button variant="primary" size="lg" className="w-full" onClick={() => void verify()} loading={state === "sending"}>
            {state === "sending" ? words.confirming : words.confirm}
          </Button>
        </>
      )}
      <p className="text-center text-sm text-slate-700">
        <Link href="/portal" className="font-semibold text-brand-800 underline underline-offset-2">
          {words.goAccount}
        </Link>
      </p>
    </section>
  );
}
