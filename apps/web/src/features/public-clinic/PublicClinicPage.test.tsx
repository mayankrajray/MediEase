import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { json, mockApi } from "@/test/api";

import { PublicClinicPage, requestHref } from "./PublicClinicPage";

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";

const CLINIC = {
  name: "Sample Clinic",
  slug: "sample-clinic",
  address_line: "12 MG Road",
  city: "Pune",
  state: "MH",
  pincode: "411001",
  phone_e164: "+919000000010",
  timezone: "Asia/Kolkata",
  booking_mode: "SLOTS",
  map_url: "https://maps.example.test/?q=12+MG+Road",
  requires_age_sex: false,
  doctors: [
    {
      id: DOCTOR,
      display_name: "Dr. Mehta",
      qualification: "MBBS",
      specialty: "General medicine",
      hours: [
        { weekday: 0, start: "10:00", end: "13:00" },
        { weekday: 2, start: "10:00", end: "13:00" },
      ],
    },
  ],
} as const;

const SESSION = {
  starts_at: "2026-11-02T04:30:00Z",
  ends_at: "2026-11-02T07:30:00Z",
  mode: "SLOTS",
  places_left: 3,
  slots: [
    { starts_at: "2026-11-02T04:30:00Z", ends_at: "2026-11-02T05:30:00Z" },
    { starts_at: "2026-11-02T05:30:00Z", ends_at: "2026-11-02T06:30:00Z" },
  ],
} as const;

beforeEach(() => {
  mockApi({ "GET /api/v1/public/clinics/sample-clinic/availability": () => json(200, { days: [{ date: "2026-11-02", sessions: [SESSION] }] }) });
});

describe("the public clinic page (M6b-P4, FR-PUB-01, 04)", () => {
  it("shows the clinic, an emergency notice, the doctor and their hours", () => {
    render(<PublicClinicPage clinic={CLINIC} language="en" />);
    expect(screen.getByRole("heading", { level: 1, name: "Sample Clinic" })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/not for emergencies/);
    expect(screen.getByText(/12 MG Road, Pune, MH, 411001/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", "tel:+919000000010");
    expect(screen.getByRole("link", { name: "Directions" })).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText(/Mon 10:00–13:00 · Wed 10:00–13:00/)).toBeInTheDocument();
  });

  it("R7: a chosen doctor's times link to the request form with the exact slot", async () => {
    render(<PublicClinicPage clinic={CLINIC} language="en" />);
    fireEvent.click(screen.getByRole("button", { name: "See times" }));
    const day = await screen.findByRole("heading", { level: 3 });
    expect(day).toHaveTextContent(/Mon, 2 Nov/);
    const link = screen.getByRole("link", { name: /Ask for 11:00 am/ });
    expect(link).toHaveAttribute("href", requestHref("sample-clinic", DOCTOR, SESSION, "2026-11-02T05:30:00Z", "en"));
    expect(link.getAttribute("href")).toContain("slot=2026-11-02T05%3A30%3A00Z");
  });

  it("R10: the Hindi page uses Hindi words and the link keeps the language", async () => {
    render(<PublicClinicPage clinic={CLINIC} language="hi" />);
    expect(screen.getByRole("link", { name: /View in English/ })).toHaveAttribute("href", "/c/sample-clinic?lang=en");
    fireEvent.click(screen.getByRole("button", { name: "समय देखें" }));
    const links = await screen.findAllByRole("link", { name: /माँगें/ });
    expect(links[0]?.getAttribute("href")).toContain("lang=hi");
  });

  it("a token session shows the places left and one link", async () => {
    mockApi({
      "GET /api/v1/public/clinics/sample-clinic/availability": () =>
        json(200, { days: [{ date: "2026-11-02", sessions: [{ ...SESSION, mode: "TOKENS", slots: [] }] }] }),
    });
    render(<PublicClinicPage clinic={{ ...CLINIC, booking_mode: "TOKENS" }} language="en" />);
    fireEvent.click(screen.getByRole("button", { name: "See times" }));
    const link = await screen.findByRole("link", { name: "Ask for this session" });
    expect(within(link.closest("div") as HTMLElement).getByText(/3 places left/)).toBeInTheDocument();
  });

  it("says plainly when nothing is free", async () => {
    mockApi({ "GET /api/v1/public/clinics/sample-clinic/availability": () => json(200, { days: [] }) });
    render(<PublicClinicPage clinic={CLINIC} language="en" />);
    fireEvent.click(screen.getByRole("button", { name: "See times" }));
    expect(await screen.findByText(/No free times in the next 14 days/)).toBeInTheDocument();
  });
});
