import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  api,
  useGetModelDownloadJobStatusQuery,
  useListHubModelsMutation,
  useStartModelDownloadMutation,
  type ModelCategory,
  type ModelDownloadJobResponse,
  type ModelHubListResponse,
} from "@/api/api.generated";
import { Loader2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { formatElapsedTimeMillis } from "@/lib/timeUtils";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";

const ITEMS_PER_PAGE = 10;

const HUB_AUTHOR = "OpenVINO";

// Maps HuggingFace `pipeline_tag` values to our model categories.
const TASK_TO_CATEGORY: Record<string, ModelCategory> = {
  "object-detection": "object_detection",
  "image-segmentation": "image_segmentation",
  "keypoint-detection": "pose_estimation",
  "image-classification": "image_classification",
  "image-to-text": "vision_language_models",
  "image-text-to-text": "vision_language_models",
  "visual-question-answering": "vision_language_models",
  "text-generation": "large_language_models",
  "text2text-generation": "large_language_models",
  "automatic-speech-recognition": "automatic_speech_recognition",
  "text-to-speech": "text_to_speech",
};

const matchCategory = (task: string | null): ModelCategory | null =>
  task ? (TASK_TO_CATEGORY[task] ?? null) : null;

type HGFBrowserProps = {
  onInstalled?: () => void;
};

const asString = (value: unknown): string | null =>
  typeof value === "string" && value !== "" ? value : null;

const getDownloads = (metadata: unknown): number | null => {
  if (typeof metadata !== "object" || metadata === null) return null;
  const downloads = (metadata as { downloads?: unknown }).downloads;
  return typeof downloads === "number" ? downloads : null;
};

export const HGFBrowser = ({ onInstalled }: HGFBrowserProps) => {
  const dispatch = useAppDispatch();
  const installedModels = useAppSelector(selectModels);
  const installedNames = useMemo(
    () =>
      new Set(
        installedModels
          .filter((model) => model.install_status === "installed")
          .map((model) => model.name),
      ),
    [installedModels],
  );

  const [inputSearch, setInputSearch] = useState("");
  const [search, setSearch] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [models, setModels] = useState<ModelHubListResponse["items"]>([]);
  const [hasNextPage, setHasNextPage] = useState(false);

  const [listHubModels, { isLoading, error }] = useListHubModelsMutation();

  const [installingName, setInstallingName] = useState<string | null>(null);
  const { execute: runInstall, jobStatus } = useAsyncJob({
    asyncJobHook: useStartModelDownloadMutation,
    statusCheckHook: useGetModelDownloadJobStatusQuery,
    pollingInterval: 2000,
    extractJobId: (response: ModelDownloadJobResponse) =>
      Object.values(response.jobs)[0]?.job_id,
  });

  const handleInstall = async (name: string, task: string | null) => {
    const category = matchCategory(task);
    if (!category) {
      toast.error("Cannot install model", {
        description: task
          ? `Unsupported task "${task}" for "${name}".`
          : `Model "${name}" has no known task.`,
      });
      return;
    }

    setInstallingName(name);
    try {
      await runInstall({
        modelDownloadRequest: { names: [name], hub: "huggingface", category },
      });
      dispatch(api.util.invalidateTags(["models"]));
      toast.success(`Model "${name}" installed successfully.`);
      onInstalled?.();
    } catch (err) {
      const rejection = (err as { data?: ModelDownloadJobResponse } | null)
        ?.data?.jobs?.[name]?.message;
      if (isAsyncJobError(err)) {
        handleAsyncJobError(err, "Model installation");
      } else if (rejection) {
        toast.error("Failed to install model", { description: rejection });
      } else {
        handleApiError(err, "Failed to install model");
      }
      console.error("Failed to install model:", err);
    } finally {
      setInstallingName(null);
    }
  };

  // Debounce filters (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(inputSearch);
      setCurrentPage(1);
    }, 300);

    return () => clearTimeout(timer);
  }, [inputSearch]);

  useEffect(() => {
    const fetchModels = async () => {
      const searchTerm = search.trim();
      try {
        const response = await listHubModels({
          modelHubListRequest: {
            hub: "huggingface",
            filters: {
              author: HUB_AUTHOR,
              ...(searchTerm ? { search: searchTerm } : {}),
            },
            limit: ITEMS_PER_PAGE,
            offset: (currentPage - 1) * ITEMS_PER_PAGE,
          },
        }).unwrap();

        // HuggingFace returns no total; one extra item signals a next page.
        const items = response.items || [];
        setModels(items.slice(0, ITEMS_PER_PAGE));
        setHasNextPage(items.length > ITEMS_PER_PAGE);
      } catch (err) {
        console.error("Failed to fetch models:", err);
        setModels([]);
        setHasNextPage(false);
      }
    };

    fetchModels();
  }, [search, currentPage, listHubModels]);

  const hasSearch = Boolean(search.trim());

  return (
    <div className="space-y-4">
      {/* Search Inputs */}
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Author</label>
          <Input type="text" value={HUB_AUTHOR} disabled />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium">Search Models</label>
          <Input
            type="text"
            placeholder="Search HuggingFace models..."
            value={inputSearch}
            onChange={(e) => setInputSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>Failed to load models. Please try again.</span>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && models.length === 0 && !error && (
        <div className="flex items-center justify-center py-8 text-center">
          <div>
            <p className="text-sm font-medium text-muted-foreground">
              {hasSearch ? "No models found" : "No models available"}
            </p>
            {hasSearch && (
              <p className="text-xs text-muted-foreground">
                Try adjusting your search terms
              </p>
            )}
          </div>
        </div>
      )}

      {/* Models Table */}
      {!isLoading && models.length > 0 && (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Task</TableHead>
              <TableHead>License</TableHead>
              <TableHead>Gated</TableHead>
              <TableHead className="text-right">Downloads</TableHead>
              <TableHead className="w-56 text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model, idx) => {
              const downloads = getDownloads(model.metadata);
              const name = asString(model.name);
              const task = asString(model.model_type);
              return (
                <TableRow key={name ?? idx} className="odd:bg-muted/30">
                  <TableCell className="whitespace-normal break-words font-medium">
                    {name ?? "—"}
                  </TableCell>
                  <TableCell>{task ?? "—"}</TableCell>
                  <TableCell>{asString(model.license) ?? "—"}</TableCell>
                  <TableCell>
                    {typeof model.gated === "boolean"
                      ? model.gated
                        ? "Yes"
                        : "No"
                      : (asString(model.gated) ?? "—")}
                  </TableCell>
                  <TableCell className="text-right">
                    {downloads !== null ? downloads.toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    {!name ? null : installedNames.has(name) ? (
                      <span className="text-sm text-muted-foreground">
                        Installed
                      </span>
                    ) : installingName === name ? (
                      <span className="inline-flex items-center gap-2 text-sm text-muted-foreground">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {jobStatus?.progress_message || "Installing"}
                        {jobStatus
                          ? ` (${formatElapsedTimeMillis(jobStatus.elapsed_time)})`
                          : ""}
                      </span>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={installingName !== null}
                        onClick={() => handleInstall(name, task)}
                      >
                        Install
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      {/* Pagination */}
      {!isLoading && (currentPage > 1 || hasNextPage) && (
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">Page {currentPage}</p>
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  className={
                    currentPage === 1
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer"
                  }
                />
              </PaginationItem>
              <PaginationItem>
                <PaginationNext
                  onClick={() => setCurrentPage(currentPage + 1)}
                  className={
                    hasNextPage
                      ? "cursor-pointer"
                      : "pointer-events-none opacity-50"
                  }
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        </div>
      )}
    </div>
  );
};
