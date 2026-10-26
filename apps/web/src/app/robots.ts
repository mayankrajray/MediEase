import type { MetadataRoute } from "next";

import { apiGet } from "@/lib/api/client";

export const revalidate = 3600;

/**
 * robots.txt (M6c-P5; FR-DIS-06): crawlers may read the public clinic and doctor pages (each page
 * still says `noindex` unless the clinic is discoverable and has not opted out), the directory
 * search and the landing and apply pages; never a signed-in area, a patient link or an API path.
 */
export default async function robots(): Promise<MetadataRoute.Robots> {
  let base: string | undefined;
  try {
    base = (await apiGet("/api/v1/public/sitemap")).data.base_url;
  } catch {
    base = undefined;
  }
  return {
    rules: {
      userAgent: "*",
      allow: ["/$", "/c/", "/find", "/apply$"],
      disallow: ["/api/", "/p/", "/q/", "/portal", "/ops", "/invite/", "/apply/confirm/", "/reset-password/"],
    },
    ...(base === undefined ? {} : { sitemap: `${base}/sitemap.xml` }),
  };
}
