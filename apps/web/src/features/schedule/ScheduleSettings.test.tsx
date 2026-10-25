import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CLINIC_A, membership, person } from "@/features/auth/testing";
import { renderInWorkspace } from "@/features/patients/testing";
import { boardRoutes, doctor, session } from "@/features/queue/testing";
import { ApiError } from "@/lib/api/client";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { ScheduleSettings, blockProblem, blocksOf } from "./ScheduleSettings";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const owner = membership(CLINIC_A, "Alpha Clinic", "OWNER", {
  permissions: ["CLINIC_VIEW", "DOCTORS_VIEW", "CLINIC_MANAGE", "SCHEDULES_MANAGE", "APPOINTMENTS_MANAGE"],
});
const URL = `/api/v1/clinic/doctors/${doctor().id}/schedule`;
const schedule = {
  doctor_id: doctor().id,
  booking_mode: "TOKENS",
  blocks: [{ id: "b1", weekday: 0, start_time: "10:00", end_time: "13:00", overnight: false, slot_minutes: 15, capacity: 12 }],
  exceptions: [
    { id: "e1", doctor_id: doctor().id, on_date: "2026-10-26", kind: "LEAVE", note: "conference", start_time: null, end_time: null, overnight: false, slot_minutes: null, capacity: null },
  ],
};
const routes = {
  ...boardRoutes,
  "GET /api/v1/me": () => json(200, person([owner])),
  [`GET ${URL}`]: () => json(200, schedule),
};

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("schedule settings (D31, FR-APT-01)", () => {
  it("R16: edits the week and saves it whole; booked sessions kept are listed", async () => {
    const api = mockApi({
      ...routes,
      [`PUT ${URL}`]: () => json(200, { ...schedule, kept_sessions: [session({ on_date: "2026-10-19", booked_count: 3 })] }),
    });
    renderInWorkspace(<ScheduleSettings />);
    const week = await screen.findByRole("region", { name: /Weekly hours for Dr Meera Iyer/ }, { timeout: 5000 });

    fireEvent.change(within(week).getAllByLabelText("To")[0] as HTMLElement, { target: { value: "14:00" } });
    fireEvent.click(within(week).getByRole("button", { name: "Add hours" }));
    fireEvent.change(within(week).getAllByLabelText("Day")[1] as HTMLElement, { target: { value: "5" } });
    fireEvent.click(within(week).getByRole("button", { name: "Save weekly hours" }));

    expect(await screen.findByText("Weekly hours for Dr Meera Iyer saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({
      blocks: [
        { weekday: 0, start_time: "10:00", end_time: "14:00", slot_minutes: 15, capacity: 12 },
        { weekday: 5, start_time: "10:00", end_time: "13:00", slot_minutes: 15, capacity: 12 },
      ],
    });
    expect(screen.getByText(/One session has bookings and was kept/)).toBeInTheDocument();
    expect(screen.getByText(/Mon, 19 Oct, .*: 3 booked/)).toBeInTheDocument();
  });

  it("R14, R15: names the block a schedule error is about", async () => {
    mockApi({
      ...routes,
      [`PUT ${URL}`]: () =>
        apiError(422, "SCH_INVALID_BLOCK", "This block cannot be scheduled.", {}, { index: "0", reason: "a block lasts at most 12 hours" }),
    });
    renderInWorkspace(<ScheduleSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Save weekly hours" }, { timeout: 5000 }));

    expect(await screen.findByText("Check block 1 (Monday 10:00–13:00): a block lasts at most 12 hours.")).toBeInTheDocument();
  });

  it("R17: adds leave and removes an exception", async () => {
    const api = mockApi({
      ...routes,
      [`POST /api/v1/clinic/doctors/${doctor().id}/schedule-exceptions`]: () => json(201, { exception: schedule.exceptions[0], kept_sessions: [] }),
      [`DELETE /api/v1/clinic/doctors/${doctor().id}/schedule-exceptions/e1`]: () => json(200, { exception: schedule.exceptions[0], kept_sessions: [] }),
    });
    renderInWorkspace(<ScheduleSettings />);
    const section = await screen.findByRole("region", { name: "Leave and extra sessions" }, { timeout: 5000 });
    expect(section).toHaveTextContent(/Mon, 26 Oct: on leave all day · conference/);

    fireEvent.change(within(section).getByLabelText("On"), { target: { value: "2026-10-27" } });
    fireEvent.click(within(section).getByRole("button", { name: "Add leave" }));
    await screen.findByText(/Leave on Tue, 27 Oct added/);
    expect(api.calls.find((c) => c.method === "POST")?.body).toEqual({ kind: "LEAVE", on_date: "2026-10-27" });

    fireEvent.click(within(section).getByRole("button", { name: "Remove the leave on Mon, 26 Oct" }));
    await waitFor(() => expect(api.count(`DELETE /api/v1/clinic/doctors/${doctor().id}/schedule-exceptions/e1`)).toBe(1));
  });

  it("R19: switches the booking mode, and shows a refusal", async () => {
    mockApi({
      ...routes,
      "PATCH /api/v1/clinic": () => apiError(409, "SCH_MODE_INCOMPATIBLE", "Every current block needs a slot length for SLOTS booking."),
    });
    renderInWorkspace(<ScheduleSettings />);
    fireEvent.click(await screen.findByRole("button", { name: "Switch to time slots" }, { timeout: 5000 }));

    expect(await screen.findByText("Every current block needs a slot length for SLOTS booking.")).toBeInTheDocument();
  });

  it("blocksOf leaves out empty values; blockProblem ignores other errors", () => {
    const draft = { key: "k", weekday: "6", start: "22:00", end: "02:00", slot: "", capacity: "5" };
    expect(blocksOf([draft])).toEqual([{ weekday: 6, start_time: "22:00", end_time: "02:00", capacity: 5 }]);
    const overlap = new ApiError("SCH_OVERLAP", "x", 409, "r", { first: "0", second: "0" });
    expect(blockProblem(overlap, [draft])).toBe("Block 1 (Sunday 22:00–02:00) overlaps block 1 (Sunday 22:00–02:00).");
    expect(blockProblem(new Error("x"), [draft])).toBeUndefined();
  });
});

describe("appointment reminders (M6a-P8, FR-APT-08, decision 3A)", () => {
  it("the owner turns the evening reminder off and moves the other to three hours before", async () => {
    const api = mockApi({
      ...routes,
      "PATCH /api/v1/clinic": () => json(200, {}),
    });
    renderInWorkspace(<ScheduleSettings />);
    const card = await screen.findByRole("region", { name: "Appointment reminders" }, { timeout: 5000 });
    const evening = within(card).getByRole("checkbox", { name: "The evening before, at 19:00" });
    expect(evening).toBeChecked();
    expect(within(card).getByLabelText("Before the visit")).toHaveValue("2");

    fireEvent.click(evening);
    fireEvent.change(within(card).getByLabelText("Before the visit"), { target: { value: "3" } });
    fireEvent.click(within(card).getByRole("button", { name: "Save reminders" }));

    expect(await screen.findByText("Appointment reminders saved: no evening reminder, 3 hours before.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({
      reminder_evening_before: false,
      reminder_hours_before: 3,
    });
  });

  it("is not offered to a member who cannot change clinic settings", async () => {
    const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["CLINIC_VIEW", "DOCTORS_VIEW"] });
    mockApi({ ...routes, "GET /api/v1/me": () => json(200, person([desk])) });
    renderInWorkspace(<ScheduleSettings />);
    await screen.findByRole("region", { name: /Weekly hours/ }, { timeout: 5000 });
    expect(screen.queryByRole("region", { name: "Appointment reminders" })).not.toBeInTheDocument();
  });
});

