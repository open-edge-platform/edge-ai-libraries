import { useAppSelector, useAppDispatch } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import {
  PRE_UPLOAD_MESSAGES,
  type PreUploadMessage as PRE_UPLOAD_MESSAGES_TYPE,
} from "@/features/upload/uploaderMessages";
import { api, type ModelCategory } from "@/api/api.generated.ts";
import JSZip from "jszip";
import { useEffect, useCallback, useMemo } from "react";
import { toast } from "sonner";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button.tsx";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { ModelsTable } from "@/features/models/ModelsTable.tsx";
import { AddModelDialog } from "@/features/models/AddModelDialog.tsx";
import { useModelInstall } from "@/features/models/useModelInstall";
import { CATEGORY_INFO } from "@/features/models/categoryInfo.ts";
import { CONTENT_CONTAINER_CLASS } from "@/lib/utils";

const REQUIRED_MODEL_FILES = ["model.bin", "model.xml"];

const validateModelArchive = async (
  file: File,
): Promise<PRE_UPLOAD_MESSAGES_TYPE | null> => {
  try {
    const zip = await JSZip.loadAsync(file);
    const fileNames = Object.keys(zip.files).map(
      (name) => name.split("/").pop()!,
    );
    const missing = REQUIRED_MODEL_FILES.filter(
      (required) => !fileNames.includes(required),
    );
    if (missing.length > 0) {
      return PRE_UPLOAD_MESSAGES.MISSING_REQUIRED_FILES;
    }
  } catch {
    return PRE_UPLOAD_MESSAGES.INVALID_ARCHIVE;
  }

  return null;
};

export const Models = () => {
  const models = useAppSelector(selectModels);
  const dispatch = useAppDispatch();
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();

  const presentCategories = useMemo(() => {
    const present = new Set(models.map((m) => m.category ?? null));
    const ordered: (ModelCategory | null)[] = (
      Object.keys(CATEGORY_INFO) as ModelCategory[]
    ).filter((c) => present.has(c));
    if (present.has(null)) ordered.push(null);
    return ordered;
  }, [models]);

  const { pendingDownloads, installModels: runModelInstall } =
    useModelInstall();

  const requiredUninstalledModels = useMemo(
    () =>
      models.filter(
        (model) =>
          (model.used_by_pipelines?.length ?? 0) > 0 &&
          (model.install_status === "not_installed" ||
            model.install_status === "failed"),
      ),
    [models],
  );

  const installSelectedModels = useCallback(
    async (names: readonly string[]) => {
      if (names.length === 0) return;
      await runModelInstall(names);
    },
    [runModelInstall],
  );

  const handleInstallRequiredModels = useCallback(
    () =>
      installSelectedModels(
        requiredUninstalledModels.map((model) => model.name),
      ),
    [requiredUninstalledModels, installSelectedModels],
  );

  useEffect(() => {
    registerJobGroup("models", "Model Uploads", ["/models"]);
    return () => {
      unregisterJobGroup("models");
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const handlePreUpload = useCallback(
    async (
      file: File,
      fields: Record<string, string>,
    ): Promise<PRE_UPLOAD_MESSAGES_TYPE | null> => {
      const archiveError = await validateModelArchive(file);
      if (archiveError !== null) return archiveError;

      const modelName = fields.model_name?.trim();
      if (modelName) {
        const exists = models.some(
          (m) => m.name === modelName && m.install_status === "installed",
        );
        if (exists) return PRE_UPLOAD_MESSAGES.FILE_EXISTS;
      }

      return null;
    },
    [models],
  );

  const handleUploadProgress = useCallback(
    (jobs: Array<{ id: string; name: string; progress: number }>) => {
      updateJobs("models", jobs);
    },
    [updateJobs],
  );

  const handleUploadComplete = useCallback(
    (succeeded: number, failed: number) => {
      if (failed === 0 && succeeded > 0) {
        dispatch(api.util.invalidateTags(["models"]));
        toast.success("Upload completed.");
      } else if (succeeded > 0 && failed > 0) {
        toast.warning(
          `${succeeded} file(s) uploaded successfully. ${failed} failed.`,
        );
        dispatch(api.util.invalidateTags(["models"]));
      } else if (failed > 0) {
        toast.error(`Upload failed for ${failed} file(s).`);
      }
    },
    [dispatch],
  );

  if (models.length > 0) {
    return (
      <div className={CONTENT_CONTAINER_CLASS}>
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Models</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use models available in the platform
          </p>
        </div>

        <div className="sticky top-0 z-10 mb-3 flex items-center justify-end gap-3 border-b bg-background py-3">
          <Button
            size="sm"
            disabled={
              requiredUninstalledModels.length === 0 ||
              requiredUninstalledModels.some((model) =>
                pendingDownloads.has(model.name),
              )
            }
            onClick={handleInstallRequiredModels}
          >
            {requiredUninstalledModels.some((model) =>
              pendingDownloads.has(model.name),
            ) ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            Install required models
            {requiredUninstalledModels.length > 0
              ? ` (${requiredUninstalledModels.length})`
              : ""}
          </Button>
          <AddModelDialog
            onPreUpload={handlePreUpload}
            onUploadProgress={handleUploadProgress}
            onUploadComplete={handleUploadComplete}
          />
        </div>

        <div className="columns-1 gap-8 lg:columns-2">
          {presentCategories.map((category) => (
            <div
              key={category ?? "uncategorized"}
              className="mb-10 break-inside-avoid"
            >
              <h2 className="mb-1 text-xl font-semibold">
                {category ? CATEGORY_INFO[category].label : "Uncategorized"}
              </h2>
              {category && (
                <p className="mb-3 text-sm text-muted-foreground">
                  {CATEGORY_INFO[category].description}
                </p>
              )}
              <ModelsTable
                category={category}
                pendingDownloads={pendingDownloads}
                onInstallOne={(name) => installSelectedModels([name])}
              />
            </div>
          ))}
        </div>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading models</div>
    </div>
  );
};
