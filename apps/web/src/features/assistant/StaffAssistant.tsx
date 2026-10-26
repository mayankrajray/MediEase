"use client";

import { useSession } from "@/features/auth/SessionProvider";
import type { RequestOptions } from "@/lib/api/client";
import { sessionPost } from "@/lib/auth/refresh";

import { Chat, type ChatStrings } from "./Chat";
import { ASSISTANT_TIMEOUT_MS } from "./PortalAssistant";

const STRINGS: ChatStrings = {
  conversation: "Conversation",
  empty: "Ask about today's queue, a day's sessions, a patient, or book, cancel or move an appointment.",
  message: "Message",
  placeholder: "For example: show today's queue",
  send: "Send",
  sending: "Sending…",
  you: "You",
  bot: "Assistant",
  confirm: "Confirm",
  confirming: "Confirming…",
  cancel: "Cancel",
  cancelled: "Nothing was changed.",
};

/**
 * The staff assistant (M7a-P5; FR-AI-01; spec assistant §6). It acts with the member's own
 * permissions; every change it proposes waits for *Confirm*. It has no clinical tools.
 */
export function StaffAssistant() {
  const { clinic, endSession } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;
  const options: RequestOptions = { timeoutMs: ASSISTANT_TIMEOUT_MS, ...(clinicId === undefined ? {} : { clinicId }) };

  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Assistant</h1>
      <p className="text-slate-700">
        It works only with what your role can already do, and never gives medical advice.
      </p>
      <Chat
        s={STRINGS}
        onLeave={(error) => endSession(error)}
        send={async (messages) => (await sessionPost("/api/v1/assistant/turns", { messages: [...messages] }, options)).data}
        confirm={async (token) => (await sessionPost("/api/v1/assistant/confirm", { token }, options)).data}
      />
    </div>
  );
}
