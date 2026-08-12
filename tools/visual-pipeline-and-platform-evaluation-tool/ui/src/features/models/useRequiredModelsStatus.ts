import { useCallback, useEffect, useMemo, useState } from "react";
import {
  useCheckModelsStatusMutation,
  type ModelInstallStatus,
} from "@/api/api.generated.ts";
import { handleApiError } from "@/lib/apiUtils.ts";
import { normalizeModelDisplayName } from "@/features/models/modelNames.ts";

export type PipelineModelStatusItem = {
  model: string;
  installStatus: ModelInstallStatus;
};

type UseRequiredModelsStatusOptions = {
  autoOpenDialog?: boolean;
  skip?: boolean;
  errorMessage?: string;
};

export const useRequiredModelsStatus = (
  requiredModels: readonly string[],
  {
    autoOpenDialog = true,
    skip = false,
    errorMessage = "Failed to check required models",
  }: UseRequiredModelsStatusOptions = {},
) => {
  const [checkModelsStatus] = useCheckModelsStatusMutation();
  const [modelStatuses, setModelStatuses] = useState<PipelineModelStatusItem[]>(
    [],
  );
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const modelsKey = useMemo(
    () =>
      JSON.stringify(
        [...new Set(requiredModels.map(normalizeModelDisplayName))]
          .filter(Boolean)
          .sort(),
      ),
    [requiredModels],
  );

  const models = useMemo(() => JSON.parse(modelsKey) as string[], [modelsKey]);

  const refresh = useCallback(async () => {
    if (skip || models.length === 0) {
      setModelStatuses([]);
      setIsDialogOpen(false);
      return;
    }

    try {
      const response = await checkModelsStatus({
        modelCheckStatusRequest: { display_names: models },
      }).unwrap();

      const installStatusByModel = new Map<string, ModelInstallStatus>();
      response.models?.forEach((model) => {
        installStatusByModel.set(model.display_name, model.install_status);
        installStatusByModel.set(model.name, model.install_status);
      });

      const statuses: PipelineModelStatusItem[] = models.map((model) => ({
        model,
        installStatus: installStatusByModel.get(model) ?? "not_installed",
      }));

      setModelStatuses(statuses);

      if (autoOpenDialog) {
        setIsDialogOpen(
          statuses.some((item) => item.installStatus !== "installed"),
        );
      }
    } catch (error) {
      handleApiError(error, errorMessage);
    }
  }, [skip, models, checkModelsStatus, autoOpenDialog, errorMessage]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const statusByModel = useMemo(() => {
    const map = new Map<string, ModelInstallStatus>();
    modelStatuses.forEach((item) => map.set(item.model, item.installStatus));
    return map;
  }, [modelStatuses]);

  const missingModels = useMemo(
    () => modelStatuses.filter((item) => item.installStatus !== "installed"),
    [modelStatuses],
  );

  const getModelStatus = useCallback(
    (model: string): ModelInstallStatus | undefined =>
      statusByModel.get(normalizeModelDisplayName(model)),
    [statusByModel],
  );

  return {
    modelStatuses,
    missingModels,
    hasMissingModels: missingModels.length > 0,
    getModelStatus,
    isDialogOpen,
    setIsDialogOpen,
    openDialog: useCallback(() => setIsDialogOpen(true), []),
    refresh,
  };
};
