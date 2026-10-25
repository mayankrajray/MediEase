import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { json, mockApi, noContent } from "@/test/api";
import { navigation, resetNavigation } from "@/test/navigation";

import { MyAppointments, isLiveToday } from "./MyAppointments";
import { PortalAccountPage } from "./PortalAccountPage";
import { portalBadge } from "./PortalBell";
import { PortalNotifications } from "./PortalNotifications";
import { CLINIC_ID, me, PREFERENCES, renderPortal } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const N1 = "0192f0a0-0000-7000-8000-0000000000a1";
const N2 = "0192f0a0-0000-7000-8000-0000000000a2";
const APPT = "0192f0a0-0000-7000-8000-0000000000b1";
const HOUR = 3_600_000;

function notice(id: string, title: string, read = false) {
  return {
    id,
    kind: "booking.accepted",
    title,
    link: "/portal/appointments",
    created_at: "2026-10-22T05:30:00Z",
    read_at: read ? "2026-10-22T06:00:00Z" : null,
  };
}

function todayIn(zone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).format(Date.now());
}

function appointment(extra: Record<string, unknown> = {}) {
  const start = new Date(Date.now() - HOUR);
  return {
    id: APPT,
    doctor_name: "Dr. Mehta",
    on_date: todayIn("Asia/Kolkata"),
    starts_at: start.toISOString(),
    session_starts_at: start.toISOString(),
    session_ends_at: new Date(Date.now() + 2 * HOUR).toISOString(),
    mode: "TOKENS",
    slot_start: null,
    token_number: 7,
    status: "BOOKED",
    ...extra,
  };
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  navigation.pathname = "/portal/notifications";
  document.cookie = "me_pt_csrf=portal-csrf; path=/";
});

describe("the portal bell (M6b-P6, R67)", () => {
  it("shows the unread count from the summary and opens Notifications", async () => {
    mockApi({
      ...me(),
      "GET /api/v1/portal/notifications/summary": () => json(200, { unread: 12, latest_id: N1 }, { ETag: '"n12"' }),
      "GET /api/v1/portal/notifications": () => json(200, { items: [] }),
    });
    await renderPortal(<PortalNotifications />);
    const bell = await screen.findByRole("link", { name: "Notifications, 12 unread" });
    expect(bell).toHaveAttribute("href", "/portal/notifications");
    expect(within(bell).getByText("9+")).toBeInTheDocument();
    expect(portalBadge(3)).toBe("3");
  });

  it("is in Hindi when the account is", async () => {
    mockApi({
      ...me({ language: "hi" }),
      "GET /api/v1/portal/notifications/summary": () => json(200, { unread: 2, latest_id: N1 }),
      "GET /api/v1/portal/notifications": () => json(200, { items: [] }),
    });
    await renderPortal(<PortalNotifications />);
    expect(await screen.findByRole("link", { name: "सूचनाएँ, 2 बिना पढ़ी" })).toBeInTheDocument();
  });
});

describe("Notifications (M6b-P6, R55, R68)", () => {
  it("lists the API's titles, marks one read on opening and all with one button", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/notifications": () =>
        json(200, { items: [notice(N1, "Booked: Sample Clinic"), notice(N2, "Older one", true)] }),
      [`POST /api/v1/portal/notifications/${N1}/read`]: () => noContent(),
      "POST /api/v1/portal/notifications/read-all": () => json(200, { marked: 1 }),
    });
    await renderPortal(<PortalNotifications />);

    const list = await screen.findByRole("list", { name: "Notifications" });
    const first = within(list).getByRole("link", { name: /Unread:\s*Booked: Sample Clinic/ });
    expect(first).toHaveAttribute("href", "/portal/appointments");
    expect(within(list).getByRole("link", { name: /^Older one/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark all as read" }));
    expect(await screen.findByText("All notifications marked as read.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark all as read" })).not.toBeInTheDocument();
    expect(api.count("POST /api/v1/portal/notifications/read-all")).toBe(1);
    expect(api.calls.find((c) => c.path.endsWith("/read-all"))?.headers.get("X-CSRF-Token")).toBe("portal-csrf");
  });

  it("opening an unread one records the read", async () => {
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/notifications": () => json(200, { items: [notice(N1, "Booked: Sample Clinic")] }),
      [`POST /api/v1/portal/notifications/${N1}/read`]: () => noContent(),
    });
    await renderPortal(<PortalNotifications />);
    fireEvent.click(await screen.findByRole("link", { name: /Booked: Sample Clinic/ }));
    await waitFor(() => expect(api.count(`POST /api/v1/portal/notifications/${N1}/read`)).toBe(1));
  });

  it("says when there is nothing yet", async () => {
    mockApi({ ...me(), "GET /api/v1/portal/notifications": () => json(200, { items: [] }) });
    await renderPortal(<PortalNotifications />);
    expect(await screen.findByText(/Nothing yet\./)).toBeInTheDocument();
  });
});

