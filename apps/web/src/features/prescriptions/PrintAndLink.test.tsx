import { fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderInWorkspace } from "@/features/patients/testing";
import { screenRoutes, RX, RX_ID } from "@/features/visits/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { ApiError } from "@/lib/api/client";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { fetchPdf } from "./api";
import { LinkPanel, PrintButton } from "./PrintAndLink";

const qrTexts: string[] = [];
vi.mock("qrcode", () => ({
  default: {
    toDataURL: async (text: string) => {
      qrTexts.push(text);
      return "data:image/png;base64,AAAA";
    },
  },
}));
vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  qrTexts.length = 0;
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  vi.restoreAllMocks();
});

const pdf = () => new Response("%PDF-1.7", { status: 200, headers: { "Content-Type": "application/pdf" } });
const link = (locked = false) =>
  json(200, {
    id: "0192f0a0-0000-7000-8000-0000000004c1",
    url: "https://sample.example/p/sample-token",
    expires_at: "2027-01-16T05:00:00+00:00",
    locked,
    open_count: 2,
    last_opened_at: "2026-10-18T06:00:00+00:00",
  });

describe("printing (M4-P4, spec D6)", () => {
  it("R18: RX_PDF_BUSY is tried once more after Retry-After, with the clinic named", async () => {
    const calls: Headers[] = [];
    const responses = [apiError(503, "RX_PDF_BUSY", "The prescription is being prepared", { "Retry-After": "0" }), pdf()];
    const fake = vi.fn<typeof fetch>(async (_url, init) => {
      calls.push(new Headers(init?.headers));
      return responses.shift() as Response;
    });

    const blob = await fetchPdf(RX_ID, "clinic-a", fake);

    expect(await blob.text()).toBe("%PDF-1.7");
    expect(fake).toHaveBeenCalledTimes(2);
    expect(calls.every((h) => h.get("X-Clinic-ID") === "clinic-a")).toBe(true);
  });

  it("a second RX_PDF_BUSY is reported, not retried for ever", async () => {
    const fake = vi.fn<typeof fetch>(async () => apiError(503, "RX_PDF_BUSY", "The prescription is being prepared", { "Retry-After": "0" }));
    await expect(fetchPdf(RX_ID, undefined, fake)).rejects.toSatisfy((e: unknown) => e instanceof ApiError && e.code === "RX_PDF_BUSY");
    expect(fake).toHaveBeenCalledTimes(2);
  });

  it("Print opens the tab at the click and points it at the PDF; a refused pop-up downloads it instead", async () => {
    mockApi({ ...screenRoutes(), [`GET ${RX}/pdf`]: () => pdf() });
    Object.assign(URL, { createObjectURL: vi.fn(() => "blob:rx"), revokeObjectURL: vi.fn() });
    const tab = { location: { href: "" }, close: vi.fn() };
    const opened = vi.spyOn(window, "open").mockReturnValueOnce(tab as unknown as Window).mockReturnValueOnce(null);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderInWorkspace(<PrintButton rxId={RX_ID} name="Print the prescription" />);

    fireEvent.click(await screen.findByRole("button", { name: "Print the prescription" }));
    await waitFor(() => expect(tab.location.href).toBe("blob:rx"));
    expect(opened).toHaveBeenCalledWith("", "_blank");

    fireEvent.click(screen.getByRole("button", { name: "Print the prescription" }));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
  });

  it("a failed PDF closes the empty tab and says why", async () => {
    mockApi({ ...screenRoutes(), [`GET ${RX}/pdf`]: () => apiError(500, "RX_PDF_FAILED", "The prescription could not be prepared. Try again") });
    const tab = { location: { href: "" }, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    renderInWorkspace(<PrintButton rxId={RX_ID} name="Print the prescription" />);

    fireEvent.click(await screen.findByRole("button", { name: "Print the prescription" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The prescription could not be prepared");
    expect(tab.close).toHaveBeenCalled();
  });
});

describe("the patient link (spec D2, M4-P5)", () => {
  it("the QR code encodes exactly the link that is shown and copied", async () => {
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    mockApi({ ...screenRoutes(), [`GET ${RX}/link`]: () => link() });
    renderInWorkspace(<LinkPanel rxId={RX_ID} />);

    expect(await screen.findByRole("img", { name: /QR code/ })).toBeInTheDocument();
    expect(qrTexts).toEqual(["https://sample.example/p/sample-token"]);
    expect(screen.getByTestId("patient-link")).toHaveTextContent("https://sample.example/p/sample-token");
    expect(screen.getByText(/Opened 2 times/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    expect(await screen.findByText("Link copied.")).toBeInTheDocument();
    expect(writeText).toHaveBeenCalledWith("https://sample.example/p/sample-token");
    expect(screen.queryByRole("button", { name: "Unlock link" })).not.toBeInTheDocument();
  });

  it("AC3: a locked link says so and staff can unlock it", async () => {
    const api = mockApi({
      ...screenRoutes(),
      [`GET ${RX}/link`]: () => link(true),
      [`POST ${RX}/link/reset`]: () => link(false),
    });
    renderInWorkspace(<LinkPanel rxId={RX_ID} />);

    expect(await screen.findByText(/Locked after 5 wrong attempts/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Unlock link" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Unlock link" })).not.toBeInTheDocument());
    expect(api.count(`POST ${RX}/link/reset`)).toBe(1);
  });
});
