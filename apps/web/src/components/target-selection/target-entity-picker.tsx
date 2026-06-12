"use client";

import type { TargetSelectionConfig } from "./target-selection-config";
import { TargetOrgPicker } from "./target-org-picker";
import type { TargetOrgPickerProps } from "./target-org-picker";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

type TargetEntityPickerProps = TargetOrgPickerProps & {
  config: TargetSelectionConfig;
};

/**
 * Routes to the correct entity picker for a target-selection flow.
 * Jobs uses the org picker today; Investors will add a person picker when
 * person lists land on the backend.
 */
export function TargetEntityPicker({
  config,
  ...orgPickerProps
}: TargetEntityPickerProps) {
  if (config.entityType === "org") {
    return <TargetOrgPicker {...orgPickerProps} config={config} />;
  }

  return (
    <Sheet open={orgPickerProps.open} onOpenChange={orgPickerProps.onOpenChange}>
      <SheetContent className="sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{config.title}</SheetTitle>
          <SheetDescription>
            {config.description} Person-list selection is not implemented yet.
          </SheetDescription>
        </SheetHeader>
      </SheetContent>
    </Sheet>
  );
}
