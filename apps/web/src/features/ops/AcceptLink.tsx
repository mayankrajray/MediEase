"use client";

import { useRef, useState } from "react";

/**
 * The invitation link, shown once (the API returns the secret in exactly one
 * response and keeps only its digest). Hand it over in person or by phone
 * (RUNBOOK §10): anyone who has it can join the clinic until it expires or is
 * replaced by a new invitation.
 */
export function AcceptLink({ url, name }: { url: string; name: string }) {
  const field = useRef<HTMLInputElement>(null);
  const [copied, setCopied] = useState<"idle" | "copied" | "manual">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied("copied");
    } catch {
      // Clipboard access can be denied: select the text so Ctrl+C works.
      field.current?.select();
      setCopied("manual");
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-slate-400 bg-slate-50 p-4">
      <label htmlFor="accept-link" className="block font-medium">
        Invitation link for {name}
      </label>
      <div className="flex gap-2">
        <input
          id="accept-link"
          ref={field}
          readOnly
          value={url}
          onFocus={(event) => event.target.select()}
          className="w-full rounded-lg border border-slate-400 bg-white px-3 py-2 font-mono text-sm"
        />
        <button
          type="button"
          onClick={() => void copy()}
          className="rounded-lg border border-slate-400 bg-white px-3 py-2 font-medium hover:bg-slate-100"
        >
          Copy link
        </button>
      </div>
      <p role="status" className="min-h-6 text-sm">
        {copied === "copied" && "Link copied."}
        {copied === "manual" && "Could not copy automatically. The link is selected: press Ctrl+C."}
      </p>
      <p className="text-sm text-slate-800">
        This link is shown <strong>only now</strong>. Give it to {name} in person or by phone; it is valid for 7 days. If it
        is lost, invite them again and the new link replaces this one.
      </p>
    </div>
  );
}