describe("online booking requests (M6b-P4, spec R20)", () => {
  it("shows the page address and saves the hold time and the age/sex choice", async () => {
    const api = mockApi({
      ...routes,
      "PATCH /api/v1/clinic": () => json(200, {}),
    });
    renderInWorkspace(<ScheduleSettings />);
    const card = await screen.findByRole("region", { name: "Online booking requests" }, { timeout: 5000 });
    expect((within(card).getByLabelText("Your clinic page") as HTMLInputElement).value).toMatch(/\/c\/[a-z0-9-]+$/);
    expect(within(card).getByLabelText("Keep a requested time for")).toHaveValue("120");

    fireEvent.change(within(card).getByLabelText("Keep a requested time for"), { target: { value: "60" } });
    fireEvent.click(within(card).getByLabelText("Ask patients for age and sex"));
    fireEvent.click(within(card).getByRole("button", { name: "Save online requests" }));

    expect(await screen.findByText("Online requests saved: a requested time is kept for 1 hour; age and sex are asked.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PATCH")?.body).toEqual({ request_hold_minutes: 60, request_requires_age_sex: true });
  });

  it("is not offered to a member who cannot change clinic settings", async () => {
    const desk = membership(CLINIC_A, "Alpha Clinic", "FRONT_DESK", { permissions: ["CLINIC_VIEW", "DOCTORS_VIEW"] });
    mockApi({ ...routes, "GET /api/v1/me": () => json(200, person([desk])) });
    renderInWorkspace(<ScheduleSettings />);
    await screen.findByRole("region", { name: /Weekly hours/ }, { timeout: 5000 });
    expect(screen.queryByRole("region", { name: "Online booking requests" })).not.toBeInTheDocument();
  });
});
