import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { flush, json, mockApi } from "@/test/api";

import { AppointmentPicker } from "./AppointmentPicker";
import type { Choice, Days } from "./availability";
import { useAvailability } from "./useAvailability";

const DOCTOR = "0192f0a0-0000-7000-8000-0000000000d1";
const ROUTE = "GET /api/v1/public/clinics/sample-clinic/availability";
const TODAY = "2026-11-12"; // Thursday

// Today: four morning slots (09:00-10:30), an afternoon token session with 12 places and an
// evening one with 2. Tomorrow: nothing (left out). Saturday: one token session.
const SLOTS = ["03:30", "04:00", "04:30", "05:00"].map((t) => ({ starts_at: `2026-11-12T${t}:00Z`, ends_at: `2026-11-12T${t}:00Z` }));
const DAYS: Days = [
  {
    date: TODAY,
    sessions: [
      { starts_at: "2026-11-12T03:30:00Z", ends_at: "2026-11-12T05:30:00Z", mode: "SLOTS", places_left: 4, slots: SLOTS },
      { starts_at: "2026-11-12T08:30:00Z", ends_at: "2026-11-12T12:30:00Z", mode: "TOKENS", places_left: 12, slots: [] },
      { starts_at: "2026-11-12T11:30:00Z", ends_at: "2026-11-12T13:30:00Z", mode: "TOKENS", places_left: 2, slots: [] },
    ],
  },
  { date: "2026-11-14", sessions: [{ starts_at: "2026-11-14T03:30:00Z", ends_at: "2026-11-14T07:30:00Z", mode: "TOKENS", places_left: 1, slots: [] }] },
];

function Harness({ date: first = TODAY, choice: picked = null, language = "en" as "en" | "hi" }: Readonly<{ date?: string; choice?: Choice | null; language?: "en" | "hi" }>) {
  const availability = useAvailability("sample-clinic", DOCTOR, false);
  const [date, setDate] = useState(first);
  const [choice, setChoice] = useState<Choice | null>(picked);
  return (
    <>
      <AppointmentPicker
        availability={availability.state}
        timezone="Asia/Kolkata"
        language={language}
        today={TODAY}
        date={date}
        choice={choice}
        onDate={(d) => {
          setDate(d);
          setChoice(null);
        }}
        onChoice={setChoice}
        onRetry={() => void availability.refresh()}
      />
      <output data-testid="state">{JSON.stringify({ date, choice })}</output>
      <button type="button" onClick={() => void availability.refresh()}>
        test-refresh
      </button>
    </>
  );
}

const state = () => JSON.parse(screen.getByTestId("state").textContent ?? "{}") as { date: string; choice: Choice | null };

