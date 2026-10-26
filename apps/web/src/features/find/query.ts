import type { FindQuery } from "./FindPage";

export type Search = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value)?.trim() ?? "";
}

/** The form's fields from the URL (M6c-P6, spec discovery R1); each one bounded. */
export function readQuery(search: Search): FindQuery {
  return {
    kind: one(search.type) === "clinics" ? "clinics" : "doctors",
    q: one(search.q).slice(0, 100),
    where: one(search.where).slice(0, 100),
    specialty: one(search.specialty).slice(0, 100),
    language: one(search.language).slice(0, 40),
    available: one(search.available) === "true",
  };
}

/** R3: `where` is a PIN code when it is six digits, a city otherwise; plus the other filters. */
export function apiFilters(query: FindQuery): Record<string, string> {
  const filters: Record<string, string> = {};
  if (query.q !== "") filters.q = query.q;
  if (/^[1-9][0-9]{5}$/.test(query.where)) filters.pincode = query.where;
  else if (query.where !== "") filters.city = query.where;
  if (query.specialty !== "") filters.specialty = query.specialty;
  if (query.language !== "") filters.language = query.language;
  if (query.available) filters.available = "true";
  return filters;
}
