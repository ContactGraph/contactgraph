export interface NetworkContactSummary {
  primaryContactName: string | null | undefined;
  contactCount: number | null | undefined;
  sharedPrimaryContactName?: string | null | undefined;
  sharedContactCount?: number | null | undefined;
  sharedPrimaryBridgeName?: string | null | undefined;
}

function normalizeCount(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function normalizeName(value: string | null | undefined): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed: string = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function formatOwnContacts(name: string, count: number): string {
  if (count === 1) {
    return name;
  }
  const othersCount: number = count - 1;
  return `${name} and ${othersCount} ${othersCount === 1 ? "other" : "others"}`;
}

function formatSharedContactsTable(name: string, count: number): string {
  if (count === 1) {
    return name;
  }
  const othersCount: number = count - 1;
  return `${name} + ${othersCount} ${othersCount === 1 ? "other" : "others"}`;
}

export function formatNetworkContactsLabel(
  summary: NetworkContactSummary,
): string {
  const ownCount: number = normalizeCount(summary.contactCount);
  const ownName: string | null = normalizeName(summary.primaryContactName);
  const sharedCount: number = normalizeCount(summary.sharedContactCount);
  const sharedName: string | null = normalizeName(summary.sharedPrimaryContactName);

  const ownPart: string | null =
    ownCount > 0 && ownName !== null ? formatOwnContacts(ownName, ownCount) : null;
  const sharedPart: string | null =
    sharedCount > 0 && sharedName !== null
      ? formatSharedContactsTable(sharedName, sharedCount)
      : null;

  if (ownPart !== null && sharedPart !== null) {
    return `${ownPart}, ${sharedPart}`;
  }
  if (ownPart !== null) {
    return ownPart;
  }
  if (sharedPart !== null) {
    return sharedPart;
  }
  return "—";
}
