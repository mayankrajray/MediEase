import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { person } from "@/features/auth/testing";
import { renderInWorkspace } from "@/features/patients/testing";
import { doctor } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi, type Recorded } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import { ConsultationScreen } from "./ConsultationScreen";
import { RX, VISIT, VISIT_ID, consultation, doctorMember, page, rx, screenRoutes, syrupLine, visit } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
  vi.useRealTimers();
});

async function open() {
  renderInWorkspace(<ConsultationScreen visitId={VISIT_ID} />);
  return screen.findByRole("heading", { level: 1 }, { timeout: 5000 });
}

const builder = () => screen.getByRole("region", { name: /^Prescription/ });
const entry = () => screen.getByRole("group", { name: "New medicine" });
const put = (api: { calls: Recorded[] }) => api.calls.filter((c) => c.method === "PUT" && c.path === RX);

/** The draft routes: created on the first save, each save one revision on. */
function draftRoutes() {
  let revision = 1;
  return {
    [`POST ${VISIT}/prescriptions`]: () => json(201, rx({ revision })),
    [`PUT ${RX}`]: () => json(200, rx({ revision: ++revision })),
  };
}

function typeLine(name: string, values: { dose?: string; frequency?: string; timing?: string; days?: string }) {
  const row = entry();
  fireEvent.change(within(row).getByRole("combobox", { name: "Medicine" }), { target: { value: name } });
  if (values.dose !== undefined) fireEvent.change(within(row).getByLabelText("Dose"), { target: { value: values.dose } });
  if (values.frequency !== undefined) fireEvent.change(within(row).getByLabelText("Frequency"), { target: { value: values.frequency } });
  if (values.timing !== undefined) fireEvent.change(within(row).getByLabelText("Timing"), { target: { value: values.timing } });
  if (values.days !== undefined) fireEvent.change(within(row).getByLabelText("Days"), { target: { value: values.days } });
}

