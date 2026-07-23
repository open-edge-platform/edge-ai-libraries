import { useCallback, useState } from "react";
import {
  api,
  useLazyGetModelDownloadJobStatusQuery,
  useStartModelDownloadMutation,
} from "@/api/api.generated.ts";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { useAppDispatch } from "@/store/hooks";
import { toast } from "sonner";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";
import { formatErrorMessage } from "@/lib/utils.ts";

export const useModelInstall = () => {
  const dispatch = useAppDispatch();
  const { execute: runInstallation } = useAsyncJob({
    asyncJobHook: useStartModelDownloadMutation,
    multiple: true,
    pollingInterval: 2000,
    statusCheckHook: useLazyGetModelDownloadJobStatusQuery,
    onJobComplete: useCallback(() => {
      dispatch(api.util.invalidateTags(["models"]));
    }, [dispatch]),
  });

  const [pendingDownloads, setPendingDownloads] = useState<ReadonlySet<string>>(
    () => new Set(),
  );

  const installModels = useCallback(
    async (names: readonly string[]) => {
      if (names.length === 0) return;

      setPendingDownloads((prev) => {
        const next = new Set(prev);
        for (const n of names) next.add(n);
        return next;
      });

      try {
        const result = await runInstallation({
          modelDownloadRequest: { names: [...names] },
        });

        if (result.completed.length > 0) {
          toast.success(
            result.completed.length === 1
              ? "Model installed successfully."
              : `${result.completed.length} models installed successfully.`,
          );
        }

        if (result.failed.length > 0 || result.rejected.length > 0) {
          const messages = [
            ...result.rejected.map((r) => `${r.name}: ${r.message}`),
            ...result.failed.map(
              (f) => `${f.model_name}: ${formatErrorMessage(f.details)}`,
            ),
          ];
          toast.error(
            messages.length === 1 ? messages[0] : messages.join("\n"),
          );
        }
      } catch (error) {
        if (isAsyncJobError(error)) {
          handleAsyncJobError(error, "Model installation");
        } else {
          handleApiError(error, "Failed to install model");
        }
        console.error("Failed to install model:", error);
      } finally {
        setPendingDownloads((prev) => {
          const next = new Set(prev);
          for (const n of names) next.delete(n);
          return next;
        });
      }
    },
    [runInstallation],
  );

  const installModel = useCallback(
    async (name: string) => {
      await installModels([name]);
    },
    [installModels],
  );

  const isPending = useCallback(
    (name: string | null | undefined) =>
      typeof name === "string" && pendingDownloads.has(name),
    [pendingDownloads],
  );

  return {
    pendingDownloads,
    installModels,
    installModel,
    isPending,
  };
};
