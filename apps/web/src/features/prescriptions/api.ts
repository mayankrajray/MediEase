"use client";

/**
 * The visit, prescription, library and printing calls (M4-P6), in one place. Like the other
 * feature APIs, each names the active clinic when the person has several and refreshes an
 * expired session once.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { ApiError, CLINIC_HEADER, REQUEST_ID_HEADER, newRequestId, type RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionDelete, sessionGet, sessionPatch, sessionPost, sessionPut, withSessionRefresh } from "@/lib/auth/refresh";

type S = components["schemas"];
export type Consultation = S["Consultation"];
export type Visit = S["Visit"];
export type VisitChange = S["VisitChange"];
export type VisitSummary = S["VisitSummary"];
export type VisitPage = S["VisitPage"];
export type Vitals = S["Vitals"];
export type Prescription = S["Prescription"];
export type PrescriptionDraft = S["PrescriptionDraft"];
export type ItemInput = S["PrescriptionItemInput"];
export type ItemOutput = S["PrescriptionItemOutput"];
export type AdviceInput = S["AdviceInput"];
export type Frequency = S["Frequency"];
export type Slot = S["Slot"];
export type DurationKind = S["DurationKind"];
export type LineWarning = S["LineWarning"];
export type Vocabulary = S["RxVocabulary"];
export type Timing = S["Timing"];
export type PreparationPhrase = S["PreparationPhrase"];
export type StoragePhrase = S["StoragePhrase"];
export type Favourite = S["Favourite"];
export type RxTemplate = S["RxTemplate"];
export type Suggestion = S["MedicineSuggestions"]["items"][number];
export type PatientPage = S["PatientPrescriptionPage"];
export type LinkInfo = S["PatientLinkInfo"];
export type Printable = S["PrintablePrescription"];

export interface RxApi {
  readonly clinicId: string | undefined;
  readonly startVisit: (appointmentId: string) => Promise<Visit>;
  readonly consultation: (visitId: string) => Promise<Consultation>;
  readonly updateVisit: (visitId: string, change: VisitChange) => Promise<Visit>;
  readonly completeVisit: (visitId: string) => Promise<Visit>;
  readonly addAddendum: (visitId: string, body: string) => Promise<S["VisitAddendum"]>;
  readonly patientVisits: (patientId: string, before?: string) => Promise<VisitPage>;
  readonly createDraft: (visitId: string) => Promise<Prescription>;
  readonly saveDraft: (rxId: string, draft: PrescriptionDraft) => Promise<Prescription>;
  readonly issue: (rxId: string, revision: number) => Promise<Prescription>;
  readonly revise: (rxId: string) => Promise<Prescription>;
  readonly preview: (rxId: string, lang?: "en" | "hi") => Promise<PatientPage>;
  readonly link: (rxId: string) => Promise<LinkInfo>;
  readonly resetLink: (rxId: string) => Promise<LinkInfo>;
  readonly printable: (patientId: string) => Promise<readonly Printable[]>;
  readonly pdf: (rxId: string) => Promise<Blob>;
  readonly suggestions: (q: string, signal?: AbortSignal) => Promise<readonly Suggestion[]>;
  readonly favourites: () => Promise<readonly Favourite[]>;
  readonly saveFavourite: (name: string, item: ItemInput) => Promise<Favourite>;
  readonly deleteFavourite: (id: string) => Promise<void>;
  readonly templates: () => Promise<readonly RxTemplate[]>;
  readonly saveTemplate: (body: S["RxTemplateInput"]) => Promise<RxTemplate>;
  readonly renameTemplate: (template: RxTemplate, name: string) => Promise<RxTemplate>;
  readonly deleteTemplate: (id: string) => Promise<void>;
  /** M6b-P3: the engine's slot sets and codes (prescriptions R21, D8). */
  readonly vocabulary: () => Promise<Vocabulary>;
}

const PDF_TIMEOUT_MS = 30_000;

/**
 * The prescription PDF as a blob (M4-P4). Fetched rather than opened by URL so the request can
 * name the clinic (`X-Clinic-ID`); `RX_PDF_BUSY` (another download is rendering it) is retried once
 * after the `Retry-After` the API gives.
 */
