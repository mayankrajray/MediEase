import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Landing } from "./Landing";

afterEach(() => {
  delete window.__meAnalytics;
});

describe("the landing page (M6c-P8, FR-LND-01..03)", () => {
  it("offers the clinic path and the patient path, with pricing and the emergency notice", () => {
    render(<Landing language="en" />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Apply to join MediEase" })[0]).toHaveAttribute("href", "/apply");
    expect(screen.getAllByRole("link", { name: "Find a doctor" })[0]).toHaveAttribute("href", "/find");
    expect(screen.getByRole("link", { name: /Sign in to the patient app/ })).toHaveAttribute("href", "/portal/sign-in");
    const pricing = screen.getByRole("region", { name: "Pricing" });
    expect(within(pricing).getByText("₹499")).toBeInTheDocument();
    expect(within(pricing).getAllByText("14-day free trial")).toHaveLength(3);
    expect(screen.getByText(/about 5 minutes/)).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/not for emergencies/);
  });

  it("records PII-free events: the view and the call to action used", () => {
    render(<Landing language="hi" />);
    fireEvent.click(screen.getAllByRole("link", { name: "डॉक्टर खोजें" })[0] as HTMLElement);
    expect(window.__meAnalytics).toEqual([
      { event: "landing_viewed", lang: "hi" },
      { event: "landing_cta_clicked", cta: "find", lang: "hi" },
    ]);
    expect(screen.getAllByRole("link", { name: "डॉक्टर खोजें" })[0]).toHaveAttribute("href", "/find?lang=hi");
  });
});
