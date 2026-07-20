const LINKEDIN_SIZE_BAND_LABELS: Readonly<Record<string, string>> = {
  "1-10": "1–10 employees",
  "11-50": "11–50 employees",
  "51-200": "51–200 employees",
  "201-500": "201–500 employees",
  "501-1000": "501–1,000 employees",
  "1001-5000": "1,001–5,000 employees",
  "5001-10000": "5,001–10,000 employees",
  "10001+": "10,001+ employees",
};

export interface CompanySizeOption {
  value: string;
  label: string;
}

export const COMPANY_SIZE_OPTIONS: ReadonlyArray<CompanySizeOption> = Object.entries(
  LINKEDIN_SIZE_BAND_LABELS,
).map(([value, label]): CompanySizeOption => ({ value, label }));

export function formatCompanySize(
  band: string | null | undefined,
  employeeCount: number | null | undefined = null,
): string {
  if (band === null || band === undefined || band.trim() === "") {
    return "—";
  }
  const normalized: string = band.trim().toLowerCase();
  const label: string = LINKEDIN_SIZE_BAND_LABELS[normalized] ?? band;
  if (employeeCount !== null && employeeCount !== undefined && employeeCount > 0) {
    return `${label} (~${employeeCount.toLocaleString()})`;
  }
  return label;
}
