"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { toast } from "sonner";

import type {
  CreateOrgListResult,
  ListOrgListsResult,
  ModifyOrgListMembershipResult,
  OrgListSummary,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

function findOrgListByName(
  orgLists: ReadonlyArray<OrgListSummary>,
  listName: string,
): OrgListSummary | undefined {
  return orgLists.find((list) => list.name === listName);
}

export interface UseOrgListMembershipResult {
  orgLists: OrgListSummary[];
  targetList: OrgListSummary | undefined;
  selectedOrgIds: ReadonlySet<string>;
  selectedCount: number;
  isPending: boolean;
  toggleOrg: (orgId: string, isSelected: boolean) => void;
  bulkUpdate: (orgIds: string[], action: "add" | "remove") => void;
  bulkUpdateAsync: (orgIds: string[], action: "add" | "remove") => Promise<void>;
  replaceSelection: (orgIds: string[]) => Promise<void>;
}

export function useOrgListMembership(listName: string): UseOrgListMembershipResult {
  const queryClient = useQueryClient();

  const orgListsQuery = useQuery({
    queryKey: ["org-lists"],
    queryFn: () => proxyPost<ListOrgListsResult>("list-org-lists"),
  });

  const orgLists: OrgListSummary[] = orgListsQuery.data?.lists ?? [];
  const targetList: OrgListSummary | undefined = findOrgListByName(
    orgLists,
    listName,
  );
  const selectedOrgIds: ReadonlySet<string> = useMemo(
    () => new Set(targetList?.org_ids ?? []),
    [targetList?.org_ids],
  );
  const selectedCount: number = targetList?.org_count ?? 0;

  const invalidateOrgLists = useCallback(async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: ["org-lists"] });
  }, [queryClient]);

  const ensureListId = useCallback(async (): Promise<string> => {
    const existingList: OrgListSummary | undefined = findOrgListByName(
      orgListsQuery.data?.lists ?? [],
      listName,
    );
    if (existingList !== undefined) {
      return existingList.list_id;
    }
    const result: CreateOrgListResult = await proxyPost<CreateOrgListResult>(
      "create-org-list",
      { name: listName },
    );
    await invalidateOrgLists();
    return result.list_id;
  }, [invalidateOrgLists, listName, orgListsQuery.data?.lists]);

  const applyOptimisticUpdate = useCallback(
    (orgIds: string[], action: "add" | "remove"): ListOrgListsResult | undefined => {
      const previous: ListOrgListsResult | undefined =
        queryClient.getQueryData<ListOrgListsResult>(["org-lists"]);
      queryClient.setQueryData<ListOrgListsResult>(["org-lists"], (old) => {
        if (old === undefined) {
          return old;
        }
        return {
          ...old,
          lists: old.lists.map((list) => {
            if (list.name !== listName) {
              return list;
            }
            const currentIds = new Set(list.org_ids);
            if (action === "add") {
              for (const id of orgIds) {
                currentIds.add(id);
              }
            } else {
              for (const id of orgIds) {
                currentIds.delete(id);
              }
            }
            return {
              ...list,
              org_ids: [...currentIds],
              org_count: currentIds.size,
            };
          }),
        };
      });
      return previous;
    },
    [listName, queryClient],
  );

  const membershipMutation = useMutation({
    mutationFn: async ({
      orgIds,
      action,
    }: {
      orgIds: string[];
      action: "add" | "remove";
    }) => {
      if (orgIds.length === 0) {
        return null;
      }
      if (action === "remove") {
        const list: OrgListSummary | undefined = findOrgListByName(
          orgListsQuery.data?.lists ?? [],
          listName,
        );
        if (list === undefined) {
          return null;
        }
        return proxyPost<ModifyOrgListMembershipResult>("remove-orgs-from-list", {
          list_id: list.list_id,
          org_ids: orgIds,
        });
      }
      const listId: string = await ensureListId();
      return proxyPost<ModifyOrgListMembershipResult>("add-orgs-to-list", {
        list_id: listId,
        org_ids: orgIds,
      });
    },
    onMutate: async ({ orgIds, action }) => {
      await queryClient.cancelQueries({ queryKey: ["org-lists"] });
      const previous = applyOptimisticUpdate(orgIds, action);
      return { previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous !== undefined) {
        queryClient.setQueryData(["org-lists"], context.previous);
      }
      toast.error("Failed to update selection");
    },
    onSettled: async () => {
      await invalidateOrgLists();
    },
  });

  const toggleOrg = useCallback(
    (orgId: string, isSelected: boolean): void => {
      membershipMutation.mutate({
        orgIds: [orgId],
        action: isSelected ? "remove" : "add",
      });
    },
    [membershipMutation],
  );

  const bulkUpdate = useCallback(
    (orgIds: string[], action: "add" | "remove"): void => {
      membershipMutation.mutate({ orgIds, action });
    },
    [membershipMutation],
  );

  const bulkUpdateAsync = useCallback(
    async (orgIds: string[], action: "add" | "remove"): Promise<void> => {
      await membershipMutation.mutateAsync({ orgIds, action });
    },
    [membershipMutation],
  );

  const replaceSelection = useCallback(
    async (orgIds: string[]): Promise<void> => {
      const listId: string = await ensureListId();
      const currentIds: string[] = targetList?.org_ids ?? [];
      const nextIds = new Set(orgIds);
      const toRemove: string[] = currentIds.filter((id) => !nextIds.has(id));
      const toAdd: string[] = orgIds.filter((id) => !selectedOrgIds.has(id));

      if (toRemove.length > 0) {
        await proxyPost<ModifyOrgListMembershipResult>("remove-orgs-from-list", {
          list_id: listId,
          org_ids: toRemove,
        });
      }
      if (toAdd.length > 0) {
        await proxyPost<ModifyOrgListMembershipResult>("add-orgs-to-list", {
          list_id: listId,
          org_ids: toAdd,
        });
      }
      await invalidateOrgLists();
    },
    [ensureListId, invalidateOrgLists, selectedOrgIds, targetList?.org_ids],
  );

  return {
    orgLists,
    targetList,
    selectedOrgIds,
    selectedCount,
    isPending: membershipMutation.isPending,
    toggleOrg,
    bulkUpdate,
    bulkUpdateAsync,
    replaceSelection,
  };
}
