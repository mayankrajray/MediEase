import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { patient, PATIENT_ID, renderInWorkspace } from "@/features/patients/testing";
import { DOCTOR_ID } from "@/features/queue/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { FollowUpReminder } from "./FollowUpReminder";
import { PatientMessages } from "./PatientMessages";
import { PatientReminders } from "./PatientReminders";
import { CHAIN_ID, REMINDER_ID, message, reminder, reminderRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const LIST = `GET /api/v1/patients/${PATIENT_ID}/reminders`;
const MESSAGES = `GET /api/v1/patients/${PATIENT_ID}/messages`;

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

const region = (name: string) => screen.findByRole("region", { name }, { timeout: 5000 });

describe("reminders on the profile (M5-P6 decision 3A; FR-REM-02, 05)", () => {
  it("R16: each reminder shows its status chip with the due time in the clinic's zone, the date, doctor and source", async () => {
    mockApi({ ...reminderRoutes, [LIST]: () => json(200, { items: [reminder()] }) });
    renderInWorkspace(<PatientReminders patient={patient()} />);

    const section = await region("Reminders");
    expect(await within(section).findByText("Follow-up reminder · Mon, 19 Oct, 09:00 · Scheduled")).toBeInTheDocument();
    expect(section).toHaveTextContent("Follow-up on Tue, 20 Oct with Dr Meera Iyer · From a prescription");
    expect(within(section).queryByRole("link", { name: /Call patient/ })).not.toBeInTheDocument();
  });

  it("spec §6: a failed reminder says why in words and offers a call, with no code on screen", async () => {
    mockApi({
      ...reminderRoutes,
      [LIST]: () => json(200, { items: [reminder({ status: "FAILED", error_code: "MSG_RECIPIENT_INVALID" })] }),
    });
    renderInWorkspace(<PatientReminders patient={patient()} />);

    const section = await region("Reminders");
    expect(await within(section).findByText("This number can't receive WhatsApp.")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: /Call patient/ })).toHaveAttribute("href", "tel:+919000000102");
    expect(section).not.toHaveTextContent("MSG_");
    expect(within(section).queryByRole("button", { name: "Move" })).not.toBeInTheDocument();
  });

  it("FR-REM-02: staff add a reminder with a doctor and a date, and it is listed", async () => {
    let listed = [] as ReturnType<typeof reminder>[];
    const api = mockApi({
      ...reminderRoutes,
      [LIST]: () => json(200, { items: listed }),
      [`POST /api/v1/patients/${PATIENT_ID}/reminders`]: (call) => {
        listed = [reminder({ source: "MANUAL", prescription_id: null, follow_up_date: (call.body as { follow_up_date: string }).follow_up_date })];
        return json(201, listed[0]);
      },
    });
    renderInWorkspace(<PatientReminders patient={patient()} />);

    const section = await region("Reminders");
    fireEvent.click(await within(section).findByRole("button", { name: "Add follow-up reminder" }));
    const form = within(section).getByRole("form", { name: "Add follow-up reminder" });
    fireEvent.change(within(form).getByLabelText("Follow-up date"), { target: { value: "2099-01-15" } });
    fireEvent.click(within(form).getByRole("button", { name: "Add reminder" }));

    expect(await within(section).findByText("Reminder added for the follow-up on Thu, 15 Jan.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ doctor_id: DOCTOR_ID, follow_up_date: "2099-01-15" });
    expect(await within(section).findByText(/Added by staff/)).toBeInTheDocument();
  });

  it("a scheduled reminder can be moved and cancelled; a refusal shows the API's words and the list reloads", async () => {
    const api = mockApi({
      ...reminderRoutes,
      [LIST]: () => json(200, { items: [reminder()] }),
      [`PATCH /api/v1/reminders/${REMINDER_ID}`]: (call) =>
        (call.body as { cancel: boolean }).cancel
          ? apiError(409, "REM_NOT_SCHEDULED", "This reminder was already sent, cancelled or skipped.")
          : json(200, reminder({ follow_up_date: "2099-02-01", revision: 2 })),
    });
    renderInWorkspace(<PatientReminders patient={patient()} />);
    const section = await region("Reminders");

    fireEvent.click(await within(section).findByRole("button", { name: "Move" }));
    fireEvent.change(within(section).getByLabelText("New follow-up date"), { target: { value: "2099-02-01" } });
    fireEvent.click(within(section).getByRole("button", { name: "Save" }));
    expect(await within(section).findByText("Reminder moved to the follow-up on Sun, 1 Feb.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ follow_up_date: "2099-02-01", cancel: false });

    fireEvent.click(await within(section).findByRole("button", { name: "Cancel reminder" }));
    expect(await within(section).findByText("This reminder was already sent, cancelled or skipped.")).toBeInTheDocument();
    await waitFor(() => expect(api.count(LIST)).toBe(3));
  });

  it("a failed load shows the Ref and Try again", async () => {
    mockApi({ ...reminderRoutes, [LIST]: () => apiError(500, "SYS_INTERNAL", "Something went wrong.") });
    renderInWorkspace(<PatientReminders patient={patient()} />);

    const section = await region("Reminders");
    expect(await within(section).findByRole("alert")).toHaveTextContent("Ref: test-ref");
  });
});

describe("message history (M5-P6 decision 1A; R16)", () => {
  it("lists what was sent, on which channel, its status and when; a failure says why and offers a call", async () => {
    mockApi({
      ...reminderRoutes,
      [MESSAGES]: () =>
        json(200, {
          items: [
            message({
              id: "0192f0a0-0000-7000-8000-0000000007a2",
              template_key: "follow_up_due",
              source_type: "REMINDER",
              status: "FAILED",
              error_code: "MSG_OUTCOME_UNKNOWN",
              delivered_at: null,
              failed_at: "2026-10-19T03:30:10+00:00",
            }),
            message(),
          ],
        }),
    });
    renderInWorkspace(<PatientMessages patient={patient()} />);

    const section = await region("Message history");
    const failed = await within(section).findByRole("row", { name: /Follow-up reminder/ });
    expect(failed).toHaveTextContent("Not delivered");
    expect(failed).toHaveTextContent("We can't tell whether it arrived, so it was not sent again.");
    expect(failed).toHaveTextContent("19 Oct 2026, 09:00");
    const ok = within(section).getByRole("row", { name: /Appointment confirmation/ });
    expect(ok).toHaveTextContent("WhatsApp");
    expect(ok).toHaveTextContent("Delivered");
    expect(within(section).getByRole("link", { name: /Call patient/ })).toHaveAttribute("href", "tel:+919000000102");
    expect(section).not.toHaveTextContent("MSG_");
  });

  it("says so when nothing was sent", async () => {
    mockApi(reminderRoutes);
    renderInWorkspace(<PatientMessages patient={patient()} />);
    expect(await within(await region("Message history")).findByText("No messages sent yet.")).toBeInTheDocument();
  });
});

describe("the reminder on the consultation (M5-P6 decision 2A)", () => {
  it("shows the chain's latest reminder, not another chain's", async () => {
    mockApi({
      ...reminderRoutes,
      [LIST]: () =>
        json(200, {
          items: [
            reminder({ id: "r-other", prescription_id: "0192f0a0-0000-7000-8000-0000000003c9", status: "FAILED" }),
            reminder({ id: "r-old", status: "CANCELLED", created_at: "2026-10-01T05:00:00+00:00" }),
            reminder({ status: "SENT" }),
          ],
        }),
    });
    renderInWorkspace(<FollowUpReminder patientId={PATIENT_ID} chainId={CHAIN_ID} />);

    expect(await screen.findByText("Follow-up reminder · Mon, 19 Oct, 09:00 · Sent", {}, { timeout: 5000 })).toBeInTheDocument();
    expect(screen.queryByText(/Cancelled|Failed/)).not.toBeInTheDocument();
  });
});
