import { Button } from "@/components/ui/button.tsx";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog.tsx";
import { ModelInstallStatusIndicator } from "@/features/models/ModelInstallStatusIndicator";
import { ModelInstallButtonSlot } from "@/features/models/ModelInstallButtonSlot";
import { LicenseAcknowledgementDialog } from "@/features/models/LicenseAcknowledgementDialog";
import { isGatedModel } from "@/features/models/modelNames.ts";
import { useModelInstall } from "@/features/models/useModelInstall.ts";
import type { PipelineModelStatusItem } from "@/features/models/useRequiredModelsStatus.ts";
import type { Model } from "@/api/api.generated.ts";
import { useAppSelector } from "@/store/hooks.ts";
import { selectModels } from "@/store/reducers/models.ts";
import { useMemo, useState } from "react";

type PipelineModelsRequiredDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  models: PipelineModelStatusItem[];
  onModelsChanged?: () => void | Promise<void>;
  title?: string;
  description?: string;
};

export type { PipelineModelStatusItem };

const toModelLabel = (value: string): string => value.split("/").pop() || value;

export const PipelineModelsRequiredDialog = ({
  open,
  onOpenChange,
  models,
  onModelsChanged,
  title = "Required models are missing",
  description = "This pipeline uses one or more models that are not installed.",
}: PipelineModelsRequiredDialogProps) => {
  const availableModels = useAppSelector(selectModels);
  const { installModel, isPending } = useModelInstall();

  const modelByDisplayName = useMemo(() => {
    const map = new Map<string, Model>();
    availableModels.forEach((model) => {
      map.set(model.display_name, model);
      map.set(model.name, model);
    });
    return map;
  }, [availableModels]);

  const [gatedPrompt, setGatedPrompt] = useState<{
    name: string;
    link: string | null;
  } | null>(null);

  const install = async (name: string) => {
    await installModel(name);
    await onModelsChanged?.();
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-xl" showCloseButton>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>

          <div className="max-h-80 overflow-y-auto rounded border">
            <div className="divide-y">
              {models.map((item) => {
                const isInstalled = item.installStatus === "installed";
                const catalogModel = modelByDisplayName.get(item.model);
                const installableModelName = catalogModel?.name;
                const canInstall =
                  !isInstalled &&
                  item.installStatus !== "installing" &&
                  Boolean(installableModelName);
                const pending = isPending(installableModelName);
                const showInstallButton = canInstall && !pending;

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
                      <ModelInstallStatusIndicator
                        status={item.installStatus}
                        showInstalling={pending}
                      />

                      <ModelInstallButtonSlot
                        showButton={showInstallButton}
                        disabled={!canInstall}
                        onInstall={async () => {
                          if (!catalogModel) {
                            return;
                          }

                          if (isGatedModel(catalogModel)) {
                            setGatedPrompt({
                              name: catalogModel.name,
                              link: catalogModel.link ?? null,
                            });
                            return;
                          }

                          await install(catalogModel.name);
                        }}
                      />
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
      <LicenseAcknowledgementDialog
        open={gatedPrompt !== null}
        onOpenChange={(isOpen) => {
          if (!isOpen) setGatedPrompt(null);
        }}
        models={
          gatedPrompt ? [{ name: gatedPrompt.name, url: gatedPrompt.link }] : []
        }
        hubName="Hugging Face"
        onConfirm={() => {
          if (!gatedPrompt) return;
          const { name } = gatedPrompt;
          setGatedPrompt(null);
          void install(name);
        }}
      />
    </>
  );
};
