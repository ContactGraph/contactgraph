import { JOB_PROSPECTS_LIST_NAME } from "@/lib/setup-utils";

export type TargetEntityType = "org" | "person";

export interface TargetSelectionConfig {
  entityType: TargetEntityType;
  listName: string;
  title: string;
  description: string;
  manageButtonLabel: string;
  graphLinkHref: string;
  graphLinkLabel: string;
}

export const JOB_TARGET_SELECTION_CONFIG: TargetSelectionConfig = {
  entityType: "org",
  listName: JOB_PROSPECTS_LIST_NAME,
  title: "Select organizations for jobs",
  description: "Companies in your network you'd like to work at.",
  manageButtonLabel: "Manage companies",
  graphLinkHref: "/graph?tab=organizations",
  graphLinkLabel: "Open full table in Graph",
};

/** Reserved for the future Investors tab — person lists not yet implemented. */
export const INVESTOR_TARGET_SELECTION_CONFIG: TargetSelectionConfig = {
  entityType: "person",
  listName: "Investor Targets",
  title: "Select investors for intros",
  description: "Investors in your network you'd like warm intros to.",
  manageButtonLabel: "Manage investors",
  graphLinkHref: "/graph?tab=people",
  graphLinkLabel: "Open full table in Graph",
};
