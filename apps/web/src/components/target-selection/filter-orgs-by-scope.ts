import type { OrgListItem } from "@/lib/api-types";

import { MINE_SHARER_KEY, type TargetScope } from "./types";

export function orgMatchesSharerScope(
  org: OrgListItem,
  sharerNames: ReadonlySet<string>,
): boolean {
  // Watched companies (list membership, no contacts) should always remain visible.
  const isWatchedOnly: boolean =
    org.contact_count === 0 && org.shared_contact_count === 0;

  if (sharerNames.size === 0) {
    return org.contact_count > 0 || isWatchedOnly;
  }

  const includeMine: boolean = sharerNames.has(MINE_SHARER_KEY);
  const includeShared: boolean = [...sharerNames].some(
    (name) => name !== MINE_SHARER_KEY && org.shared_from.includes(name),
  );

  if (includeMine && (org.contact_count > 0 || isWatchedOnly)) {
    return true;
  }
  return includeShared;
}

export function filterOrgsByScope(
  orgs: ReadonlyArray<OrgListItem>,
  scope: TargetScope,
): OrgListItem[] {
  let rows: OrgListItem[] = [...orgs];

  rows = rows.filter((org) => orgMatchesSharerScope(org, scope.sharerNames));

  if (scope.industryTags.size > 0) {
    rows = rows.filter((org) =>
      org.categories.some((tag) => scope.industryTags.has(tag)),
    );
  }

  if (scope.sizeBands.size > 0) {
    rows = rows.filter(
      (org) =>
        org.company_size_band !== null &&
        scope.sizeBands.has(org.company_size_band),
    );
  }

  return rows;
}

export function orgMatchesSearch(org: OrgListItem, query: string): boolean {
  const normalized: string = query.trim().toLowerCase();
  if (normalized.length === 0) {
    return true;
  }
  const haystack: string = [
    org.name,
    org.primary_domain,
    org.description,
    ...org.categories,
    ...org.shared_from,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalized);
}
