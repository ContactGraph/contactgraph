"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type {
  NextStepsResult,
  SetJobInterestRequest,
  SetJobInterestResult,
  UpdateTaskStatusRequest,
  UpdateTaskStatusResult,
} from "@/lib/api-types";
import { proxyPost } from "@/lib/proxy-client";

export function useNextSteps() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["next-steps"],
    queryFn: () => proxyPost<NextStepsResult>("get-next-steps"),
  });

  const updateStatusMutation = useMutation({
    mutationFn: (body: UpdateTaskStatusRequest) =>
      proxyPost<UpdateTaskStatusResult>("update-task-status", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["next-steps"] });
    },
  });

  const setJobInterestMutation = useMutation({
    mutationFn: (body: SetJobInterestRequest) =>
      proxyPost<SetJobInterestResult>("set-job-interest", body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["next-steps"] });
      void queryClient.invalidateQueries({ queryKey: ["flat-jobs"] });
    },
  });

  return {
    ...query,
    updateTaskStatus: updateStatusMutation.mutateAsync,
    isUpdatingTask: updateStatusMutation.isPending,
    setJobInterest: setJobInterestMutation.mutateAsync,
    isSettingJobInterest: setJobInterestMutation.isPending,
  };
}
