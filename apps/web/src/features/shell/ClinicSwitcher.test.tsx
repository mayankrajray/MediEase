import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CLINIC_A, CLINIC_B, membership } from "@/features/auth/testing";

import { ClinicSwitcher } from "./ClinicSwitcher";

const a = membership(CLINIC_A, "Alpha Clinic", "OWNER");
const b = membership(CLINIC_B, "Beta Clinic", "DOCTOR");

describe("ClinicSwitcher", () => {
  it("FR-AUTH-03: renders nothing for a person with one clinic", () => {
    const { container } = render(<ClinicSwitcher memberships={[a]} activeClinicId={CLINIC_A} onSelect={vi.fn()} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("FR-AUTH-03: lists every clinic with the person's role in it and marks the active one", () => {
    render(<ClinicSwitcher memberships={[a, b]} activeClinicId={CLINIC_B} onSelect={vi.fn()} />);

    const select = screen.getByRole("combobox", { name: "Clinic" });
    expect(select).toHaveValue(CLINIC_B);
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "Alpha Clinic (Owner)",
      "Beta Clinic (Doctor)",
    ]);
  });

  it("FR-AUTH-03: reports the chosen clinic", () => {
    const onSelect = vi.fn();
    render(<ClinicSwitcher memberships={[a, b]} activeClinicId={CLINIC_A} onSelect={onSelect} />);

    fireEvent.change(screen.getByRole("combobox", { name: "Clinic" }), { target: { value: CLINIC_B } });

    expect(onSelect).toHaveBeenCalledExactlyOnceWith(CLINIC_B);
  });
});