describe("the date and time picker (M7d-P2, design §4 decision 4, §7)", () => {
  it("selects today, shows the next three dates with what is left, and groups today's times", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness />);
    expect(await screen.findByRole("heading", { name: "Times on Thu, 12 Nov" })).toBeInTheDocument();
    const today = screen.getByRole("button", { name: /^Thu, 12 Nov, 18 left$/ });
    expect(today).toHaveAttribute("aria-pressed", "true");
    expect(within(today).getByText("Today")).toBeInTheDocument();
    // Tomorrow has nothing: said in words, not only greyed.
    expect(screen.getByRole("button", { name: "Fri, 13 Nov, No times" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getAllByRole("button", { name: /^\w{3}, \d+ Nov, / })).toHaveLength(4);
    expect(screen.getByText("18 places left")).toBeInTheDocument();
    for (const part of ["Morning", "Afternoon", "Evening"]) expect(screen.getByRole("group", { name: part })).toBeInTheDocument();
    // Three morning times, then the rest on request.
    const morning = screen.getByRole("group", { name: "Morning" });
    expect(within(morning).getAllByRole("button", { pressed: false })).toHaveLength(3);
    fireEvent.click(within(morning).getByRole("button", { name: "Show all morning times (1 more)" }));
    expect(within(morning).getByRole("button", { name: "10:30 am" })).toBeInTheDocument();
    expect(within(morning).getByRole("button", { name: "Show fewer morning times" })).toHaveAttribute("aria-expanded", "true");
  });

  it("marks the chosen slot and token session, and says the choice to a screen reader", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness />);
    const nine = await screen.findByRole("button", { name: "9:00 am" });
    fireEvent.click(nine);
    expect(nine).toHaveAttribute("aria-pressed", "true");
    expect(state().choice).toEqual({ session: "2026-11-12T03:30:00Z", slot: "2026-11-12T03:30:00Z" });
    expect(screen.getByText("Your choice: Thu, 12 Nov, 9:00 am")).toBeInTheDocument();
    // A token session: one row, its places, "Choose" then "Chosen".
    const row = screen.getByRole("button", { name: "Choose 2:00 pm–6:00 pm" });
    expect(row.closest("li")).toHaveTextContent("12 places left");
    fireEvent.click(row);
    expect(row).toHaveAttribute("aria-pressed", "true");
    expect(row).toHaveTextContent("Chosen");
    expect(nine).toHaveAttribute("aria-pressed", "false");
    expect(state().choice).toEqual({ session: "2026-11-12T08:30:00Z", slot: null });
    // Few places are flagged; the evening session has 2.
    expect(screen.getByText("2 places left")).toHaveClass("text-warning");
  });

  it("a date with nothing says so and offers the next available date", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness />);
    fireEvent.click(await screen.findByRole("button", { name: "Fri, 13 Nov, No times" }));
    expect(screen.getByText("No available times on this date.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next available: Sat, 14 Nov" }));
    expect(state().date).toBe("2026-11-14");
    expect(screen.getByRole("heading", { name: "Times on Sat, 14 Nov" })).toBeInTheDocument();
    // Nothing after Saturday: a later date offers the first free one instead.
    fireEvent.change(screen.getByLabelText("Another date"), { target: { value: "2026-11-20" } });
    expect(state().date).toBe("2026-11-20");
    expect(screen.getByRole("button", { name: "First available: Thu, 12 Nov" })).toBeInTheDocument();
  });

  it("limits the calendar to today and the next 13 days, and refuses others in words", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness />);
    const other = await screen.findByLabelText("Another date");
    expect(other).toHaveAttribute("type", "date");
    expect(other).toHaveAttribute("min", "2026-11-12");
    expect(other).toHaveAttribute("max", "2026-11-25");
    fireEvent.change(other, { target: { value: "2026-11-26" } });
    expect(state().date).toBe(TODAY);
    expect(other).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Choose a date from 12 Nov 2026 to 25 Nov 2026.")).toBeInTheDocument();
    fireEvent.change(other, { target: { value: "2026-11-11" } });
    expect(state().date).toBe(TODAY);
  });

  it("shows loading, then a failure with Try again that keeps the chosen date", async () => {
    mockApi({ [ROUTE]: [() => json(503, { error: { code: "SYS_UNAVAILABLE", message: "x", request_id: "r", details: {} } }), () => json(200, { days: DAYS })] });
    render(<Harness date="2026-11-14" />);
    expect(screen.getByText("Loading times.")).toHaveAttribute("role", "status");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("We could not load the times.");
    fireEvent.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("button", { name: "Choose 9:00 am–1:00 pm" })).toBeInTheDocument();
    expect(state().date).toBe("2026-11-14");
  });

  it("says when the chosen time is no longer offered after a refresh, and keeps the rest", async () => {
    const taken: Days = [{ ...DAYS[0]!, sessions: DAYS[0]!.sessions.map((s) => (s.mode === "SLOTS" ? { ...s, places_left: 3, slots: SLOTS.slice(1) } : s)) }];
    mockApi({ [ROUTE]: [() => json(200, { days: DAYS }), () => json(200, { days: taken })] });
    render(<Harness choice={{ session: "2026-11-12T03:30:00Z", slot: "2026-11-12T03:30:00Z" }} />);
    expect(await screen.findByRole("button", { name: "9:00 am" })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: "test-refresh" }));
    expect(await screen.findByText("The time you chose is no longer available. Please choose another.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "9:00 am" })).not.toBeInTheDocument();
    expect(screen.getByText("17 places left")).toBeInTheDocument();
  });

  it("opens the part of the day that holds a chosen time beyond the first three", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness choice={{ session: "2026-11-12T03:30:00Z", slot: "2026-11-12T05:00:00Z" }} />);
    expect(await screen.findByRole("button", { name: "10:30 am" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: /Show (all|fewer) morning/ })).not.toBeInTheDocument();
  });

  it("fetches again when the patient comes back after a minute, not before", async () => {
    const api = mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    const now = vi.spyOn(Date, "now").mockReturnValue(1_000_000);
    render(<Harness />);
    await screen.findByRole("group", { name: "Morning" });
    expect(api.count(ROUTE)).toBe(1);
    now.mockReturnValue(1_000_000 + 59_000);
    fireEvent.focus(window);
    await flush();
    expect(api.count(ROUTE)).toBe(1);
    now.mockReturnValue(1_000_000 + 61_000);
    fireEvent.focus(window);
    await flush();
    expect(api.count(ROUTE)).toBe(2);
    now.mockRestore();
  });

  it("speaks Hindi on the Hindi page", async () => {
    mockApi({ [ROUTE]: () => json(200, { days: DAYS }) });
    render(<Harness language="hi" />);
    expect(await screen.findByRole("group", { name: "सुबह" })).toBeInTheDocument();
    expect(screen.getByText("तारीख़ चुनें")).toBeInTheDocument();
    expect(screen.getByLabelText("कोई और तारीख़")).toBeInTheDocument();
  });
});
