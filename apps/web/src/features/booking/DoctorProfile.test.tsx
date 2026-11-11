import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { json, mockApi } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import type { Days } from "./availability";
import { DoctorProfile } from "./DoctorProfile";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const ROUTE = "GET /api/v1/public/clinics/sample-clinic/availability";
const TODAY = "2026-11-12";

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
  map_url: null,
  requires_age_sex: false,
  specialties: ["General Medicine"],
  indexable: false,
  doctors: [
    {
      id: DOCTOR,
      display_name: "Dr. Mehta",
      qualification: "MBBS, MD",
      specialty: "General Medicine",
      languages: ["Hindi", "English"],
      fee_paise: 50000,
      hours: [
        { weekday: 0, start: "09:00", end: "13:00" },
        { weekday: 2, start: "09:00", end: "13:00" },
        { weekday: 4, start: "16:00", end: "20:00" },
      ],
    },
  ],
} as const;
const DOC = CLINIC.doctors[0];

const SLOTS = ["03:30", "04:00"].map((t) => ({ starts_at: `2026-11-12T${t}:00Z`, ends_at: `2026-11-12T${t}:00Z` }));
const DAYS: Days = [
  { date: TODAY, sessions: [{ starts_at: "2026-11-12T03:30:00Z", ends_at: "2026-11-12T05:30:00Z", mode: "SLOTS", places_left: 2, slots: SLOTS }] },
  { date: "2026-11-14", sessions: [{ starts_at: "2026-11-14T03:30:00Z", ends_at: "2026-11-14T07:30:00Z", mode: "TOKENS", places_left: 9, slots: [] }] },
];

function show(props: Partial<Parameters<typeof DoctorProfile>[0]> = {}) {
  return render(<DoctorProfile clinic={CLINIC} doctor={DOC} language="en" viaDirectory={false} today={TODAY} initialDate={TODAY} initialChoice={null} {...props} />);
}

beforeEach(() => {
  resetNavigation();
  window.history.replaceState(null, "", "/c/sample-clinic/doctors/x");
});

