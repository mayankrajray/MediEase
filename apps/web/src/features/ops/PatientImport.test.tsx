import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { CLINIC_A, ops } from "@/features/auth/testing";
import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { resetNavigation } from "@/test/navigation";

import { PatientImport } from "./PatientImport";
import { codeRange, duplicateText, fileProblem, type ImportReport, importable, problemText } from "./patientImportReport";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const IMPORT = "POST /api/v1/ops/clinics/" + CLINIC_A + "/patient-imports";
const base = {
  "GET /api/v1/me": () => json(200, ops()),
  [`GET /api/v1/ops/clinics/${CLINIC_A}`]: () => json(200, { id: CLINIC_A, name: "Sample Clinic", slug: "sample-clinic", status: "ACTIVE" }),
};

const report = (overrides: Partial<ImportReport> = {}): ImportReport => ({
  dry_run: true,
  rows: 10,
  valid: 8,
  invalid: 2,
  possible_duplicates: 2,
  already_registered: 1,
  imported: 0,
  codes: [],
  errors: [
    { row: 8, field: "guardian_name", reason: "is required for a patient under 18" },
    { row: 9, field: "phone", reason: "is not a valid phone number" },
  ],
  duplicates: [
    { row: 3, kind: "earlier_row", same_as_row: 2 },
    { row: 10, kind: "existing_patient", matches: 1 },
    { row: 11, kind: "already_registered", same_as_row: 2 },
  ],
  errors_truncated: false,
  duplicates_truncated: false,
  ...overrides,
});

const csv = (name = "patients.csv", text = "name,phone,sex,dob_or_age,guardian_name,language\nA,9000000001,F,30,,en\n") =>
  new File([text], name, { type: "text/csv" });

function renderImport() {
  return render(
    <SessionProvider>
      <PatientImport clinicId={CLINIC_A} />
    </SessionProvider>,
  );
}

async function pick(file: File) {
  fireEvent.change(await screen.findByLabelText("CSV file"), { target: { files: [file] } });
}

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  vi.restoreAllMocks();
});

