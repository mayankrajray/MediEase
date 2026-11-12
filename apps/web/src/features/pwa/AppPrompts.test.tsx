import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AppPrompts, PROMPT_KEY } from "./AppPrompts";

/** M7e-E1: the install offer (once per device), iPhone guidance, and Update. */

function installPrompt(outcome: "accepted" | "dismissed" = "accepted") {
  const event = Object.assign(new Event("beforeinstallprompt"), {
    prompt: vi.fn(async () => undefined),
    userChoice: Promise.resolve({ outcome }),
  });
  return event;
}

function standalone(on: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({ matches: on && query === "(display-mode: standalone)", media: query, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

function userAgent(ua: string, touchPoints = 0) {
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(ua);
  // jsdom has no maxTouchPoints; define it for the test.
  Object.defineProperty(navigator, "maxTouchPoints", { value: touchPoints, configurable: true });
}

const ANDROID = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36";
const IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 Version/17.5 Mobile/15E148 Safari/604.1";

beforeEach(() => {
  window.localStorage.clear();
  delete window.__mediease;
  standalone(false);
  userAgent(ANDROID);
});
afterEach(() => {
  delete window.__mediease;
});

describe("AppPrompts (M7e-E1)", () => {
  it("offers Install when the browser can install, and shows the browser's own prompt", async () => {
    render(<AppPrompts language="en" />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();

    const prompt = installPrompt();
    act(() => {
      window.__mediease = { install: prompt as never };
      window.dispatchEvent(new Event("mediease:installable"));
    });
    const card = screen.getByRole("region", { name: "Install the MediEase app" });
    fireEvent.click(screen.getByRole("button", { name: "Install" }));
    await act(async () => undefined);
    expect(prompt.prompt).toHaveBeenCalledTimes(1);
    expect(card).not.toBeInTheDocument();
    expect(window.localStorage.getItem(PROMPT_KEY)).toBe("answered");
  });

  it("is shown once: Not now is remembered on this device", () => {
    window.__mediease = { install: installPrompt() as never };
    const { unmount } = render(<AppPrompts language="en" />);
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
    unmount();
    render(<AppPrompts language="en" />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("offers nothing inside the installed app", () => {
    standalone(true);
    window.__mediease = { install: installPrompt() as never };
    render(<AppPrompts language="en" />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("on an iPhone, explains Add to Home Screen in the patient's language, once", () => {
    userAgent(IPHONE);
    const { unmount } = render(<AppPrompts language="hi" />);
    const card = screen.getByRole("region", { name: "MediEase को होम स्क्रीन पर जोड़ें" });
    expect(card).toHaveTextContent("Add to Home Screen चुनें।");
    // The X closes it too, under its own name.
    fireEvent.click(screen.getByRole("button", { name: "बंद करें" }));
    unmount();
    render(<AppPrompts language="hi" />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });

  it("an iPad that reports itself as a Mac still gets the guidance", () => {
    userAgent("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15", 5);
    render(<AppPrompts language="en" />);
    expect(screen.getByRole("region", { name: "Add MediEase to your Home Screen" })).toBeInTheDocument();
  });

  it("says a new version is ready, and Update hands over to it once", () => {
    const waiting = { postMessage: vi.fn() };
    render(<AppPrompts language="en" />);
    act(() => {
      window.__mediease = { waiting: waiting as never };
      window.dispatchEvent(new Event("mediease:update"));
    });
    expect(screen.getByRole("status")).toHaveTextContent("A new version of MediEase is ready.");
    const update = screen.getByRole("button", { name: "Update" });
    fireEvent.click(update);
    fireEvent.click(update);
    expect(waiting.postMessage).toHaveBeenCalledTimes(1);
    expect(waiting.postMessage).toHaveBeenCalledWith({ type: "SKIP_WAITING" });
    expect(window.__mediease?.updating).toBe(true);
  });

  it("with storage blocked, does not offer at all rather than on every page", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    window.__mediease = { install: installPrompt() as never };
    render(<AppPrompts language="en" />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});
