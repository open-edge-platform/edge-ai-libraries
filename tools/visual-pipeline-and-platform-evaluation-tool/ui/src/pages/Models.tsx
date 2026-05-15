import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table.tsx";
import { Button } from "@/components/ui/button.tsx";
import { Badge } from "@/components/ui/badge.tsx";
import { Checkbox } from "@/components/ui/checkbox.tsx";
import { useAppSelector, useAppDispatch } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { selectPipelinesMap } from "@/store/reducers/pipelines";
import { MultiFileUploader } from "@/features/upload/MultiFileUploader.tsx";
import {
  PRE_UPLOAD_MESSAGES,
  type PreUploadMessage as PRE_UPLOAD_MESSAGES_TYPE,
} from "@/features/upload/uploaderMessages";
import { ENDPOINTS } from "@/api/apiEndpoints";
import {
  api,
  type ModelInstallStatus,
  useStartModelDownloadMutation,
} from "@/api/api.generated.ts";
import JSZip from "jszip";
import { useEffect, useCallback, useMemo, useRef, useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { useBackgroundJobs } from "@/contexts/useBackgroundJobs";

const REQUIRED_MODEL_FILES = ["model.bin", "model.xml"];
const ALLOWED_CATEGORIES = ["classification", "detection", "genai"] as const;

/**
 * Render a model `install_status` value as a Title-Case label without
 * underscores, e.g. `not_installed` -> `Not Installed`.
 */
const formatInstallStatus = (status: ModelInstallStatus): string =>
  status
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");

const STATUS_BADGE_VARIANT: Record<
  ModelInstallStatus,
  "default" | "secondary" | "destructive" | "outline"
> = {
  installed: "default",
  installing: "secondary",
  not_installed: "outline",
  failed: "destructive",
};

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
  const pipelinesMap = useAppSelector(selectPipelinesMap);
  const dispatch = useAppDispatch();
  const { registerJobGroup, unregisterJobGroup, updateJobs } =
    useBackgroundJobs();
  const [startDownload] = useStartModelDownloadMutation();
  // Track model names with an in-flight download request so the button
  // can show a spinner immediately, even before the next /models poll
  // flips install_status to "installing".
  const [pendingDownloads, setPendingDownloads] = useState<
    ReadonlySet<string>
  >(() => new Set());
  // Names currently checked in the bulk-install column. Stale entries
  // (models that became installed) are filtered out at render time.
  const [selectedNames, setSelectedNames] = useState<ReadonlySet<string>>(
    () => new Set(),
  );

  // Names a user is allowed to install in bulk (not_installed or failed).
  const installableNames = useMemo(
    () =>
      models
        .filter(
          (m) =>
            m.install_status === "not_installed" ||
            m.install_status === "failed",
        )
        .map((m) => m.name),
    [models],
  );

  // Auto-select every `default` model that is still installable. We
  // track which names we already auto-handled so that:
  //   * a model is only ever pre-selected once (deselecting it manually
  //     stays sticky across polls),
  //   * a model that goes back to "not_installed" / "failed" later (e.g.
  //     after a failed install) is **not** re-selected silently.
  const autoSelectedRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    const installable = new Set(installableNames);
    const toAdd: string[] = [];
    for (const m of models) {
      if (
        m.default &&
        installable.has(m.name) &&
        !autoSelectedRef.current.has(m.name)
      ) {
        toAdd.push(m.name);
        autoSelectedRef.current.add(m.name);
      }
    }
    if (toAdd.length > 0) {
      setSelectedNames((prev) => {
        const next = new Set(prev);
        for (const n of toAdd) next.add(n);
        return next;
      });
    }
  }, [models, installableNames]);

  // Drop selections whose underlying model is no longer installable so
  // the header checkbox / button stays consistent across polls.
  const effectiveSelection = useMemo(() => {
    const installable = new Set(installableNames);
    return new Set([...selectedNames].filter((n) => installable.has(n)));
  }, [selectedNames, installableNames]);

  const toggleSelected = useCallback((modelName: string, value: boolean) => {
    setSelectedNames((prev) => {
      const next = new Set(prev);
      if (value) next.add(modelName);
      else next.delete(modelName);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(
    (value: boolean) => {
      setSelectedNames(value ? new Set(installableNames) : new Set());
    },
    [installableNames],
  );

  useEffect(() => {
    registerJobGroup("models", "Model Uploads", ["/models"]);
    return () => {
      unregisterJobGroup("models");
    };
  }, [registerJobGroup, unregisterJobGroup]);

  const installModels = useCallback(
    async (names: readonly string[]) => {
      if (names.length === 0) return;
      setPendingDownloads((prev) => {
        const next = new Set(prev);
        for (const n of names) next.add(n);
        return next;
      });
      try {
        // The endpoint always returns ModelDownloadJobResponse (202 or
        // 207). RTK Query rejects on non-2xx (400/404/409) too — both
        // branches share the per-name `jobs` map shape.
        let jobs: Record<
          string,
          {
            status_code: number;
            message: string;
            job_id?: string | null;
          }
        > = {};
        try {
          const response = await startDownload({
            modelDownloadRequest: { names: [...names] },
          }).unwrap();
          jobs = response.jobs ?? {};
        } catch (err) {
          const data = (err as { data?: unknown })?.data;
          if (
            data &&
            typeof data === "object" &&
            "jobs" in data &&
            data.jobs &&
            typeof data.jobs === "object"
          ) {
            jobs = data.jobs as typeof jobs;
          } else {
            throw err;
          }
        }

        let accepted = 0;
        const rejected: string[] = [];
        for (const name of names) {
          const item = jobs[name];
          if (item?.status_code === 202) {
            accepted += 1;
          } else if (item) {
            rejected.push(`${name}: ${item.message}`);
          } else {
            rejected.push(`${name}: no response from backend`);
          }
        }

        if (accepted > 0) {
          toast.success(
            accepted === 1
              ? `Started download of 1 model.`
              : `Started download of ${accepted} models.`,
          );
        }
        if (rejected.length > 0) {
          toast.error(
            rejected.length === 1
              ? rejected[0]
              : `${rejected.length} model(s) could not be installed:\n${rejected.join("\n")}`,
          );
        }

        // Clear selection for any successfully accepted model.
        setSelectedNames((prev) => {
          const next = new Set(prev);
          for (const name of names) {
            const item = jobs[name];
            if (item?.status_code === 202) next.delete(name);
          }
          return next;
        });

        // Trigger a fresh /models fetch so install_status updates.
        dispatch(api.util.invalidateTags(["models"]));
      } catch (error) {
        const message =
          (error as { data?: { message?: string } })?.data?.message ??
          `Could not start download.`;
        toast.error(message);
      } finally {
        setPendingDownloads((prev) => {
          const next = new Set(prev);
          for (const n of names) next.delete(n);
          return next;
        });
      }
    },
    [dispatch, startDownload],
  );

  const handleInstall = useCallback(
    (modelName: string) => installModels([modelName]),
    [installModels],
  );

  const handleInstallSelected = useCallback(
    () => installModels([...effectiveSelection]),
    [effectiveSelection, installModels],
  );

  const handlePreUpload = useCallback(
    async (
      file: File,
      fields: Record<string, string>,
    ): Promise<PRE_UPLOAD_MESSAGES_TYPE | null> => {
      const archiveError = await validateModelArchive(file);
      if (archiveError !== null) return archiveError;

      // Check existence against the in-store list (kept up to date by
      // the useModelsLoader hook). vippet-app reports a model as
      // installed via `install_status` once the upload finishes.
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
              regex: /^[a-zA-Z0-9_-\s]+$/,
              regexMessage:
                "Only alphanumeric characters, spaces, underscores, and hyphens are allowed.",
            },
            {
              name: "category",
              label: "Category",
              placeholder: ALLOWED_CATEGORIES.join(" | "),
              required: true,
              regex: new RegExp(`^(?:${ALLOWED_CATEGORIES.join("|")})$`),
              regexMessage: `Must be one of: ${ALLOWED_CATEGORIES.join(", ")}.`,
            },
          ]}
          className="mb-8"
        />

        <div className="mb-3 flex items-center justify-end gap-3">
          <span className="text-sm text-muted-foreground">
            {effectiveSelection.size > 0
              ? `${effectiveSelection.size} model${effectiveSelection.size === 1 ? "" : "s"} selected`
              : "Select one or more uninstalled models to install"}
          </span>
          <Button
            size="sm"
            disabled={
              effectiveSelection.size === 0 ||
              [...effectiveSelection].some((n) => pendingDownloads.has(n))
            }
            onClick={handleInstallSelected}
          >
            {[...effectiveSelection].some((n) => pendingDownloads.has(n)) ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Download className="size-4" />
            )}
            Install
            {effectiveSelection.size > 0 ? ` (${effectiveSelection.size})` : ""}
          </Button>
        </div>

        <Table className="mb-10">
          <TableHeader>
            <TableRow>
              <TableHead className="w-8">
                <Checkbox
                  aria-label="Select all installable models"
                  disabled={installableNames.length === 0}
                  checked={
                    installableNames.length > 0 &&
                    effectiveSelection.size === installableNames.length
                      ? true
                      : effectiveSelection.size > 0
                        ? "indeterminate"
                        : false
                  }
                  onCheckedChange={(value) => toggleSelectAll(value === true)}
                />
              </TableHead>
              <TableHead className="w-[33%] truncate">Name</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Precisions</TableHead>
              <TableHead>Used by</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model) => {
              const isPending = pendingDownloads.has(model.name);
              const canInstall =
                model.install_status === "not_installed" ||
                model.install_status === "failed";
              const isChecked = effectiveSelection.has(model.name);
              return (
                <TableRow key={model.name}>
                  <TableCell>
                    <Checkbox
                      aria-label={`Select ${model.display_name}`}
                      disabled={!canInstall || isPending}
                      checked={isChecked}
                      onCheckedChange={(value) =>
                        toggleSelected(model.name, value === true)
                      }
                    />
                  </TableCell>
                  <TableCell className="font-medium max-w-0">
                    <div className="truncate" title={model.display_name}>
                      {model.display_name}
                    </div>
                  </TableCell>
                  <TableCell>{model.category ?? "-"}</TableCell>
                  <TableCell>{model.source}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_BADGE_VARIANT[model.install_status]}>
                      {formatInstallStatus(model.install_status)}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {Array.from(
                      new Set(
                        model.variants
                          ?.map((v) => v.precision)
                          .filter((p): p is string => Boolean(p)) ?? [],
                      ),
                    ).join(", ") || "-"}
                  </TableCell>
                  <TableCell className="whitespace-pre-line">
                    {(model.used_by_pipelines ?? [])
                      .map(
                        (pipelineId) =>
                          pipelinesMap.get(pipelineId)?.name ?? pipelineId,
                      )
                      .join("\n") || "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    {canInstall && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={isPending}
                        onClick={() => handleInstall(model.name)}
                      >
                        {isPending ? (
                          <Loader2 className="size-4 animate-spin" />
                        ) : (
                          <Download className="size-4" />
                        )}
                        Install
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
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
