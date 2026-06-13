import type { MetadataRoute } from "next";

import { getAllAlternativesSlugs } from "@/app/(marketing)/alternatives/data";
import {
  fetchCategoryCompanies,
  getAllCategorySlugs,
} from "@/app/(marketing)/company-lists/data";
import { getAllGuideSlugs } from "@/app/(marketing)/guides/data";
import { companyPageHref } from "@/lib/company-slug";
import { SITE_URL } from "@/lib/site-url";

export const revalidate = 3600;

const STATIC_ROUTES: readonly {
  readonly path: string;
  readonly changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"];
  readonly priority: number;
}[] = [
  { path: "/", changeFrequency: "weekly", priority: 1 },
  { path: "/about", changeFrequency: "monthly", priority: 0.7 },
  { path: "/manifesto", changeFrequency: "monthly", priority: 0.6 },
  { path: "/resources", changeFrequency: "weekly", priority: 0.9 },
  { path: "/privacy", changeFrequency: "yearly", priority: 0.3 },
  { path: "/terms", changeFrequency: "yearly", priority: 0.3 },
  { path: "/join", changeFrequency: "monthly", priority: 0.5 },
] as const;

function staticEntry(
  path: string,
  changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"],
  priority: number,
): MetadataRoute.Sitemap[number] {
  return {
    url: `${SITE_URL}${path}`,
    lastModified: new Date(),
    changeFrequency,
    priority,
  };
}

async function fetchCompanySlugs(): Promise<readonly string[]> {
  const categorySlugs: readonly string[] = getAllCategorySlugs();
  const results = await Promise.all(
    categorySlugs.map((slug: string) => fetchCategoryCompanies(slug)),
  );

  const slugSet: Set<string> = new Set<string>();
  for (const result of results) {
    for (const company of result.companies) {
      slugSet.add(company.slug);
    }
  }

  return [...slugSet];
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now: Date = new Date();

  const staticPages: MetadataRoute.Sitemap = STATIC_ROUTES.map(
    (route: (typeof STATIC_ROUTES)[number]) =>
      staticEntry(route.path, route.changeFrequency, route.priority),
  );

  const guidePages: MetadataRoute.Sitemap = getAllGuideSlugs().map(
    (slug: string) => ({
      url: `${SITE_URL}/guides/${slug}`,
      lastModified: now,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    }),
  );

  const alternativesPages: MetadataRoute.Sitemap = getAllAlternativesSlugs().map(
    (slug: string) => ({
      url: `${SITE_URL}/alternatives/${slug}`,
      lastModified: now,
      changeFrequency: "monthly" as const,
      priority: 0.7,
    }),
  );

  const categoryPages: MetadataRoute.Sitemap = getAllCategorySlugs().map(
    (slug: string) => ({
      url: `${SITE_URL}/company-lists/${slug}`,
      lastModified: now,
      changeFrequency: "daily" as const,
      priority: 0.8,
    }),
  );

  const companySlugs: readonly string[] = await fetchCompanySlugs();
  const companyPages: MetadataRoute.Sitemap = companySlugs.map((slug: string) => ({
    url: `${SITE_URL}${companyPageHref(slug)}`,
    lastModified: now,
    changeFrequency: "daily" as const,
    priority: 0.6,
  }));

  return [
    ...staticPages,
    ...guidePages,
    ...alternativesPages,
    ...categoryPages,
    ...companyPages,
  ];
}
