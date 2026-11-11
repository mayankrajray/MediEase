"use client";

import { PageHeader } from "@/components/ui/PageHeader";
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
  failed: {
    AI_UNAVAILABLE:
      "The assistant could not answer this time, because the AI service it uses did not reply properly. Your message is back in the box: press Send to try again, or do it from the Queue screen.",
    AI_PROVIDER_BUSY: "The AI service is busy. Wait about a minute, then press Send again. Your message is back in the box.",
    AI_RATE_LIMITED: "You sent several messages very quickly. Wait about a minute, then press Send again. Your message is back in the box.",
    offline: "This computer could not reach MediEase. Check the internet connection, then press Send again.",
  },
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
      <PageHeader title="Assistant" description="It works only with what your role can already do, and never gives medical advice." />
      <Chat
        s={STRINGS}
        onLeave={(error) => endSession(error)}
        send={async (messages) => (await sessionPost("/api/v1/assistant/turns", { messages: [...messages] }, options)).data}
        confirm={async (token) => (await sessionPost("/api/v1/assistant/confirm", { token }, options)).data}
      />
    </div>
  );
}
