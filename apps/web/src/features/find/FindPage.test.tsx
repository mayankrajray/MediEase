import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FindPage, findHref, type FindQuery } from "./FindPage";
import { apiFilters, readQuery } from "./query";

const QUERY: FindQuery = { kind: "doctors", q: "mehta", where: "560001", specialty: "", language: "Hindi", available: true };
const OPTIONS = { specialties: ["General Medicine", "Paediatrics"], languages: ["English", "Hindi"] };

const DOCTOR = {
  id: "0192f0a0-0000-7000-8000-0000000000d1",
  display_name: "Dr. Mehta",
  qualification: "MBBS",
  specialty: "General Medicine",
  languages: ["Hindi", "English"],
  fee_paise: 30000,
  next_available: "2026-10-28",
  clinic: { slug: "sample-clinic", name: "Sample Clinic", city: "Pune", state: "MH", pincode: "411001" },
};

describe("directory search (M6c-P6, discovery R1-R10)", () => {
  it("reads the URL and turns `where` into a PIN or a city", () => {
    const query = readQuery({ q: " mehta ", where: "560001", available: "true", type: "clinics" });
    expect(query).toEqual({ kind: "clinics", q: "mehta", where: "560001", specialty: "", language: "", available: true });
    expect(apiFilters(query)).toEqual({ q: "mehta", pincode: "560001", available: "true" });
    expect(apiFilters({ ...query, where: "Pune" })).toEqual({ q: "mehta", city: "Pune", available: "true" });
    expect(findHref(QUERY, "hi", "clinics")).toBe("/find?type=clinics&q=mehta&where=560001&language=Hindi&available=true&lang=hi");
  });

  it("lists doctors with their clinic, languages, fee and first free day, linking to the profile", () => {
    render(<FindPage query={QUERY} result={{ status: "doctors", items: [DOCTOR] }} options={OPTIONS} language="en" />);
    expect(screen.getByRole("search")).toBeInTheDocument();
    expect(screen.getByLabelText("Doctor, clinic or specialty")).toHaveValue("mehta");
    expect(screen.getByLabelText("Free in the next 7 days")).toBeChecked();
    const item = screen.getByRole("listitem");
    expect(within(item).getByText("Sample Clinic, Pune")).toBeInTheDocument();
    expect(within(item).getByText("Fee ₹300")).toBeInTheDocument();
    expect(within(item).getByText(/^Free from /)).toBeInTheDocument();
    expect(within(item).getByRole("link", { name: /See profile and times/ })).toHaveAttribute("href", `/c/sample-clinic/doctors/${DOCTOR.id}?via=directory`);
    expect(screen.getByRole("link", { name: "Doctors" })).toHaveAttribute("aria-current", "page");
  });

  it("says when nothing matches, and when search is limited, in Hindi too", () => {
    const { rerender } = render(<FindPage query={QUERY} result={{ status: "doctors", items: [] }} options={OPTIONS} language="en" />);
    expect(screen.getByText(/Nothing matches yet/)).toBeInTheDocument();
    rerender(<FindPage query={QUERY} result={{ status: "limited" }} options={undefined} language="hi" />);
    expect(screen.getByRole("alert")).toHaveTextContent("बहुत ज़्यादा खोजें");
  });
});
