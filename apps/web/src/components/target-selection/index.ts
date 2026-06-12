import type { TargetSelectionConfig } from "./target-selection-config";

export {
  INVESTOR_TARGET_SELECTION_CONFIG,
  JOB_TARGET_SELECTION_CONFIG,
} from "./target-selection-config";
export type { TargetEntityType, TargetSelectionConfig } from "./target-selection-config";

export { filterOrgsByScope, orgMatchesSearch, orgMatchesSharerScope } from "./filter-orgs-by-scope";
export {
  INDUSTRY_SCOPE_PRESETS,
  presetIdsFromTags,
  presetTagsForSelection,
} from "./industry-scope-presets";
export type { IndustryScopePreset } from "./industry-scope-presets";

export { JobTargetCompaniesCard } from "./job-target-companies-card";
export { TargetOrgPicker, useTargetOrgPickerScope } from "./target-org-picker";
export { TargetScopePanel } from "./target-scope-panel";
export {
  defaultTargetScope,
  MINE_SHARER_KEY,
  targetScopeFromPayload,
  targetScopeToPayload,
  targetScopesEqual,
} from "./types";
export type { TargetScope, TargetScopePayload } from "./types";
export { useOrgListMembership } from "./use-org-list-membership";
export type { UseOrgListMembershipResult } from "./use-org-list-membership";

export { TargetEntityPicker } from "./target-entity-picker";

export function isOrgTargetConfig(
  config: TargetSelectionConfig,
): config is TargetSelectionConfig & { entityType: "org" } {
  return config.entityType === "org";
}

export function isPersonTargetConfig(
  config: TargetSelectionConfig,
): config is TargetSelectionConfig & { entityType: "person" } {
  return config.entityType === "person";
}
