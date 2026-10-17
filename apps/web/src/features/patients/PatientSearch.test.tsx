import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetRefreshState } from "@/lib/auth/refresh";
import { apiError, json, mockApi } from "@/test/api";
import { push, resetNavigation } from "@/test/navigation";

import { PatientResults } from "./PatientResults";
import { OTHER_ID, patient, renderInWorkspace, workspaceRoutes } from "./testing";

vi.mock("next/navigation", async () => (await import("@/test/navigation")).nextNavigationMock);

const rao = [
  patient({ full_name: "Arun Rao", code: "SC-0002", phone_e164: "+919000000101", age_years: 38, age_is_estimated: false }),
  patient({ id: OTHER_ID, full_name: "Asha Rao", code: "SC-0001", phone_e164: "+919000000101", age_years: 36, age_is_estimated: false }),
];

beforeEach(() => {
  resetNavigation();
  resetRefreshState();
  document.cookie = "me_csrf=csrf-token; path=/";
});

afterEach(() => {
  document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  window.localStorage.clear();
});

async function search() {
  renderInWorkspace(<PatientResults q="" />);
  return screen.findByRole("combobox", { name: "Find a patient" });
}

describe("patient search in the header (FR-PAT-04)", () => {
  it("spec §6: / focuses the search from anywhere, but not while typing in a field", async () => {
    mockApi(workspaceRoutes);
    const box = await search();
    await act(async () => {}); // the shortcut listener is added in an effect

    fireEvent.keyDown(document.body, { key: "/" });
    expect(box.isConnected).toBe(true);
    expect(document.activeElement).toBe(box);

    const other = document.createElement("input");
    document.body.append(other);
    other.focus();
    fireEvent.keyDown(other, { key: "/" });
    expect(other).toHaveFocus();
    other.remove();
  });

  it("FR-PAT-04, AC1: one lookup per pause in typing; matches show masked phones; arrows and Enter open one", async () => {
    const api = mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: rao }) });
    const box = await search();

    fireEvent.change(box, { target: { value: "90000" } });
    fireEvent.change(box, { target: { value: "90000 00101" } });

    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(2);
    const lookups = api.calls.filter((c) => c.path === "/api/v1/patients");
    expect(lookups.map((c) => c.search.get("q"))).toEqual(["90000 00101"]);
    expect(options[0]).toHaveTextContent("Arun Rao");
    expect(options[0]).toHaveTextContent("+91******0101");
    expect(screen.getByRole("listbox")).not.toHaveTextContent("+919000000101");

    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    expect(box).toHaveAttribute("aria-activedescendant", options[1]?.id);
    fireEvent.keyDown(box, { key: "Enter" });

    expect(push).toHaveBeenCalledWith(`/patients/${OTHER_ID}`);
    expect(box).toHaveValue("");
  });

  it("Enter with no match chosen opens the results page for the text", async () => {
    mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: rao }) });
    const box = await search();

    fireEvent.change(box, { target: { value: "rao" } });
    fireEvent.keyDown(box, { key: "Enter" });

    expect(push).toHaveBeenCalledWith("/patients?q=rao");
  });

  it("no match offers Register patient with the phone already filled in", async () => {
    mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: [] }) });
    const box = await search();

    fireEvent.change(box, { target: { value: "90000 00999" } });
    expect(await screen.findByText("No patient matches.")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("listbox").parentElement as HTMLElement).getByRole("button", { name: "Register patient" }));

    const dialog = await screen.findByRole("dialog", { name: "Register patient" });
    expect(within(dialog).getByLabelText(/^Phone/)).toHaveValue("90000 00999");
  });

  it("a failed lookup shows the API's message and Ref", async () => {
    mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => apiError(500, "SYS_INTERNAL", "Something went wrong.") });
    const box = await search();

    fireEvent.change(box, { target: { value: "asha" } });

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Something went wrong.");
    expect(alert).toHaveTextContent("Ref: test-ref");
  });

  it("Escape closes the list, and a second Escape clears the text", async () => {
    mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: rao }) });
    const box = await search();
    fireEvent.change(box, { target: { value: "rao" } });
    await screen.findAllByRole("option");

    fireEvent.keyDown(box, { key: "Escape" });
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    fireEvent.keyDown(box, { key: "Escape" });
    expect(box).toHaveValue("");
  });

  it("the header links to Patients for a role that manages patients", async () => {
    mockApi(workspaceRoutes);
    await search();
    expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("href", "/patients");
  });
});

describe("results page (/patients?q=)", () => {
  it("FR-PAT-04: lists the matches with links to their profiles and masked phones", async () => {
    const api = mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: rao }) });
    renderInWorkspace(<PatientResults q="rao" />);

    const table = await screen.findByRole("table", { name: "Patients matching “rao”" });
    expect(within(table).getByRole("link", { name: "Asha Rao" })).toHaveAttribute("href", `/patients/${OTHER_ID}`);
    expect(table).toHaveTextContent("+91******0101");
    expect(table).not.toHaveTextContent("+919000000101");
    expect(api.calls.find((c) => c.path === "/api/v1/patients")?.search.get("q")).toBe("rao");
  });

  it("says when nothing matches, and asks for a search when there is no text", async () => {
    mockApi({ ...workspaceRoutes, "GET /api/v1/patients": () => json(200, { items: [] }) });
    const { unmount } = renderInWorkspace(<PatientResults q="zzz" />);
    expect(await screen.findByText("No patient matches “zzz”.")).toBeInTheDocument();
    unmount();

    renderInWorkspace(<PatientResults q="" />);
    expect(await screen.findByText(/Find a patient with the search above/)).toBeInTheDocument();
  });

  it("an unreachable API offers Try again", async () => {
    let up = false;
    mockApi({
      ...workspaceRoutes,
      "GET /api/v1/patients": () => {
        if (!up) throw new TypeError("fetch failed");
        return json(200, { items: rao });
      },
    });
    renderInWorkspace(<PatientResults q="rao" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The API could not be reached.");

    up = true;
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByRole("table")).toBeInTheDocument());
  });
});
