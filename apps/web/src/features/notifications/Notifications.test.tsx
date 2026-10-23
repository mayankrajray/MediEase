import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { renderInWorkspace, workspaceRoutes } from "@/features/patients/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import type { Notification, Preference } from "./api";
import { badgeText } from "./NotificationBell";
import { NotificationPreferences } from "./NotificationPreferences";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const SUMMARY = "GET /api/v1/notifications/summary";
const N1 = "0192f0a0-0000-7000-8000-00000000a001";
const N2 = "0192f0a0-0000-7000-8000-00000000a002";

function notification(id: string, title: string, read = false): Notification {
  return {
    id,
    kind: "appointment.booked",
    title,
    link: "/queue?date=2026-10-23",
    entity_type: "appointment",
    entity_id: "0192f0a0-0000-7000-8000-00000000b001",
    created_at: "2026-10-22T05:00:00+00:00",
    read_at: read ? "2026-10-22T06:00:00+00:00" : null,
  };
}

const PREFERENCES: Preference[] = [
  { kind: "appointment.booked", label: "A patient is booked with me", channel: "IN_APP", enabled: true },
  { kind: "appointment.arrived", label: "My patient has arrived", channel: "IN_APP", enabled: true },
];

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function render(routes: Parameters<typeof mockApi>[0] = {}) {
  const api = mockApi({
    ...workspaceRoutes,
    "GET /api/v1/notifications/preferences": () => json(200, { items: PREFERENCES }),
    ...routes,
  });
  renderInWorkspace(<NotificationPreferences />);
  return api;
}

const bell = (name: RegExp = /^Notifications/) => screen.findByRole("button", { name }, { timeout: 5000 });

describe("the notification bell (M6a-P7, FR-NTF-03)", () => {
  it("shows the unread count, lists the latest and marks them all read", async () => {
    const api = render({
      [SUMMARY]: () => json(200, { unread: 2, latest_id: N1 }, { ETag: '"s1"' }),
      "GET /api/v1/notifications": () =>
        json(200, { items: [notification(N1, "Asha · SC-0001 booked for 23 Oct, token 4"), notification(N2, "Bina · SC-0002 booked for 23 Oct, token 5")] }),
      "POST /api/v1/notifications/read-all": () => json(200, { updated: 2 }),
    });

    fireEvent.click(await bell(/^Notifications, 2 unread$/));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    const list = await within(drawer).findByRole("list", { name: "Latest notifications" });
    const links = within(list).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/queue?date=2026-10-23", "/queue?date=2026-10-23"]);
    expect(links[0]).toHaveTextContent("Unread: Asha · SC-0001 booked for 23 Oct, token 4");
    expect(within(drawer).getByRole("link", { name: "Notification settings" })).toHaveAttribute(
      "href",
      "/settings/notifications",
    );

    fireEvent.click(within(drawer).getByRole("button", { name: "Mark all as read" }));

    expect(await within(drawer).findByText("All notifications marked as read.")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Mark all as read" })).not.toBeInTheDocument();
    expect(within(list).getAllByRole("link")[0]).not.toHaveTextContent("Unread:");
    expect(api.count("POST /api/v1/notifications/read-all")).toBe(1);
    expect(screen.getByRole("button", { name: /^Notifications$/, hidden: true })).toBeInTheDocument();
  });

  it("opening one marks it read and closes the drawer", async () => {
    const api = render({
      [SUMMARY]: () => json(200, { unread: 1, latest_id: N1 }),
      "GET /api/v1/notifications": () => json(200, { items: [notification(N1, "Asha · SC-0001 booked for 23 Oct, token 4")] }),
      [`POST /api/v1/notifications/${N1}/read`]: () => json(200, notification(N1, "Asha", true)),
    });

    fireEvent.click(await bell(/1 unread/));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    fireEvent.click(await within(drawer).findByRole("link", { name: /Asha · SC-0001/ }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Notifications" })).not.toBeInTheDocument());
    expect(api.count(`POST /api/v1/notifications/${N1}/read`)).toBe(1);
    expect(await bell(/^Notifications$/)).toBeInTheDocument();
  });

  it("says when there is nothing yet, and offers a retry when the list fails", async () => {
    render({
      [SUMMARY]: () => json(200, { unread: 0, latest_id: null }),
      "GET /api/v1/notifications": [
        () => apiError(503, "SYS_UNAVAILABLE", "Try again shortly."),
        () => json(200, { items: [] }),
      ],
    });

    fireEvent.click(await bell(/^Notifications$/));
    const drawer = await screen.findByRole("dialog", { name: "Notifications" });
    fireEvent.click(await within(drawer).findByRole("button", { name: /Try again/ }));
    expect(await within(drawer).findByText("No notifications yet")).toBeInTheDocument();
    expect(within(drawer).queryByRole("button", { name: "Mark all as read" })).not.toBeInTheDocument();
  });

  it("caps the badge at 9+", () => {
    expect([0, 1, 9, 10, 250].map(badgeText)).toEqual(["0", "1", "9", "9+", "9+"]);
  });
});

describe("my notification settings (M6a-P7, FR-NTF-05)", () => {
  it("lists each kind, on by default, and saves a change at once", async () => {
    const api = render({
      "PUT /api/v1/notifications/preferences": () =>
        json(200, { items: PREFERENCES.map((p) => (p.kind === "appointment.booked" ? { ...p, enabled: false } : p)) }),
    });

    expect(await screen.findByRole("heading", { name: "Notifications", level: 1 })).toBeInTheDocument();
    const booked = await screen.findByRole("checkbox", { name: "A patient is booked with me" });
    expect(booked).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "My patient has arrived" })).toBeChecked();

    fireEvent.click(booked);

    expect(await screen.findByText("Saved: “A patient is booked with me” is off.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "A patient is booked with me" })).not.toBeChecked();
    const put = api.calls.find((c) => c.method === "PUT");
    expect(put?.body).toEqual({ items: [{ kind: "appointment.booked", channel: "IN_APP", enabled: false }] });
  });

  it("keeps the switch as it was when saving fails", async () => {
    render({
      "PUT /api/v1/notifications/preferences": () => apiError(503, "SYS_UNAVAILABLE", "Try again shortly."),
    });

    const booked = await screen.findByRole("checkbox", { name: "A patient is booked with me" });
    fireEvent.click(booked);

    expect(await screen.findByRole("alert")).toHaveTextContent(/Try again shortly|try again/i);
    expect(screen.getByRole("checkbox", { name: "A patient is booked with me" })).toBeChecked();
  });
});
