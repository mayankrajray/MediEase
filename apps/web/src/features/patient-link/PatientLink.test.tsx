import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { components } from "@/lib/api/schema";

import { ChallengeForm, LinkProblem } from "./ChallengeForm";
import { PrescriptionView } from "./PrescriptionView";
import { stringsFor } from "./strings";
import { problemFor, readProblem } from "./view-cookie";

type Page = components["schemas"]["PatientPrescriptionPage"];

const PAGE: Page = {
  language: "en",
  version: 2,
  clinic_name: "Sample Clinic",
  clinic_phone_e164: "+919000000000",
  call_label: "Call the clinic",
  doctor_name: "Dr. Sample Doctor",
  doctor_lines: ["MBBS", "Reg. No. SAMPLE-0001, Sample State Medical Council"],
  issued_on: { label: "Date", value: "19 Oct 2026" },
  updated_note: "Updated by your doctor on 19 Oct 2026",
  medicines_heading: "Medicines",
  medicines: [
    {
      number: 1,
      name: "Syrup X",
      form_strength: null,
      fields: [
        { label: "How much", value: "5 ml" },
        { label: "When to take", value: "Twice a day, morning and night, after food" },
        { label: "How to give", value: "Shake well before use; Mix in 10 ml of water" },
      ],
    },
  ],
  advice_heading: "Advice",
  advice: [{ heading: "Come back immediately if", entries: ["breathing is difficult"] }],
  advice_notes: null,
  follow_up: { label: "Next visit", value: "24 Oct 2026" },
};

describe("the patient page (M4-P5, spec §6, R11, R12, AC2)", () => {
  it("AC2: one card per medicine, the dilution under How to give, and a call button", () => {
    render(<PrescriptionView page={PAGE} strings={stringsFor("en")} switchHref="/p/t?lang=hi" />);
    const [card] = screen.getAllByRole("listitem");
    if (card === undefined) throw new Error("no card");
    expect(within(card).getByRole("heading", { level: 3 })).toHaveTextContent("1. Syrup X");
    const term = within(card).getByText("How to give");
    expect(term.nextElementSibling).toHaveTextContent("Mix in 10 ml of water");
    expect(screen.getByRole("status")).toHaveTextContent("Updated by your doctor"); // R11
    expect(screen.getByRole("link", { name: "Call the clinic" })).toHaveAttribute("href", "tel:+919000000000");
    expect(screen.getByRole("link", { name: "हिन्दी में देखें" })).toHaveAttribute("href", "/p/t?lang=hi");
    expect(screen.getByRole("main")).toHaveAttribute("lang", "en");
  });

  it("R19: a Hindi page is marked as Hindi and offers English", () => {
    render(<PrescriptionView page={{ ...PAGE, language: "hi" }} strings={stringsFor("hi")} switchHref="/p/t?lang=en" />);
    expect(screen.getByRole("main")).toHaveAttribute("lang", "hi");
    expect(screen.getByRole("link", { name: "View in English" })).toBeInTheDocument();
  });
});

describe("the last-4 check (M4-P5, spec R10)", () => {
  it("is a plain form posting to the page's route handler, with a labelled numeric field", () => {
    render(
      <ChallengeForm token="a.b.c" clinicName="Sample Clinic" language="en" strings={stringsFor("en")} locked={false} switchHref="/p/a.b.c?lang=hi" />,
    );
    const field = screen.getByLabelText("Last 4 digits of your phone number");
    expect(field).toHaveAttribute("inputmode", "numeric");
    expect(field).toHaveAttribute("pattern", "[0-9]{4}");
    expect(field.closest("form")).toHaveAttribute("action", "/p/a.b.c/verify");
    expect(field.closest("form")).toHaveAttribute("method", "post");
    expect(screen.getByText("From Sample Clinic")).toBeInTheDocument();
  });

  it("announces a wrong answer next to the field", () => {
    const strings = stringsFor("en");
    render(
      <ChallengeForm token="t" clinicName="C" language="en" strings={strings} problem={strings.wrong(3)} locked={false} switchHref="/p/t" />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("3 tries left");
    expect(screen.getByLabelText(/Last 4 digits/)).toHaveAccessibleDescription(/3 tries left/);
  });

  it("AC3: a locked link shows only the message, no form", () => {
    const strings = stringsFor("hi");
    render(<ChallengeForm token="t" clinicName="C" language="hi" strings={strings} problem={strings.locked} locked switchHref="/p/t" />);
    expect(screen.getByRole("alert")).toHaveTextContent("क्लिनिक से संपर्क करें");
    expect(screen.queryByRole("textbox")).toBeNull();
  });

  it("a broken link says only that", () => {
    render(<LinkProblem language="en" message={stringsFor("en").invalid} />);
    expect(screen.getByRole("alert")).toHaveTextContent("This link isn't valid");
  });
});

describe("problems in the URL", () => {
  it("only allow-listed values are read", () => {
    expect(readProblem("locked")).toBe("locked");
    expect(readProblem("<script>")).toBeUndefined();
    expect(readProblem(["locked"])).toBeUndefined();
  });

  it("maps API codes, anything unknown to unavailable", () => {
    expect(problemFor("LINK_REVOKED")).toBe("revoked");
    expect(problemFor("REQ_VALIDATION_FAILED")).toBe("failed");
    expect(problemFor("WEB_API_UNREACHABLE")).toBe("unavailable");
  });

  it("both languages have every string", () => {
    for (const lang of ["en", "hi"] as const) {
      const s = stringsFor(lang);
      for (const value of Object.values(s)) {
        expect(typeof value === "function" ? value(2) : value).not.toBe("");
      }
    }
    expect(stringsFor("en").wrong(1)).toContain("1 try left");
    expect(stringsFor("en").wrong(undefined)).toBe("Those digits don't match.");
  });
});
