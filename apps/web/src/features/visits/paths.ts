/** The consultation screen of a visit (M4-P6). The URL carries the visit ID only, never a name. */
export const visitPath = (visitId: string) => `/visits/${encodeURIComponent(visitId)}`;
