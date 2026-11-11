import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import type { Days } from "@/features/booking/availability";
import { apiError, json, mockApi, type Recorded } from "@/test/api";

import { PublicClinicPage } from "./PublicClinicPage";

const MEHTA = "0192f0a0-0000-7000-8000-0000000000d1";
const RAO = "0192f0a0-0000-7000-8000-0000000000d2";
const ROUTE = "GET /api/v1/public/clinics/sample-clinic/availability";
const TODAY = "2026-11-12";

const doctor = (id: string, name: string) => ({
  id,
  display_name: name,
  qualification: "MBBS",
  specialty: "General medicine",
  languages: ["Hindi", "English"],
  fee_paise: 30000,
  hours: [{ weekday: 3, start: "10:00", end: "13:00" }],
});

const CLINIC = {
  name: "Sample Clinic",
  slug: "sample-clinic",
  address_line: "12 MG Road",
  city: "Pune",
  state: "MH",
  pincode: "411001",
  phone_e164: "+919000000010",
  timezone: "Asia/Kolkata",
  booking_mode: "TOKENS",
  map_url: "https://maps.example.test/?q=12+MG+Road",
  requires_age_sex: false,
  specialties: ["General Medicine"],
  indexable: false,
  doctors: [doctor(MEHTA, "Dr. Mehta"), doctor(RAO, "Dr. Rao")],
} as const;

const tokens = (date: string, startUtc: string, places: number) => ({
  date,
  sessions: [{ starts_at: `${date}T${startUtc}:00Z`, ends_at: `${date}T${startUtc}:00Z`, mode: "TOKENS" as const, places_left: places, slots: [] }],
});
// Dr. Mehta: today 2 places, and Saturday. Dr. Rao: Saturday only.
const DAYS: Record<string, Days> = { [MEHTA]: [tokens(TODAY, "04:30", 2), tokens("2026-11-14", "04:30", 5)], [RAO]: [tokens("2026-11-14", "10:30", 8)] };
const byDoctor = (days: Record<string, Days>) => (call: Recorded) => json(200, { days: days[call.search.get("doctor_id") ?? ""] ?? [] });

function show(props: Partial<Parameters<typeof PublicClinicPage>[0]> = {}) {
  return render(<PublicClinicPage clinic={CLINIC} language="en" today={TODAY} {...props} />);
}

beforeEach(() => {
  window.history.replaceState(null, "", "/c/sample-clinic");
});

describe("the public clinic page (M6b-P4, FR-PUB-01, 04; M7d-P4)", () => {
  it("shows the clinic, an emergency notice and the ways to reach it", () => {
    mockApi({ [ROUTE]: byDoctor(DAYS) });
    show();
    expect(screen.getByRole("heading", { level: 1, name: "Sample Clinic" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/not for emergencies/);
    expect(screen.getByText(/12 MG Road, Pune, MH, 411001/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", "tel:+919000000010");
    expect(screen.getByRole("link", { name: "Directions" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByRole("list", { name: "Specialties" })).toHaveTextContent("General Medicine");
    // Decision 3: no filters.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("selects today and lists only the doctors free on it, with places left and the doctor's page on that date", async () => {
    mockApi({ [ROUTE]: byDoctor(DAYS) });
    show({ viaDirectory: true });
    expect(screen.getByRole("button", { name: /^Thu, 12 Nov/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("heading", { name: "Doctors available on Thu, 12 Nov" })).toBeInTheDocument();
    const card = (await screen.findByText("Dr. Mehta")).closest("li") as HTMLElement;
    expect(within(card).getByText("2 places left")).toHaveClass("bg-warning-soft");
    expect(within(card).getByText("From 10:00 am")).toBeInTheDocument();
    expect(within(card).getByRole("link", { name: /View profile and times/ })).toHaveAttribute("href", `/c/sample-clinic/doctors/${MEHTA}?date=2026-11-12&via=directory`);
    expect(screen.queryByText("Dr. Rao")).not.toBeInTheDocument();
    expect(screen.getByText("1 other doctor has no times on this date.")).toBeInTheDocument();
    // The tiles add up the doctors: Saturday has 13.
    expect(screen.getByRole("button", { name: "Sat, 14 Nov, 13 left" })).toBeInTheDocument();
  });

  it("another date shows that date's doctors and keeps the date in the address", async () => {
    mockApi({ [ROUTE]: byDoctor(DAYS) });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Sat, 14 Nov, 13 left" }));
    expect(await screen.findByText("Dr. Rao")).toBeInTheDocument();
    expect(screen.getByText("Dr. Mehta")).toBeInTheDocument();
    expect(window.location.search).toBe("?date=2026-11-14");
    expect(screen.getByRole("link", { name: /हिन्दी में देखें/ })).toHaveAttribute("href", "/c/sample-clinic?date=2026-11-14&lang=hi");
  });

  it("a date when nobody is free offers the next date when someone is", async () => {
    mockApi({ [ROUTE]: byDoctor(DAYS) });
    show({ initialDate: "2026-11-13" });
    expect(await screen.findByText("No doctor has available times on this date.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next available: Sat, 14 Nov" }));
    expect(await screen.findByText("Dr. Rao")).toBeInTheDocument();
  });

  it("says when nothing is free in the window", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: [] }) });
    show();
    expect(await screen.findByText("No available times in the next 14 days. Please call the clinic.")).toBeInTheDocument();
  });

  it("shows the doctors it could load when one fails, and offers Try again", async () => {
    let fail = true;
    mockApi({ [ROUTE]: (call) => (call.search.get("doctor_id") === RAO && fail ? apiError(503, "SYS_UNAVAILABLE", "x") : byDoctor(DAYS)(call)) });
    show({ initialDate: "2026-11-14" });
    expect(await screen.findByText("Dr. Mehta")).toBeInTheDocument();
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("We could not load the times of some doctors.");
    fail = false;
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Dr. Rao")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("an address date outside the window falls back to today; Hindi words on the Hindi page", async () => {
    mockApi({ [ROUTE]: byDoctor(DAYS) });
    show({ initialDate: "2026-12-30", language: "hi" });
    expect(screen.getByRole("link", { name: /View in English/ })).toHaveAttribute("href", "/c/sample-clinic?date=2026-11-12&lang=en");
    expect(await screen.findByRole("link", { name: /प्रोफ़ाइल और समय देखें/ })).toHaveAttribute("href", `/c/sample-clinic/doctors/${MEHTA}?date=2026-11-12&lang=hi`);
  });
});