export async function fetchPdf(rxId: string, clinicId: string | undefined, fetchImpl: typeof fetch = fetch): Promise<Blob> {
  const once = async (): Promise<Blob> => {
    const requestId = newRequestId();
    const headers: Record<string, string> = { Accept: "application/pdf, application/json", [REQUEST_ID_HEADER]: requestId };
    if (clinicId !== undefined) headers[CLINIC_HEADER] = clinicId;
    let response: Response;
    try {
      response = await fetchImpl(`/api/v1/prescriptions/${encodeURIComponent(rxId)}/pdf`, {
        headers,
        credentials: "same-origin",
        cache: "no-store",
        signal: AbortSignal.timeout(PDF_TIMEOUT_MS),
      });
    } catch {
      throw new ApiError("WEB_API_UNREACHABLE", "The API could not be reached.", 0, requestId, { reason: "network" });
    }
    if (response.ok) return response.blob();
    const id = response.headers.get(REQUEST_ID_HEADER) ?? requestId;
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      body = undefined;
    }
    const error = (body as { error?: { code?: string; message?: string; details?: Record<string, unknown> } } | undefined)?.error;
    const retry = Number(response.headers.get("Retry-After") ?? Number.NaN);
    throw new ApiError(
      error?.code ?? "WEB_API_BAD_RESPONSE",
      error?.message ?? "The API sent an unexpected response.",
      response.status,
      id,
      error?.details ?? {},
      Number.isFinite(retry) ? retry : undefined,
    );
  };
  return withSessionRefresh(async () => {
    try {
      return await once();
    } catch (error) {
      if (error instanceof ApiError && error.code === "RX_PDF_BUSY") {
        await new Promise((resolve) => setTimeout(resolve, Math.min(error.retryAfterSeconds ?? 2, 10) * 1000));
        return once();
      }
      throw error;
    }
  });
}

export function useRxApi(): RxApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const visit = (id: string): RequestOptions => ({ ...base, pathParams: { visit_id: id } });
    const rx = (id: string): RequestOptions => ({ ...base, pathParams: { rx_id: id } });
    return {
      clinicId,
      startVisit: async (appointmentId) => (await sessionPost("/api/v1/visits", { appointment_id: appointmentId }, base)).data,
      consultation: async (id) => (await sessionGet("/api/v1/visits/{visit_id}", visit(id))).data,
      updateVisit: async (id, change) => (await sessionPatch("/api/v1/visits/{visit_id}", change, visit(id))).data,
      completeVisit: async (id) => (await sessionPost("/api/v1/visits/{visit_id}/complete", undefined, visit(id))).data,
      addAddendum: async (id, body) => (await sessionPost("/api/v1/visits/{visit_id}/addenda", { body }, visit(id))).data,
      patientVisits: async (patientId, before) =>
        (
          await sessionGet("/api/v1/patients/{patient_id}/visits", {
            ...base,
            pathParams: { patient_id: patientId },
            ...(before === undefined ? {} : { query: { before } }),
          })
        ).data,
      createDraft: async (visitId) => (await sessionPost("/api/v1/visits/{visit_id}/prescriptions", undefined, visit(visitId))).data,
      saveDraft: async (id, draft) => (await sessionPut("/api/v1/prescriptions/{rx_id}", draft, rx(id))).data,
      issue: async (id, revision) => (await sessionPost("/api/v1/prescriptions/{rx_id}/issue", { revision }, rx(id))).data,
      revise: async (id) => (await sessionPost("/api/v1/prescriptions/{rx_id}/revise", undefined, rx(id))).data,
      preview: async (id, lang) => (await sessionGet("/api/v1/prescriptions/{rx_id}/preview", { ...rx(id), query: { lang } })).data,
      link: async (id) => (await sessionGet("/api/v1/prescriptions/{rx_id}/link", rx(id))).data,
      resetLink: async (id) => (await sessionPost("/api/v1/prescriptions/{rx_id}/link/reset", undefined, rx(id))).data,
      printable: async (patientId) =>
        (await sessionGet("/api/v1/patients/{patient_id}/prescriptions", { ...base, pathParams: { patient_id: patientId } })).data
          .items,
      pdf: (id) => fetchPdf(id, clinicId),
      suggestions: async (q, signal) =>
        (await sessionGet("/api/v1/medicine-suggestions", { ...base, query: { q }, ...(signal === undefined ? {} : { signal }) })).data
          .items,
      favourites: async () => (await sessionGet("/api/v1/rx-favourites", base)).data.items,
      saveFavourite: async (name, item) => (await sessionPost("/api/v1/rx-favourites", { name, item }, base)).data,
      deleteFavourite: async (id) => {
        await sessionDelete("/api/v1/rx-favourites/{favourite_id}", { ...base, pathParams: { favourite_id: id } });
      },
      templates: async () => (await sessionGet("/api/v1/rx-templates", base)).data.items,
      saveTemplate: async (body) => (await sessionPost("/api/v1/rx-templates", body, base)).data,
      renameTemplate: async (template, name) =>
        (
          await sessionPut(
            "/api/v1/rx-templates/{template_id}",
            {
              name,
              items: template.items as ItemInput[],
              advice: template.advice,
              follow_up_days: template.follow_up_days,
              revision: template.revision,
            },
            { ...base, pathParams: { template_id: template.id } },
          )
        ).data,
      deleteTemplate: async (id) => {
        await sessionDelete("/api/v1/rx-templates/{template_id}", { ...base, pathParams: { template_id: id } });
      },
      vocabulary: async () => (await sessionGet("/api/v1/rx-vocabulary", base)).data,
    };
  }, [clinicId]);
}
