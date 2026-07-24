import type { ModelInstallStatus } from "@/api/api.generated";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useModelInstall } from "@/features/models/useModelInstall";
import { Download, Loader2 } from "lucide-react";
import { useMemo } from "react";
import { useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type PipelineModelsRequiredDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  models: PipelineModelStatusItem[];
  onModelsChanged?: () => void | Promise<void>;
};

export type PipelineModelStatusItem = {
  model: string;
  installStatus: ModelInstallStatus;
};

const formatInstallStatus = (status: ModelInstallStatus): string =>
  status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const statusBadgeVariant = (
  status: ModelInstallStatus,
): "default" | "secondary" | "destructive" | "outline" => {
  if (status === "installed") return "default";
  if (status === "installing") return "secondary";
  if (status === "failed") return "destructive";
  return "outline";
};

const toModelLabel = (value: string): string => value.split("/").pop() || value;

export const PipelineModelsRequiredDialog = ({
  open,
  onOpenChange,
  models,
  onModelsChanged,
}: PipelineModelsRequiredDialogProps) => {
  const availableModels = useAppSelector(selectModels);
  const { installModel, isPending } = useModelInstall();

  const modelNameByDisplayName = useMemo(() => {
    const map = new Map<string, string>();
    availableModels.forEach((model) => {
      map.set(model.display_name, model.name);
      map.set(model.name, model.name);
    });
    return map;
  }, [availableModels]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl" showCloseButton>
        <DialogHeader>
          <DialogTitle>Required models are missing</DialogTitle>
          <DialogDescription>
            This pipeline uses one or more models that are not installed.
          </DialogDescription>
        </DialogHeader>

        <div className="max-h-80 overflow-y-auto rounded border">
          <div className="divide-y">
            {models.map((item) => {
              const isInstalled = item.installStatus === "installed";
              const installableModelName = modelNameByDisplayName.get(
                item.model,
              );
              const canInstall =
                !isInstalled &&
                item.installStatus !== "installing" &&
                Boolean(installableModelName);
              const pending = isPending(installableModelName);

              return (
                <div
                  key={item.model}
                  className="flex items-center justify-between gap-3 px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium" title={item.model}>
                      {toModelLabel(item.model)}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge variant={statusBadgeVariant(item.installStatus)}>
                      {formatInstallStatus(item.installStatus)}
                    </Badge>
                    {!isInstalled && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!canInstall || pending}
                        onClick={async () => {
                          if (!installableModelName) {
                            return;
                          }

                          await installModel(installableModelName);
                          await onModelsChanged?.();
                        }}
                      >
                        {pending ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Download className="size-4" />
                        )}
                        Download
                      </Button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button onClick={() => onOpenChange(false)}>Continue</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
