import type { MetadataRoute } from "next";

import { apiGet } from "@/lib/api/client";

// Regenerated at most hourly; the API answer is cacheable for an hour too.
export const revalidate = 3600;

/**
 * sitemap.xml (M6c-P5; FR-DIS-06, spec R63): the public profiles of discoverable clinics that
 * have not opted out, as the API lists them. If the API cannot be reached the sitemap is empty
 * rather than an error, so a crawler retries later.
 */
export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  try {
    const { data } = await apiGet("/api/v1/public/sitemap");
    return data.items.map((item) => ({ url: item.loc, lastModified: item.lastmod, changeFrequency: "weekly" }));
  } catch {
    return [];
  }
}
