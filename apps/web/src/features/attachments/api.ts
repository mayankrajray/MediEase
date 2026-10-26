/**
 * Reports attached to visits (M6d-P6; FR-VIS-04; spec visit-attachments). Every call names the
 * active clinic when the person has several and refreshes an expired session once. The file
 * itself is fetched as a blob, never opened by URL, so the request can name the clinic.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { fetchPdfAt } from "@/features/prescriptions/api";
import type { RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionDelete, sessionGet, sessionPostForm, sessionPut } from "@/lib/auth/refresh";

export type Attachment = components["schemas"]["VisitAttachment"];
export type PortalAttachment = components["schemas"]["PortalAttachmentList"]["items"][number];

/** R2: what the API takes; checked here only to say so before uploading. */
export const MAX_ATTACHMENT_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_TYPES = "application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";

export interface AttachmentsApi {
  readonly list: (visitId: string) => Promise<readonly Attachment[]>;
  readonly upload: (visitId: string, file: File) => Promise<Attachment>;
  readonly file: (visitId: string, attachmentId: string) => Promise<Blob>;
  readonly remove: (visitId: string, attachmentId: string) => Promise<void>;
  readonly share: (visitId: string, attachmentId: string, shared: boolean) => Promise<Attachment>;
}

export function useAttachmentsApi(): AttachmentsApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    const visit = (visitId: string): RequestOptions => ({ ...base, pathParams: { visit_id: visitId } });
    const one = (visitId: string, attachmentId: string): RequestOptions => ({
      ...base,
      pathParams: { visit_id: visitId, attachment_id: attachmentId },
    });
    return {
      list: async (visitId) => (await sessionGet("/api/v1/visits/{visit_id}/attachments", visit(visitId))).data.items,
      upload: async (visitId, file) => {
        const form = new FormData();
        form.append("file", file, file.name);
        return (await sessionPostForm("/api/v1/visits/{visit_id}/attachments", form, visit(visitId))).data;
      },
      file: (visitId, attachmentId) =>
        fetchPdfAt(`/api/v1/visits/${encodeURIComponent(visitId)}/attachments/${encodeURIComponent(attachmentId)}/file`, clinicId),
      remove: async (visitId, attachmentId) => {
        await sessionDelete("/api/v1/visits/{visit_id}/attachments/{attachment_id}", one(visitId, attachmentId));
      },
      share: async (visitId, attachmentId, shared) =>
        (await sessionPut("/api/v1/visits/{visit_id}/attachments/{attachment_id}/share", { shared }, one(visitId, attachmentId))).data,
    };
  }, [clinicId]);
}

/** "1.2 MB", "340 KB": the size people read. */
export function sizeText(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** R2 before sending: a type the API takes and at most 10 MB (the API decides by the bytes). */
export function fileProblem(file: File): string | undefined {
  if (file.size === 0) return "The file is empty.";
  if (file.size > MAX_ATTACHMENT_BYTES) return "The report must be at most 10 MB.";
  if (!/\.(pdf|jpe?g|png)$/i.test(file.name) && !["application/pdf", "image/jpeg", "image/png"].includes(file.type)) {
    return "The report must be a PDF, JPEG or PNG file.";
  }
  return undefined;
}

/** Saves a fetched file under its name (the browser opens or keeps it). */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
}
