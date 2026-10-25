import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import { liveWords } from "@/lib/i18n/patient-notifications";
import { apiError, json, mockApi } from "@/test/api";

import { LIVE_INTERVAL_MS, LiveQueueView, type LiveQueue } from "./LiveQueueView";
import { liveProblemOf, liveProblemText } from "./problems";

const TOKEN = "signed-token";
const PATH = `GET /api/v1/public/queue/${TOKEN}`;

const VIEW: LiveQueue = {
  clinic_name: "Sample Clinic",
  doctor_name: "Dr. Mehta",
  timezone: "Asia/Kolkata",
  mode: "TOKENS",
  state: "WAITING",
  token_number: 7,
  slot_start: null,
  ahead: 2,
  now_seeing_token: 4,
  now_seeing_slot: null,
  session_starts_at: "2026-10-22T04:30:00Z",
};

beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
afterEach(() => vi.useRealTimers());

describe("the live token page (M6b-P6, R69-R72, AC27)", () => {
  it("shows the token, who is ahead and who is being seen, then follows the queue", async () => {
    const api = mockApi({ [PATH]: [() => json(200, { ...VIEW, ahead: 0, now_seeing_token: 6 }, { ETag: '"b"' })] });
    render(<LiveQueueView token={TOKEN} language="en" initial={VIEW} initialEtag={'"a"'} />);

    expect(screen.getByRole("heading", { level: 2, name: "Your token: 7" })).toBeInTheDocument();
    expect(screen.getByText("2 people ahead of you")).toBeInTheDocument();
    expect(screen.getByText("Now seeing: token 4")).toBeInTheDocument();
    expect(api.calls).toHaveLength(0); // the server already rendered it

    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_INTERVAL_MS);
    });
    expect(api.calls[0]?.headers.get("If-None-Match")).toBe('"a"');
    expect(await screen.findByText("Nobody is ahead of you.")).toBeInTheDocument();
    expect(screen.getByText("Now seeing: token 6")).toBeInTheDocument();
  });

  it("says it is your turn, in Hindi when asked", () => {
    mockApi({});
    render(<LiveQueueView token={TOKEN} language="hi" initial={{ ...VIEW, state: "YOUR_TURN" }} initialEtag={'"a"'} />);
    expect(screen.getByText("आपकी बारी है। कृपया अंदर जाएँ।")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View in English" })).toHaveAttribute("href", "?lang=en");
  });

  it("an expired link stops asking and says why", async () => {
    const api = mockApi({ [PATH]: [() => apiError(410, "LINK_EXPIRED", "This link has expired.")] });
    render(<LiveQueueView token={TOKEN} language="en" initial={VIEW} initialEtag={'"a"'} />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(LIVE_INTERVAL_MS);
    });
    expect(await screen.findByRole("alert")).toHaveTextContent(liveWords("en").expired);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * LIVE_INTERVAL_MS);
    });
    expect(api.count(PATH)).toBe(1);
  });

  it("maps the API's answers to the page's words", () => {
    const words = liveWords("en");
    expect(liveProblemOf(new ApiError("LINK_INVALID", "x", 404, "r"))).toBe("invalid");
    expect(liveProblemOf(new ApiError("LINK_EXPIRED", "x", 410, "r"))).toBe("expired");
    expect(liveProblemOf(new ApiError("RATE_LIMITED", "x", 429, "r"))).toBe("rate");
    expect(liveProblemOf(new Error("boom"))).toBe("unavailable");
    expect(liveProblemText(words, "invalid")).toBe(words.invalid);
  });
});
