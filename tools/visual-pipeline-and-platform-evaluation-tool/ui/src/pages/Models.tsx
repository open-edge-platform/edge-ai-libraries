import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
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
import { useLazyGetModelJobsQuery } from "@/api/api.model-download.generated.ts";

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

  useEffect(() => {
    registerJobGroup("models", "Model Uploads", ["/models"]);
    return () => {
      unregisterJobGroup("models");
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const [getModelJobs] = useLazyGetModelJobsQuery();

  const handlePreUpload = useCallback(
    async (
      file: File,
      fields: Record<string, string>,
    ): Promise<PRE_UPLOAD_MESSAGES_TYPE | null> => {
      const archiveError = await validateModelArchive(file);
      if (archiveError !== null) return archiveError;

      const modelName = fields.model_name?.trim();
      if (modelName) {
        try {
          const result = await getModelJobs({ modelName }).unwrap();
          const exists = result.jobs?.some((job) => job.status === "completed");
          if (exists) return PRE_UPLOAD_MESSAGES.FILE_EXISTS;
        } catch {
          // if local check failed by any reason — proceed to upload
        }
      }

      return null;
    },
    [getModelJobs],
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
              regex: /^[a-zA-Z0-9_-\s]+$/,
              regexMessage:
                "Only alphanumeric characters, spaces, underscores, and hyphens are allowed.",
            },
          ]}
          className="mb-8"
        />

        <Table className="mb-10">
          <TableHeader>
            <TableRow>
              <TableHead className="w-[33%] truncate">Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Precision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model) => (
              <TableRow key={model.name}>
                <TableCell className="font-medium max-w-0">
                  <div className="truncate" title={model.display_name}>
                    {model.display_name}
                  </div>
                </TableCell>
                <TableCell>{model.category}</TableCell>
                <TableCell>{model.precision}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }
  return (
    <div className="h-full overflow-auto">
      <div className="container mx-auto py-10">Loading models</div>
    </div>
  );
};