describe("ops patient import (M9-P3, FR-OPS-02)", () => {
  it("checks the file first, shows each row's outcome, then imports and names the codes", async () => {
    const api = mockApi({
      ...base,
      [IMPORT]: (call) =>
        call.search.get("dry_run") === "true"
          ? json(200, report())
          : json(200, report({ dry_run: false, imported: 7, codes: ["SC-0021", "SC-0022", "SC-0023", "SC-0024", "SC-0025", "SC-0026", "SC-0027"] })),
    });
    renderImport();

    expect(await screen.findByRole("heading", { name: "Import patients" })).toBeInTheDocument();
    expect(screen.getByText(/Sample Clinic\. Check the clinic’s patient list first/)).toBeInTheDocument();
    const check = screen.getByRole("button", { name: "Check file" });
    expect(check).toBeDisabled();

    await pick(csv());
    fireEvent.click(check);

    expect(await screen.findByRole("heading", { name: "Check result" })).toBeInTheDocument();
    const [call] = api.calls.filter((c) => `${c.method} ${c.path}` === IMPORT);
    expect(call?.search.get("dry_run")).toBe("true");
    expect(call?.headers.get("content-type")).toBe("text/csv");
    expect(call?.headers.get("x-csrf-token")).toBe("csrf-token");

    expect(screen.getByText("7 patients ready, 2 rows with a problem")).toBeInTheDocument();
    const strip = screen.getByRole("list", { name: "The file, row by row" });
    expect(within(strip).getByText("Ready to import").parentElement?.parentElement).toHaveTextContent("7");
    const problems = screen.getByRole("table", { name: /Rows with a problem/ });
    expect(within(problems).getByRole("row", { name: /8 Guardian Required for a patient under 18\./ })).toBeInTheDocument();
    expect(within(problems).getByRole("row", { name: /9 Phone Not a valid phone number\./ })).toBeInTheDocument();
    const shared = screen.getByRole("table", { name: "Will be imported, with a phone already in use" });
    expect(within(shared).getByText(/Same phone as row 2/)).toBeInTheDocument();
    expect(within(shared).getByText(/1 patient in the clinic already uses this phone/)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Left out as already registered" })).toHaveTextContent("same name and phone as row 2");

    fireEvent.click(screen.getByRole("button", { name: "Import 7 patients" }));
    expect(await screen.findByText("Imported 7 patients into Sample Clinic")).toBeInTheDocument();
    expect(screen.getByText(/Codes SC-0021 to SC-0027/)).toBeInTheDocument();
    expect(screen.getByText(/3 rows left out \(2 with a problem, 1 already registered\)/)).toBeInTheDocument();
    expect(api.calls.filter((c) => `${c.method} ${c.path}` === IMPORT).at(-1)?.search.get("dry_run")).toBe("false");
    expect(screen.getByRole("link", { name: "Back to clinics" })).toHaveAttribute("href", "/ops");
  });

  it("refuses a file that is not a CSV or is over 2 MB before sending anything", async () => {
    const api = mockApi({ ...base, [IMPORT]: () => json(200, report()) });
    renderImport();

    await pick(csv("patients.xlsx"));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose a .csv file");
    expect(screen.getByRole("button", { name: "Check file" })).toBeDisabled();

    const big = csv();
    Object.defineProperty(big, "size", { value: 2 * 1024 * 1024 + 1 });
    await pick(big);
    expect(screen.getByRole("alert")).toHaveTextContent("over 2 MB");
    expect(api.count(IMPORT)).toBe(0);
  });

  it("says why the whole file cannot be read, with the API's reasons", async () => {
    mockApi({
      ...base,
      [IMPORT]: () =>
        apiError(422, "PAT_IMPORT_INVALID", "The import file cannot be read.", {}, { problems: ["missing columns: dob_or_age"] }),
    });
    renderImport();
    await pick(csv());
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The file cannot be read");
    expect(alert).toHaveTextContent("missing columns: dob_or_age");
    expect(alert).toHaveTextContent("Ref: test-ref");
  });

  it("explains a file the server found too large", async () => {
    mockApi({ ...base, [IMPORT]: () => apiError(413, "REQ_REQUEST_ENTITY_TOO_LARGE", "The data value transmitted exceeds the capacity limit.") });
    renderImport();
    await pick(csv());
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The file is over 2 MB");
  });

  it("offers nothing to import when every row is left out, and a new file clears the result", async () => {
    mockApi({ ...base, [IMPORT]: () => json(200, report({ valid: 3, invalid: 7, already_registered: 3, duplicates: [], errors: [] })) });
    renderImport();
    await pick(csv());
    fireEvent.click(screen.getByRole("button", { name: "Check file" }));

    expect(await screen.findByText("No rows can be imported")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import 0 patients" })).toBeDisabled();

    await pick(csv("other.csv"));
    await waitFor(() => expect(screen.queryByRole("heading", { name: "Check result" })).not.toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Check file" })).toBeEnabled();
  });
});

describe("import report words", () => {
  it("counts what would be imported and describes each flagged row without saying who", () => {
    expect(importable(report())).toBe(7);
    expect(duplicateText({ row: 4, kind: "existing_patient", matches: 3 })).toBe(
      "Will be imported. 3 patients in the clinic already use this phone (often family); the desk can check at the next visit.",
    );
    expect(duplicateText({ row: 5, kind: "already_registered" })).toMatch(/already registered/);
    expect(codeRange(["A-1"])).toBe("A-1");
    expect(codeRange(["A-1", "A-2", "A-3"])).toBe("A-1 to A-3");
    expect(fileProblem(csv("list.CSV"))).toBeUndefined();
    expect(fileProblem(new File([], "empty.csv"))).toBe("This file is empty.");
    expect(problemText({ row: 8, field: "guardian_name", reason: "is required for a patient under 18" })).toBe(
      "Required for a patient under 18.",
    );
  });
});