describe("notification switches (M6b-P6, R62, R63)", () => {
  it("offers email only for booking answers and saves a switch", async () => {
    navigation.pathname = "/portal/account";
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/links": () => json(200, { items: [] }),
      "PUT /api/v1/portal/notification-preferences": (call) =>
        json(200, {
          items: PREFERENCES.map((p) => (p.kind === "booking.accepted" ? { ...p, email: (call.body as { enabled: boolean }).enabled } : p)),
        }),
    });
    await renderPortal(<PortalAccountPage />);

    const accepted = await screen.findByRole("group", { name: "Booking request accepted" });
    const due = screen.getByRole("group", { name: "Medicine time" });
    expect(within(due).queryByRole("checkbox", { name: "Email" })).not.toBeInTheDocument();
    fireEvent.click(within(accepted).getByRole("checkbox", { name: "Email" }));

    expect(await screen.findByText("Notification settings saved.")).toBeInTheDocument();
    expect(api.calls.find((c) => c.method === "PUT")?.body).toEqual({ kind: "booking.accepted", channel: "EMAIL", enabled: false });
    expect(within(accepted).getByRole("checkbox", { name: "Email" })).not.toBeChecked();
  });
});

describe("Live queue on My appointments (M6b-P6, R69)", () => {
  it("today's appointment opens the live page from its own link", async () => {
    navigation.pathname = "/portal/appointments";
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign, origin: "http://localhost" });
    const api = mockApi({
      ...me(),
      "GET /api/v1/portal/appointments": () =>
        json(200, {
          items: [{ clinic_id: CLINIC_ID, clinic_name: "Sample Clinic", timezone: "Asia/Kolkata", phone_e164: null, appointments: [appointment()] }],
        }),
      "GET /api/v1/portal/reminders": () => json(200, { items: [] }),
      "GET /api/v1/portal/booking-requests": () => json(200, { items: [] }),
      [`GET /api/v1/portal/appointments/${APPT}/live-link`]: () =>
        json(200, { url: "https://example.test/q/signed-token", expires_at: "2026-10-22T14:30:00Z" }),
    });
    await renderPortal(<MyAppointments />);

    fireEvent.click(await screen.findByRole("button", { name: "Live queue" }));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/q/signed-token"));
    expect(api.count(`GET /api/v1/portal/appointments/${APPT}/live-link`)).toBe(1);
    vi.unstubAllGlobals();
  });

  it("only today's appointments still in the queue have one", () => {
    const now = Date.now();
    expect(isLiveToday(appointment() as never, "Asia/Kolkata", now)).toBe(true);
    expect(isLiveToday(appointment({ status: "COMPLETED" }) as never, "Asia/Kolkata", now)).toBe(false);
    expect(isLiveToday(appointment({ status: "CANCELLED" }) as never, "Asia/Kolkata", now)).toBe(false);
    expect(isLiveToday(appointment({ on_date: "2020-01-01" }) as never, "Asia/Kolkata", now)).toBe(false);
    expect(isLiveToday(appointment({ session_ends_at: new Date(now - 1000).toISOString() }) as never, "Asia/Kolkata", now)).toBe(false);
  });
});