describe("a doctor's page (M7d-P3, design §7)", () => {
  it("shows only real facts: fee, next available, languages, qualification, and a short About", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    // jsdom lays nothing out: the About paragraph is made taller than its three clamped lines.
    const tall = vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(120);
    const clamp = vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(72);
    show();
    tall.mockRestore();
    clamp.mockRestore();
    expect(screen.getByRole("heading", { level: 1, name: "Dr. Mehta" })).toBeInTheDocument();
    expect(screen.getByText("General Medicine · MBBS, MD")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All doctors at Sample Clinic" })).toHaveAttribute("href", "/c/sample-clinic?date=2026-11-12");
    expect(screen.getByRole("note")).toHaveTextContent(/not for emergencies/);
    const facts = screen.getByText("Consultation fee").closest("dl") as HTMLElement;
    expect(within(facts).getByText("₹500")).toBeInTheDocument();
    expect(within(facts).getByText("Hindi, English")).toBeInTheDocument();
    expect(await within(facts).findByText("Thu, 12 Nov")).toBeInTheDocument();
    // No invented ratings, reviews or patient counts.
    expect(document.body).not.toHaveTextContent(/rating|review|patients treated|years/i);
    // About: built from the published facts; cut at three lines, so Read more.
    const more = screen.getByRole("button", { name: "Read more" });
    expect(screen.getByText(/Dr\. Mehta sees patients at Sample Clinic, Pune\. Specialty: General Medicine\./)).toHaveClass("line-clamp-3");
    fireEvent.click(more);
    expect(screen.getByRole("button", { name: "Read less" })).toHaveAttribute("aria-expanded", "true");
  });

  it("keeps Request this time disabled until a time is chosen, then checks it and goes to the form", async () => {
    const api = mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    show({ viaDirectory: true });
    const request = screen.getByRole("button", { name: "Request this time" });
    expect(request).toBeDisabled();
    expect(screen.getByText("Choose a date and a time to continue.")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "9:30 am" }));
    await waitFor(() => expect(request).toBeEnabled());
    expect(screen.getByText("Thu, 12 Nov, 9:30 am")).toBeInTheDocument();
    expect(screen.getByText(/₹500, pay at the clinic/)).toBeInTheDocument();
    // The address holds the choice, so Back and reload return to it.
    expect(window.location.search).toBe("?date=2026-11-12&session=2026-11-12T03%3A30%3A00Z&slot=2026-11-12T04%3A00%3A00Z&via=directory");
    const before = api.count(ROUTE);
    fireEvent.click(request);
    fireEvent.click(request); // a second tap does nothing more
    await waitFor(() => expect(push).toHaveBeenCalledTimes(1));
    expect(api.count(ROUTE)).toBe(before + 1);
    expect(push).toHaveBeenCalledWith(
      "/portal/request?clinic=sample-clinic&doctor=0192f0a0-0000-7000-8000-0000000000d1&session=2026-11-12T03%3A30%3A00Z&slot=2026-11-12T04%3A00%3A00Z&via=directory",
    );
  });

  it("stays on the page when the time was taken meanwhile, and says so", async () => {
    const taken: Days = [{ ...DAYS[0]!, sessions: [{ ...DAYS[0]!.sessions[0]!, places_left: 1, slots: SLOTS.slice(0, 1) }] }, DAYS[1]!];
    let calls = 0;
    mockApi({ [ROUTE]: () => json(200, { days: (calls += 1) <= 1 ? DAYS : taken }) });
    show({ initialChoice: { session: "2026-11-12T03:30:00Z", slot: "2026-11-12T04:00:00Z" } });
    const request = screen.getByRole("button", { name: "Request this time" });
    await waitFor(() => expect(request).toBeEnabled());
    fireEvent.click(request);
    expect(await screen.findByText("The time you chose is no longer available. Please choose another.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(request).toBeDisabled();
  });

  it("says when the last check failed, keeping the choice", async () => {
    let calls = 0;
    mockApi({
      [ROUTE]: () => ((calls += 1) <= 1 ? json(200, { days: DAYS }) : json(503, { error: { code: "SYS_UNAVAILABLE", message: "x", request_id: "r", details: {} } })),
    });
    show({ initialChoice: { session: "2026-11-12T03:30:00Z", slot: "2026-11-12T03:30:00Z" } });
    const request = screen.getByRole("button", { name: "Request this time" });
    await waitFor(() => expect(request).toBeEnabled());
    fireEvent.click(request);
    expect(await screen.findByText("We could not check this time. Please try again.")).toBeInTheDocument();
    expect(push).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "9:00 am" })).toHaveAttribute("aria-pressed", "true");
  });

  it("offers no Read more when the About fits", () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    show();
    expect(screen.queryByRole("button", { name: "Read more" })).not.toBeInTheDocument();
  });

  it("opens on the date and time from the address, and the language switch keeps them", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    show({ initialDate: "2026-11-14", initialChoice: { session: "2026-11-14T03:30:00Z", slot: null } });
    expect(await screen.findByRole("button", { name: "Choose 9:00 am–1:00 pm" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("link", { name: /हिन्दी में देखें/ })).toHaveAttribute(
      "href",
      `/c/sample-clinic/doctors/${DOCTOR}?date=2026-11-14&session=2026-11-14T03%3A30%3A00Z&lang=hi`,
    );
  });

  it("speaks Hindi on the Hindi page", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    show({ language: "hi" });
    expect(screen.getByRole("button", { name: "यह समय माँगें" })).toBeDisabled();
    expect(screen.getByText("परामर्श शुल्क")).toBeInTheDocument();
    expect(await screen.findByRole("group", { name: "सुबह" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /View in English/ }).getAttribute("href")).toContain("lang=en");
  });
});
