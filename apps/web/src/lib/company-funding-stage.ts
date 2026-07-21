const FUNDING_STAGE_LABELS: Readonly<Record<string, string>> = {
  seed: "Seed",
  series_a: "Series A",
  series_b: "Series B",
  series_c_plus: "Series C+",
  mezzanine: "Mezzanine",
  public: "Public",
  mature: "Mature",
  unknown: "Unknown",
};

const FUNDING_STAGE_SHORT_LABELS: Readonly<Record<string, string>> = {
  seed: "Seed",
  series_a: "A",
  series_b: "B",
  series_c_plus: "C+",
  mezzanine: "Mezz",
  public: "Public",
  mature: "Mature",
  unknown: "?",
};

export interface FundingStageOption {
  value: string;
  label: string;
}

export const FUNDING_STAGE_OPTIONS: ReadonlyArray<FundingStageOption> = [
  { value: "seed", label: "Seed" },
  { value: "series_a", label: "Series A" },
  { value: "series_b", label: "Series B" },
  { value: "series_c_plus", label: "Series C+" },
  { value: "mezzanine", label: "Mezzanine" },
  { value: "public", label: "Public" },
  { value: "mature", label: "Mature" },
];

export function formatFundingStage(
  stage: string | null | undefined,
): string {
  if (stage === null || stage === undefined || stage.trim() === "") {
    return "—";
  }
  const normalized: string = stage.trim().toLowerCase();
  return FUNDING_STAGE_LABELS[normalized] ?? stage;
}

export function shortFundingStage(
  stage: string | null | undefined,
): string {
  if (stage === null || stage === undefined || stage.trim() === "") {
    return "—";
  }
  const normalized: string = stage.trim().toLowerCase();
  return FUNDING_STAGE_SHORT_LABELS[normalized] ?? stage;
}
