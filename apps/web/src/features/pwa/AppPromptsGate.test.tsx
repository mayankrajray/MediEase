import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppPromptsGate } from "./AppPromptsGate";

/** M7e-E1 (NFR-02): the prompts load only when this device has something to be offered. */

const DESKTOP = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36";

beforeEach(() => {
  window.localStorage.clear();
  delete window.__mediease;
  vi.spyOn(navigator, "userAgent", "get").mockReturnValue(DESKTOP);
  Object.defineProperty(navigator, "maxTouchPoints", { value: 0, configurable: true });
  vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })));
});

describe("AppPromptsGate (M7e-E1)", () => {
  it("renders nothing while there is nothing to offer, then the prompt once the browser can install", async () => {
    const { container } = render(<AppPromptsGate language="en" />);
    expect(container).toBeEmptyDOMElement();

    act(() => {
      window.__mediease = { install: Object.assign(new Event("beforeinstallprompt"), { prompt: vi.fn(), userChoice: Promise.resolve({ outcome: "accepted" }) }) as never };
      window.dispatchEvent(new Event("mediease:installable"));
    });
    expect(await screen.findByRole("region", { name: "Install the MediEase app" })).toBeInTheDocument();
  });

  it("stays empty once the offer was answered on this device", () => {
    window.localStorage.setItem("me_app_prompt", "answered");
    window.__mediease = { install: new Event("beforeinstallprompt") as never };
    const { container } = render(<AppPromptsGate language="en" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("an update always gets through, even after the install offer was answered", async () => {
    window.localStorage.setItem("me_app_prompt", "answered");
    render(<AppPromptsGate language="hi" />);
    act(() => {
      window.__mediease = { waiting: { postMessage: vi.fn() } as never };
      window.dispatchEvent(new Event("mediease:update"));
    });
    expect(await screen.findByRole("status")).toHaveTextContent("MediEase का नया संस्करण तैयार है।");
  });
});
