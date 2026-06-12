import { useEffect, useRef } from "react";

import { MINE_SHARER_KEY, type TargetScope } from "@/components/target-selection/types";

export function useDefaultTrustScope(
  scope: TargetScope,
  availableSharers: ReadonlyArray<string>,
  onScopeChange: (scope: TargetScope) => void,
): void {
  const initializedRef = useRef<boolean>(false);

  useEffect(() => {
    if (initializedRef.current || availableSharers.length === 0) {
      return;
    }

    const isDefaultMineOnly: boolean =
      scope.sharerNames.size === 1 && scope.sharerNames.has(MINE_SHARER_KEY);
    if (!isDefaultMineOnly) {
      initializedRef.current = true;
      return;
    }

    initializedRef.current = true;
    onScopeChange({
      ...scope,
      sharerNames: new Set<string>([MINE_SHARER_KEY, ...availableSharers]),
    });
  }, [availableSharers, onScopeChange, scope]);
}