describe("consultation screen (M4-P6, spec §6)", () => {
  it("journey 2: the patient, the earlier visits and, for the visit's doctor, the notes and builder", async () => {
    mockApi(screenRoutes());
    const heading = await open();

    expect(heading).toHaveTextContent("Bina Shah");
    expect(screen.getByText(/SC-0004 · about 47 years · Female · reads English/)).toBeInTheDocument();
    const history = screen.getByRole("region", { name: "Earlier visits" });
    expect(within(history).getByText("Complaint: Earlier complaint")).toBeInTheDocument();
    expect(within(history).getByText("Tablet Sample · 1 · 1-0-1 · after food · 3 days")).toBeInTheDocument();
    expect(screen.getByLabelText("Chief complaint")).toBeEnabled();
    expect(screen.getByLabelText("BP systolic (mmHg)")).toBeInTheDocument();
    expect(within(builder()).getByRole("button", { name: "Review and issue" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Complete visit" })).toBeInTheDocument();
  });

  it("the entry row: Enter on the last field adds the line and returns to the medicine; the draft is created on first save", async () => {
    const api = mockApi({ ...screenRoutes(), ...draftRoutes() });
    await open();

    typeLine("Syrup X", { dose: "5 ml", frequency: "101", timing: "AFTER_FOOD", days: "5" });
    expect(within(entry()).getByText("1-0-1 · morning and night")).toBeInTheDocument();
    fireEvent.keyDown(within(entry()).getByLabelText("Days"), { key: "Enter" });

    const list = within(builder()).getByRole("list", { name: "Medicines" });
    expect(list).toHaveTextContent("1. Syrup X · 5 ml · 1-0-1 · after food · 5 days");
    expect(within(entry()).getByRole("combobox", { name: "Medicine" })).toHaveFocus();
    expect(within(entry()).getByRole("combobox", { name: "Medicine" })).toHaveValue("");

    // Decision 2A: saved about a second later, with the revision the create returned.
    await waitFor(() => expect(put(api)).toHaveLength(1), { timeout: 3000 });
    expect(api.count(`POST ${VISIT}/prescriptions`)).toBe(1);
    expect(put(api)[0]?.body).toMatchObject({
      revision: 1,
      items: [{ medicine_name: "Syrup X", dose: "5 ml", frequency: "1-0-1", timing: "AFTER_FOOD", duration_days: 5 }],
      follow_up_date: null,
    });
    expect(await within(builder()).findByText(/Saved$/)).toBeInTheDocument();
  });

  it("the entry row refuses a frequency it cannot read and asks for the custom words after C", async () => {
    mockApi(screenRoutes());
    await open();

    typeLine("Syrup X", { frequency: "1x" });
    expect(within(entry()).getByLabelText("Frequency")).toHaveAttribute("aria-invalid", "true");
    fireEvent.keyDown(within(entry()).getByLabelText("Frequency"), { key: "Enter" });
    expect(within(builder()).queryByRole("list", { name: "Medicines" })).not.toBeInTheDocument();

    fireEvent.change(within(entry()).getByLabelText("Frequency"), { target: { value: "c" } });
    fireEvent.keyDown(within(entry()).getByLabelText("Frequency"), { key: "Enter" });
    expect(within(entry()).getByText("Say how often")).toBeInTheDocument();
    fireEvent.change(within(entry()).getByLabelText("How often (custom)"), { target: { value: "every other day" } });
    fireEvent.keyDown(within(entry()).getByLabelText("How often (custom)"), { key: "Enter" });
    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent("Syrup X · every other day");
  });

  it("M6b-P3 (R21-R23): any 0/1 pattern the API publishes, never all zeros; until review; the API's bedtime note under the line", async () => {
    let revision = 1;
    const api = mockApi({
      ...screenRoutes(),
      [`POST ${VISIT}/prescriptions`]: () => json(201, rx({ revision })),
      [`PUT ${RX}`]: () =>
        json(200, rx({ revision: ++revision, items: [{ ...syrupLine, frequency: "1-1-0", slots: ["MORNING", "AFTERNOON"], timing: "BEDTIME", line_warnings: ["BEDTIME_WITHOUT_NIGHT"] }] })),
    });
    await open();

    typeLine("Tab Sample", { frequency: "000" });
    expect(within(entry()).getByLabelText("Frequency")).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(within(entry()).getByLabelText("Frequency"), { target: { value: "110" } });
    expect(within(entry()).getByText("1-1-0 · morning and afternoon")).toBeInTheDocument();
    fireEvent.change(within(entry()).getByLabelText("Timing"), { target: { value: "BEDTIME" } });
    fireEvent.change(within(entry()).getByLabelText("Days"), { target: { value: "r" } });
    fireEvent.keyDown(within(entry()).getByLabelText("Days"), { key: "Enter" });
    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent("Tab Sample · 1-1-0 · at bedtime · until review");

    await waitFor(() => expect(put(api)).toHaveLength(1), { timeout: 3000 });
    expect(put(api)[0]?.body).toMatchObject({ items: [{ frequency: "1-1-0", duration_kind: "UNTIL_REVIEW", duration_days: null }], starts_on: null });
    expect(await within(builder()).findByText(/Check: At bedtime, but the frequency has no night dose/)).toBeInTheDocument();
  });

  it("FR-RX-05: a favourite picked from the suggestions inserts its whole line", async () => {
    const favourite = {
      id: "0192f0a0-0000-7000-8000-0000000006d1",
      name: "Syrup X kids",
      item: { ...syrupLine, preparation: [{ code: "DILUTE_IN_WATER", text: "10 ml" }] },
      revision: 1,
      use_count: 3,
      last_used_at: null,
      updated_at: "2026-10-01T00:00:00+00:00",
    };
    const api = mockApi({
      ...screenRoutes(),
      ...draftRoutes(),
      "GET /api/v1/rx-favourites": () => json(200, { items: [favourite] }),
      "GET /api/v1/medicine-suggestions": () =>
        json(200, { items: [{ name: "Syrup X", source: "FAVOURITE", uses: 3, favourite_id: favourite.id }] }),
    });
    await open();

    const medicine = within(entry()).getByRole("combobox", { name: "Medicine" });
    fireEvent.change(medicine, { target: { value: "Sy" } });
    expect(await screen.findByRole("option", { name: /Syrup X · favourite/ }, { timeout: 3000 })).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === "/api/v1/medicine-suggestions")?.search.get("q")).toBe("Sy");
    fireEvent.keyDown(medicine, { key: "ArrowDown" });
    fireEvent.keyDown(medicine, { key: "Enter" });

    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent(
      "1. Syrup X · 5 ml · 1-0-1 · after food · 5 days · with instructions",
    );
    expect(medicine).toHaveValue("");
    fireEvent.blur(screen.getByLabelText(/^Diet/));
    await waitFor(() => expect(put(api)).toHaveLength(1));
    expect(put(api)[0]?.body).toMatchObject({
      items: [{ medicine_name: "Syrup X", favourite_id: favourite.id, preparation: [{ code: "DILUTE_IN_WATER", text: "10 ml" }] }],
    });
  });

  it("Repeat copies an earlier visit's medicines; Alt+↓ moves a line and Remove takes it out", async () => {
    mockApi({ ...screenRoutes(), ...draftRoutes() });
    await open();

    typeLine("Syrup X", {});
    fireEvent.keyDown(within(entry()).getByRole("combobox", { name: "Medicine" }), { key: "Enter" });
    fireEvent.click(screen.getByRole("button", { name: /^Repeat the medicines of/ }));
    const list = within(builder()).getByRole("list", { name: "Medicines" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringContaining("1. Syrup X"),
      expect.stringContaining("2. Tablet Sample · 1 · 1-0-1 · after food · 3 days"),
    ]);

    const more = within(list).getByRole("button", { name: "More for line 1, Syrup X" });
    more.focus();
    fireEvent.keyDown(more, { key: "ArrowDown", altKey: true });
    expect(within(list).getAllByRole("listitem")[1]).toHaveTextContent("2. Syrup X");
    await waitFor(() => expect(within(list).getByRole("button", { name: "More for line 2, Syrup X" })).toHaveFocus());

    fireEvent.click(within(list).getByRole("button", { name: "Remove line 1, Tablet Sample" }));
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("More opens every field of a line, with the dilution amount required", async () => {
    mockApi({ ...screenRoutes(), ...draftRoutes() });
    await open();
    typeLine("Syrup X", { dose: "5 ml" });
    fireEvent.keyDown(within(entry()).getByLabelText("Dose"), { key: "Enter" });

    fireEvent.click(screen.getByRole("button", { name: "More for line 1, Syrup X" }));
    const drawer = screen.getByRole("dialog", { name: "Line 1: Syrup X" });
    fireEvent.change(within(drawer).getByLabelText("Form (e.g. syrup)"), { target: { value: "Syrup" } });
    fireEvent.click(within(drawer).getByLabelText("Mix in water"));
    fireEvent.click(within(drawer).getByRole("button", { name: "Done" }));
    expect(within(drawer).getByText("Required")).toBeInTheDocument();
    fireEvent.change(within(drawer).getByLabelText("Amount of water, e.g. 10 ml"), { target: { value: "10 ml" } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Done" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent("with instructions");
  });

  it("decision 2A: notes save on leaving the field with the revision; VIS_STALE stops saving and offers Reload", async () => {
    const api = mockApi({
      ...screenRoutes(),
      [`PATCH ${VISIT}`]: [() => json(200, visit({ revision: 2 })), () => apiError(409, "VIS_STALE", "This visit was changed elsewhere", {}, { revision: 5 })],
    });
    await open();

    const complaint = screen.getByLabelText("Chief complaint");
    fireEvent.change(complaint, { target: { value: "Fever for 2 days" } });
    fireEvent.change(screen.getByLabelText("Temperature (°C)"), { target: { value: "38.5" } });
    fireEvent.blur(complaint);
    await waitFor(() => expect(api.count(`PATCH ${VISIT}`)).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      revision: 1,
      chief_complaint: "Fever for 2 days",
      findings: null,
      diagnosis: null,
      notes: null,
      vitals: { temp_c: 38.5 },
    });

    fireEvent.change(complaint, { target: { value: "Fever for 3 days" } });
    fireEvent.blur(complaint);
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(/Changed in another tab/);
    expect(api.calls.filter((c) => c.method === "PATCH")[1]?.body).toMatchObject({ revision: 2 });
    expect(screen.getByLabelText("Chief complaint")).toBeDisabled();

    fireEvent.click(within(banner).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(api.count(`GET ${VISIT}`)).toBe(2));
  });

  it("a vital out of range is flagged and the vitals are left out of the save", async () => {
    const api = mockApi({ ...screenRoutes(), [`PATCH ${VISIT}`]: () => json(200, visit({ revision: 2 })) });
    await open();

    const pulse = screen.getByLabelText("Pulse (/min)");
    fireEvent.change(pulse, { target: { value: "720" } });
    fireEvent.blur(pulse);
    expect(pulse).toHaveAttribute("aria-invalid", "true");
    expect(pulse).toHaveAccessibleDescription(/A whole number from 20 to 250/);
    await waitFor(() => expect(api.count(`PATCH ${VISIT}`)).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).not.toHaveProperty("vitals");
  });

  it("RX_STALE: a draft changed in another tab stops saving and offers Reload, which shows the other tab's draft", async () => {
    const theirs = rx({ items: [syrupLine, { ...syrupLine, id: "0192f0a0-0000-7000-8000-0000000005c2", medicine_name: "Tablet Two" }], revision: 4 });
    const api = mockApi({
      ...screenRoutes(),
      [`GET ${VISIT}`]: [
        () => json(200, consultation({ prescriptions: [rx({ items: [syrupLine], revision: 3 })] })),
        () => json(200, consultation({ prescriptions: [theirs] })),
      ],
      [`PUT ${RX}`]: () => apiError(409, "RX_STALE", "This prescription was changed elsewhere", {}, { revision: 4 }),
    });
    await open();

    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent("Syrup X");
    fireEvent.click(screen.getByRole("button", { name: "Follow-up in 7 days" }));
    fireEvent.blur(screen.getByLabelText("Follow-up"));
    const banner = await within(builder()).findByRole("alert");
    expect(banner).toHaveTextContent(/Changed in another tab/);
    expect(put(api)[0]?.body).toMatchObject({ revision: 3 });
    expect(within(builder()).getByRole("button", { name: "Review and issue" })).toBeDisabled();

    fireEvent.click(within(banner).getByRole("button", { name: "Reload" }));
    await waitFor(() => expect(api.count(`GET ${VISIT}`)).toBe(2));
    expect(await within(builder()).findByText(/Tablet Two/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(within(builder()).queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Follow-up")).toHaveValue("");
  });

  it("journey 4: Review shows the patient's page in their language, then Hindi; Issue shows Print, the QR link and Revise", async () => {
    const issued = rx({ items: [syrupLine], status: "ISSUED", revision: 2, issued_at: "2026-10-18T05:00:00+00:00", language: "en" });
    let current = consultation({ prescriptions: [rx({ items: [syrupLine], revision: 2 })] });
    const api = mockApi({
      ...screenRoutes(),
      [`GET ${VISIT}`]: () => json(200, current),
      [`GET ${RX}/preview`]: (call) => json(200, page(call.search.get("lang") === "hi" ? "hi" : "en")),
      [`POST ${RX}/issue`]: () => {
        current = consultation({ prescriptions: [issued] });
        return json(200, issued);
      },
      [`GET ${RX}/link`]: () =>
        json(200, {
          id: "0192f0a0-0000-7000-8000-0000000004c1",
          url: "https://sample.example/p/sample-token",
          expires_at: "2027-01-16T05:00:00+00:00",
          locked: false,
          open_count: 0,
          last_opened_at: null,
        }),
    });
    await open();

    fireEvent.click(within(builder()).getByRole("button", { name: "Review and issue" }));
    const review = screen.getByRole("dialog", { name: "Review and issue" });
    const preview = await within(review).findByRole("region", { name: "What the patient will see" });
    expect(within(preview).getByText("How to give")).toBeInTheDocument();
    expect(within(preview).getByText("Mix in 10 ml of water")).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === `${RX}/preview`)?.search.get("lang")).toBe("en");

    fireEvent.click(within(review).getByRole("button", { name: "हिन्दी (Hindi)" }));
    expect(await within(review).findByText("कैसे दें")).toBeInTheDocument();
    expect(within(review).getByRole("region", { name: "What the patient will see" })).toHaveAttribute("lang", "hi");

    fireEvent.click(within(review).getByRole("button", { name: "Issue" }));
    expect(await screen.findByRole("heading", { name: "Prescription issued" })).toBeInTheDocument();
    expect(api.calls.find((c) => c.path === `${RX}/issue`)?.body).toEqual({ revision: 2 });
    expect(screen.getByRole("button", { name: "Print the prescription" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revise" })).toBeInTheDocument();
    expect(await screen.findByTestId("patient-link")).toHaveTextContent("https://sample.example/p/sample-token");
  });

  it("AC4: RX_DOCTOR_INCOMPLETE names the missing fields of the doctor's profile", async () => {
    mockApi({
      ...screenRoutes(consultation({ prescriptions: [rx({ items: [syrupLine] })] })),
      [`GET ${RX}/preview`]: () => json(200, page()),
      [`POST ${RX}/issue`]: () =>
        apiError(422, "RX_DOCTOR_INCOMPLETE", "The doctor's profile is missing registration details", {}, {
          fields: "registration_number,registration_council",
        }),
    });
    await open();

    fireEvent.click(within(builder()).getByRole("button", { name: "Review and issue" }));
    const review = screen.getByRole("dialog", { name: "Review and issue" });
    await within(review).findByRole("region", { name: "What the patient will see" });
    fireEvent.click(within(review).getByRole("button", { name: "Issue" }));
    expect(await within(review).findByRole("alert")).toHaveTextContent(
      "The doctor's profile is missing: registration number, registration council.",
    );
  });

  it("Revise starts a new version and the builder opens on it", async () => {
    const issued = rx({ items: [syrupLine], status: "ISSUED", issued_at: "2026-10-18T05:00:00+00:00" });
    const revision = rx({ id: "0192f0a0-0000-7000-8000-0000000003b2", version: 2, items: [syrupLine] });
    let current = consultation({ prescriptions: [issued] });
    mockApi({
      ...screenRoutes(),
      [`GET ${VISIT}`]: () => json(200, current),
      [`GET ${RX}/link`]: () => apiError(404, "REQ_NOT_FOUND", "Not found"),
      [`POST ${RX}/revise`]: () => {
        current = consultation({ prescriptions: [issued, revision] });
        return json(201, revision);
      },
    });
    await open();

    fireEvent.click(await screen.findByRole("button", { name: "Revise" }));
    expect(await screen.findByRole("heading", { name: "Prescription · version 2 (revision)" })).toBeInTheDocument();
    expect(within(builder()).getByRole("list", { name: "Medicines" })).toHaveTextContent("Syrup X");
  });

  it("journey 5: Complete asks when the prescription is written but not issued, then returns to the queue", async () => {
    const api = mockApi({
      ...screenRoutes(consultation({ prescriptions: [rx({ items: [syrupLine] })] })),
      [`POST ${VISIT}/complete`]: () => json(200, visit({ status: "COMPLETED" })),
    });
    await open();

    fireEvent.click(screen.getByRole("button", { name: "Complete visit" }));
    const ask = screen.getByRole("dialog", { name: "Complete without issuing?" });
    fireEvent.click(within(ask).getByRole("button", { name: "Go back" }));
    expect(api.count(`POST ${VISIT}/complete`)).toBe(0);

    fireEvent.click(screen.getByRole("button", { name: "Complete visit" }));
    fireEvent.click(screen.getByRole("button", { name: "Complete anyway" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/queue"));
  });

  it("FR-VIS-05: a locked visit is read only and offers only an addendum", async () => {
    const locked = visit({
      status: "COMPLETED",
      chief_complaint: "Fever",
      completed_at: "2026-10-16T05:00:00+00:00",
      locked_at: "2026-10-17T05:00:00+00:00",
      is_locked: true,
    });
    const api = mockApi({
      ...screenRoutes(consultation({ visit: locked })),
      [`POST ${VISIT}/addenda`]: () =>
        json(201, { id: "a1", visit_id: VISIT_ID, author_user_id: "u-1", body: "Lab result normal", created_at: "2026-10-18T06:00:00+00:00" }),
    });
    await open();

    expect(screen.getByText("Completed · locked")).toBeInTheDocument();
    expect(screen.queryByLabelText("Chief complaint")).not.toBeInTheDocument();
    expect(screen.getByText("Fever")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "New medicine" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete visit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Repeat/ })).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("New addendum"), { target: { value: "Lab result normal" } });
    fireEvent.click(screen.getByRole("button", { name: "Add addendum" }));
    await waitFor(() => expect(api.calls.find((c) => c.path === `${VISIT}/addenda`)?.body).toEqual({ body: "Lab result normal" }));
  });

  it("spec §2: another doctor's visit reads, and nothing can be changed", async () => {
    mockApi({
      ...screenRoutes(),
      "GET /api/v1/me": () => json(200, person([doctorMember])),
      "GET /api/v1/clinic/doctors": () => json(200, { items: [doctor({ user_id: "someone-else" })] }),
    });
    await open();

    expect(screen.getByText(/another doctor's visit/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Chief complaint")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "New medicine" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete visit" })).not.toBeInTheDocument();
  });

  it("an unknown or other clinic's visit reads 'Visit not found'", async () => {
    mockApi({ ...screenRoutes(), [`GET ${VISIT}`]: () => apiError(404, "REQ_NOT_FOUND", "Not found") });
    expect(await open()).toHaveTextContent("Visit not found");
  });

  it("autosave waits for typing to stop: several changes are one save", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = mockApi({ ...screenRoutes(), [`PATCH ${VISIT}`]: () => json(200, visit({ revision: 2 })) });
    await open();

    const findings = screen.getByLabelText("Findings");
    for (const text of ["T", "Th", "Thr", "Throat red"]) {
      fireEvent.change(findings, { target: { value: text } });
      await act(async () => {
        await vi.advanceTimersByTimeAsync(300);
      });
    }
    expect(api.count(`PATCH ${VISIT}`)).toBe(0);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1100);
    });
    await waitFor(() => expect(api.count(`PATCH ${VISIT}`)).toBe(1));
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toMatchObject({ findings: "Throat red" });
  });
});
