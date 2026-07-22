/** Labels for mechanical job seniority_level ordinals. */
export const SENIORITY_LEVEL_LABELS: Readonly<Record<number, string>> = {
  0: "Intern",
  1: "Entry",
  2: "Associate",
  3: "Mid",
  4: "Senior",
  5: "Staff / Principal",
  6: "Manager",
  7: "Director",
  8: "VP",
  9: "C-level",
};

export function formatSeniorityLevel(level: number | null | undefined): string {
  if (level === null || level === undefined) {
    return "";
  }
  return SENIORITY_LEVEL_LABELS[level] ?? `Level ${level}`;
}
