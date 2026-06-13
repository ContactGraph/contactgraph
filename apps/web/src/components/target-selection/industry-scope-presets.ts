export interface IndustryScopePreset {
  id: string;
  label: string;
  tags: readonly string[];
}

/** Human-friendly industry chips mapped to org category tags. */
export const INDUSTRY_SCOPE_PRESETS: readonly IndustryScopePreset[] = [
  { id: "technology", label: "Technology", tags: ["naics:51"] },
  { id: "healthcare", label: "Healthcare", tags: ["naics:62"] },
  {
    id: "financial",
    label: "Financial Services",
    tags: ["naics:52", "venture_capital"],
  },
  { id: "professional", label: "Professional Services", tags: ["naics:54"] },
  { id: "education", label: "Education", tags: ["naics:61"] },
  { id: "retail", label: "Retail", tags: ["naics:44"] },
  { id: "manufacturing", label: "Manufacturing", tags: ["naics:31"] },
  { id: "government", label: "Government", tags: ["naics:92"] },
  { id: "nonprofit", label: "Nonprofit", tags: ["nonprofit"] },
  { id: "legal", label: "Legal", tags: ["legal"] },
] as const;

export function presetTagsForSelection(
  selectedPresetIds: ReadonlySet<string>,
): ReadonlySet<string> {
  const tags = new Set<string>();
  for (const preset of INDUSTRY_SCOPE_PRESETS) {
    if (selectedPresetIds.has(preset.id)) {
      for (const tag of preset.tags) {
        tags.add(tag);
      }
    }
  }
  return tags;
}

export function presetIdsFromTags(
  industryTags: ReadonlySet<string>,
): ReadonlySet<string> {
  const ids = new Set<string>();
  for (const preset of INDUSTRY_SCOPE_PRESETS) {
    if (preset.tags.some((tag) => industryTags.has(tag))) {
      ids.add(preset.id);
    }
  }
  return ids;
}
