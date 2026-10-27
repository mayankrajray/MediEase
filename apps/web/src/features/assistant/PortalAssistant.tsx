"use client";

import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { DEFAULT_ZONE, type PortalPrescription, usePortalLoad, zonesOf } from "@/features/portal/data";
import { PortalCard, ScreenLoading, usePortal } from "@/features/portal/PortalShell";
import { portalGet, portalPost } from "@/lib/auth/portal-session";
import { portalDate } from "@/lib/i18n/portal";

import { Chat } from "./Chat";
import { type Upload, UploadPanel, usableUpload } from "./UploadPanel";

/** A model may take a while; the API itself bounds each provider call (LLM_TIMEOUT_SECONDS). */
export const ASSISTANT_TIMEOUT_MS = 45_000;

async function loadChoices() {
  const [links, items] = await Promise.all([portalGet("/api/v1/portal/links"), portalGet("/api/v1/portal/prescriptions")]);
  return { zones: zonesOf(links.data.items), items: items.data.items as readonly PortalPrescription[] };
}

/**
 * The patient assistant (M7a-P4; FR-AI-01, 04; spec assistant R9, §6). The *prescription to ask
 * about* picker lists the account's current prescriptions (decision D7); the chosen one is sent
 * as the turn's context and the API re-checks it every turn. M7b: anything else (a family
 * member's, a paper one) is uploaded or its code typed in `UploadPanel`; once verified, with a
 * version chosen, that upload is the context instead.
 */
export function PortalAssistant() {
  const { s, leave } = usePortal();
  const params = useSearchParams();
  const loaded = usePortalLoad(loadChoices);
  const [chosen, setChosen] = useState<string>(params.get("rx") ?? "");
  const [upload, setUpload] = useState<Upload | null>(null);

  const items = loaded.status === "ready" ? loaded.data.items : [];
  const fromUpload = usableUpload(upload);
  const valid = fromUpload === null && items.some((p) => p.id === chosen) ? chosen : "";
  const a = s.assistant;
  const context = fromUpload !== null ? { upload_id: fromUpload } : valid === "" ? null : { prescription_id: valid };

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{a.title}</h1>
      <p className="text-slate-800">{a.intro}</p>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && (
        <PortalCard id="assistant-choice" title={a.choose}>
          {items.length === 0 ? (
            <p>{a.noPrescriptions}</p>
          ) : (
            <>
              <label htmlFor="assistant-prescription" className="sr-only">
                {a.choose}
              </label>
              <select
                id="assistant-prescription"
                value={valid}
                onChange={(event) => setChosen(event.target.value)}
                disabled={fromUpload !== null}
                className="block min-h-11 w-full rounded-lg border border-slate-300 bg-white p-2"
              >
                <option value="">{a.noChoice}</option>
                {items.map((p) => (
                  <option key={p.id} value={p.id}>
                    {a.option(p.doctor_name, p.clinic_name, portalDate(p.issued_at, loaded.data.zones.get(p.clinic_id) ?? DEFAULT_ZONE, s))}
                  </option>
                ))}
              </select>
            </>
          )}
          {fromUpload !== null && <p className="text-sm">{a.upload.asking}</p>}
        </PortalCard>
      )}
      <UploadPanel onChange={setUpload} />
      <Chat
        key={fromUpload === null ? valid : `${fromUpload}:${upload?.verification?.selected ?? ""}`}
        s={a}
        onLeave={leave}
        send={async (messages) =>
          (
            await portalPost(
              "/api/v1/portal/assistant/turns",
              { messages: [...messages], language: s.lang, context },
              { timeoutMs: ASSISTANT_TIMEOUT_MS },
            )
          ).data
        }
        confirm={async (token) =>
          (await portalPost("/api/v1/portal/assistant/confirm", { token, language: s.lang }, { timeoutMs: ASSISTANT_TIMEOUT_MS })).data
        }
      />
    </div>
  );
}
