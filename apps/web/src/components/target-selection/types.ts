export const MINE_SHARER_KEY: "mine" = "mine";

export interface TargetScope {
  industryTags: ReadonlySet<string>;
  sharerNames: ReadonlySet<string>;
  sizeBands: ReadonlySet<string>;
}

export interface TargetScopePayload {
  industry_tags: string[];
  sharer_names: string[];
  size_bands: string[];
}

export function defaultTargetScope(): TargetScope {
  return {
    industryTags: new Set<string>(),
    sharerNames: new Set<string>([MINE_SHARER_KEY]),
    sizeBands: new Set<string>(),
  };
}

export function targetScopeFromPayload(
  payload: TargetScopePayload | null | undefined,
): TargetScope {
  if (payload === null || payload === undefined) {
    return defaultTargetScope();
  }
  return {
    industryTags: new Set(payload.industry_tags),
    sharerNames:
      payload.sharer_names.length > 0
        ? new Set(payload.sharer_names)
        : new Set<string>([MINE_SHARER_KEY]),
    sizeBands: new Set(payload.size_bands),
  };
}

export function targetScopeToPayload(scope: TargetScope): TargetScopePayload {
  return {
    industry_tags: [...scope.industryTags],
    sharer_names: [...scope.sharerNames],
    size_bands: [...scope.sizeBands],
  };
}

export function targetScopesEqual(
  left: TargetScope,
  right: TargetScope,
): boolean {
  return (
    setsEqual(left.industryTags, right.industryTags) &&
    setsEqual(left.sharerNames, right.sharerNames) &&
    setsEqual(left.sizeBands, right.sizeBands)
  );
}

function setsEqual(left: ReadonlySet<string>, right: ReadonlySet<string>): boolean {
  if (left.size !== right.size) {
    return false;
  }
  for (const value of left) {
    if (!right.has(value)) {
      return false;
    }
  }
  return true;
}
