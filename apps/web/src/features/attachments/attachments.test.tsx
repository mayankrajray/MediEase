import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { VISIT, VISIT_ID } from "@/features/visits/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, noContent } from "@/test/api";

import { AttachForm } from "./AttachForm";
import { AttachmentsPanel } from "./AttachmentsPanel";
import { fileProblem, sizeText, type Attachment } from "./api";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const REPORT_ID = "0192f0a0-0000-7000-8000-0000000009a1";
const doctorMember = membership(CLINIC_A, "Alpha Clinic", "DOCTOR", {
  permissions: ["CLINIC_VIEW", "CLINICAL_VIEW", "CLINICAL_WRITE", "ATTACHMENTS_ADD"],
});

function report(overrides: Partial<Attachment> = {}): Attachment {
  return {
    id: REPORT_ID,
    visit_id: VISIT_ID,
    filename: "cbc-report.pdf",
    content_type: "application/pdf",
    size_bytes: 245_760,
    uploaded_at: "2026-10-26T05:00:00+00:00",
    uploaded_by_user_id: "u-1",
    shared_with_patient: false,
    shared_at: null,
    can_delete: true,
    deletable_until: "2026-10-27T05:00:00+00:00",
    ...overrides,
  };
}

const routes = (items: readonly Attachment[]) => ({
  ...workspaceRoutes,
  "GET /api/v1/me": () => json(200, person([doctorMember])),
  [`GET ${VISIT}/attachments`]: () => json(200, { items }),
});

beforeEach(() => {
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.unstubAllGlobals();
});

describe("visit reports (M6d-P6, FR-VIS-04)", () => {
  it("R2: the type and size are checked before anything is sent", () => {
    expect(fileProblem(new File(["%PDF-"], "a.pdf", { type: "application/pdf" }))).toBeUndefined();
    expect(fileProblem(new File(["x"], "scan.JPG"))).toBeUndefined();
    expect(fileProblem(new File([""], "a.pdf"))).toBe("The file is empty.");
    expect(fileProblem(new File(["x"], "notes.docx", { type: "application/msword" }))).toBe("The report must be a PDF, JPEG or PNG file.");
    const big = new File(["x"], "big.pdf");
    Object.defineProperty(big, "size", { value: 10 * 1024 * 1024 + 1 });
    expect(fileProblem(big)).toBe("The report must be at most 10 MB.");
    expect([sizeText(245_760), sizeText(3 * 1024 * 1024), sizeText(10)]).toEqual(["240 KB", "3.0 MB", "1 KB"]);
  });

  it("R1, R4: attaching sends one multipart part named file and reports what the API says", async () => {
    const api = mockApi({
      ...routes([]),
      [`POST ${VISIT}/attachments`]: [
        () => apiError(422, "VIS_FILE_REJECTED", "The report must be a PDF, JPEG or PNG file.", {}, { reason: "type" }),
        () => json(201, report()),
      ],
    });
    const onAdded = vi.fn();
    renderInWorkspace(<AttachForm visitId={VISIT_ID} onAdded={onAdded} />);

    const input = await screen.findByLabelText("Attach a report");
    const button = screen.getByRole("button", { name: "Attach" });
    expect(button).toBeDisabled();
    fireEvent.change(input, { target: { files: [new File(["%PDF-1.7"], "cbc-report.pdf", { type: "application/pdf" })] } });
    fireEvent.click(button);
    expect(await screen.findByText("The report must be a PDF, JPEG or PNG file.")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Attach" }));
    await waitFor(() => expect(onAdded).toHaveBeenCalledWith(report()));
    const init = api.fetchMock.mock.calls.filter(([, i]) => i?.method === "POST").at(-1)?.[1];
    const body = init?.body as FormData;
    expect(body.get("file")).toBeInstanceOf(File);
    expect((body.get("file") as File).name).toBe("cbc-report.pdf");
    expect(new Headers(init?.headers).has("Content-Type")).toBe(false);
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("csrf-token");
  });

  it("a file of another type is refused on the screen and never sent", async () => {
    const api = mockApi(routes([]));
    renderInWorkspace(<AttachForm visitId={VISIT_ID} onAdded={vi.fn()} />);
    const input = await screen.findByLabelText("Attach a report");
    fireEvent.change(input, { target: { files: [new File(["x"], "notes.docx", { type: "application/msword" })] } });
    expect(screen.getByRole("alert")).toHaveTextContent("The report must be a PDF, JPEG or PNG file.");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("button", { name: "Attach" })).toBeDisabled();
    expect(api.count(`POST ${VISIT}/attachments`)).toBe(0);
  });

  it("R6-R10: the list downloads a report, the visit's doctor shares it and the uploader deletes it", async () => {
    let items = [report()];
    const api = mockApi({
      ...routes([]),
      [`GET ${VISIT}/attachments`]: () => json(200, { items }),
      [`GET ${VISIT}/attachments/${REPORT_ID}/file`]: () => new Response(new Blob(["%PDF-"]), { status: 200, headers: { "Content-Type": "application/pdf" } }),
      [`PUT ${VISIT}/attachments/${REPORT_ID}/share`]: () => {
        items = [report({ shared_with_patient: true, shared_at: "2026-10-26T06:00:00+00:00" })];
        return json(200, items[0]);
      },
      [`DELETE ${VISIT}/attachments/${REPORT_ID}`]: () => {
        items = [];
        return noContent();
      },
    });
    const createObjectURL = vi.fn(() => "blob:report");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    renderInWorkspace(<AttachmentsPanel visitId={VISIT_ID} canShare timeZone="Asia/Kolkata" />);

    const region = await screen.findByRole("region", { name: "Reports" });
    expect(await within(region).findByText("cbc-report.pdf", { selector: ".font-semibold" })).toBeInTheDocument();
    expect(within(region).getByText(/PDF · 240 KB · added/)).toBeInTheDocument();

    fireEvent.click(within(region).getByRole("button", { name: "Download cbc-report.pdf" }));
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(api.count(`GET ${VISIT}/attachments/${REPORT_ID}/file`)).toBe(1);

    fireEvent.click(within(region).getByRole("button", { name: "Share with patient cbc-report.pdf" }));
    expect(await within(region).findByText(/shared with the patient/)).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ shared: true });
    expect(within(region).getByRole("button", { name: "Stop sharing cbc-report.pdf" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(within(region).getByRole("button", { name: "Delete cbc-report.pdf" }));
    expect(await within(region).findByText("No reports attached.")).toBeInTheDocument();
    click.mockRestore();
  });

  it("R8, R10: someone else's report has no Delete, and only the visit's doctor shares", async () => {
    mockApi(routes([report({ can_delete: false })]));
    renderInWorkspace(<AttachmentsPanel visitId={VISIT_ID} canShare={false} timeZone="Asia/Kolkata" />);
    const region = await screen.findByRole("region", { name: "Reports" });
    await within(region).findByText("cbc-report.pdf", { selector: ".font-semibold" });
    expect(within(region).queryByRole("button", { name: /Delete/ })).not.toBeInTheDocument();
    expect(within(region).queryByRole("button", { name: /Share/ })).not.toBeInTheDocument();
    expect(within(region).getByRole("button", { name: "Download cbc-report.pdf" })).toBeInTheDocument();
  });
});
