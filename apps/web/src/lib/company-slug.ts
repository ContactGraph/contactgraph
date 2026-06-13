/** URL slug for public company pages — must match backend company_slug(). */

const NON_SLUG_CHARS_RE: RegExp = /[^a-z0-9]+/g;

export function companySlug(name: string): string {
  const normalized: string = name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  const slug: string = normalized.replace(NON_SLUG_CHARS_RE, "-").replace(/^-|-$/g, "");
  return slug.length > 0 ? slug : "company";
}

export function companyPageHref(slug: string): string {
  return `/companies/${slug}`;
}

export function companyListPageHref(categorySlug: string): string {
  return `/company-lists/${categorySlug}`;
}
