import { useAppSelector, useAppDispatch } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import {
  PRE_UPLOAD_MESSAGES,
  type PreUploadMessage as PRE_UPLOAD_MESSAGES_TYPE,
} from "@/features/upload/uploaderMessages";
import { ENDPOINTS } from "@/api/apiEndpoints";
import { api } from "@/api/api.generated.ts";
import JSZip from "jszip";
import { useEffect, useCallback } from "react";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";
import { ModelsTable } from "@/features/models/ModelsTable.tsx";

const REQUIRED_MODEL_FILES = ["model.bin", "model.xml"];
const ALLOWED_CATEGORIES = ["classification", "detection", "genai"] as const;

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
      <div className="container pl-16 mx-auto py-10">
        <div className="mb-6">
          <h1 className="text-3xl font-bold">Models</h1>
          <p className="text-muted-foreground mt-2">
            Ready-to-use models available in the platform
          </p>
        </div>

        <MultiFileUploader
          accept=".zip,application/zip"
          uploadEndpoint={ENDPOINTS.UPLOAD_MODEL}
          multiple={false}
          maxSize={500 * 1024 * 1024} // 500 MB
          preUpload={handlePreUpload}
          preUploadImmediate
          onUploadProgress={handleUploadProgress}
          onUploadComplete={handleUploadComplete}
          formFields={[
            {
              name: "model_name",
              label: "Model name",
              placeholder: "Enter model name",
              required: true,
              regex: /^[a-zA-Z0-9_\s-]+$/,
              regexMessage:
                "Only alphanumeric characters, spaces, underscores, and hyphens are allowed.",
            },
            {
              name: "category",
              label: "Category",
              placeholder: "Select a category",
              required: true,
              type: "combobox" as const,
              options: [...ALLOWED_CATEGORIES],
            },
          ]}
          className="mb-8"
        />

        <ModelsTable />
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading models</div>
    </div>
  );
};
