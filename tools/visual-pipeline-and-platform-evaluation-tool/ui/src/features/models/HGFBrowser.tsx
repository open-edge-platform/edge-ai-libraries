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
  PaginationLink,
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
import { Loader2, AlertCircle, Download, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { selectModels } from "@/store/reducers/models";
import { useAsyncJob } from "@/hooks/useAsyncJob";
import { formatElapsedTimeMillis } from "@/lib/timeUtils";
import { ModelInstallStatusIndicator } from "@/features/models/ModelInstallStatusIndicator";
import { asString } from "@/lib/utils";
import {
  handleApiError,
  handleAsyncJobError,
  isAsyncJobError,
} from "@/lib/apiUtils.ts";

const ITEMS_PER_PAGE = 13;

const HUB_AUTHOR = "OpenVINO";

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
  const [offsetStack, setOffsetStack] = useState<number[]>([0]);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
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

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(inputSearch);
      setOffsetStack([0]);
    }, 300);

    return () => clearTimeout(timer);
  }, [inputSearch]);

  const offset = offsetStack[offsetStack.length - 1];

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
            offset,
          },
        }).unwrap();

        setModels(response.items || []);
        setHasNextPage(
          response.has_more ?? (response.items?.length ?? 0) >= ITEMS_PER_PAGE,
        );
        setNextOffset(response.next_offset ?? offset + ITEMS_PER_PAGE);
      } catch (err) {
        console.error("Failed to fetch models:", err);
        setModels([]);
        setHasNextPage(false);
        setNextOffset(null);
      }
    };

    fetchModels();
  }, [search, offset, listHubModels]);

  const hasSearch = Boolean(search.trim());

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <label className="text-sm font-medium">Organization</label>
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

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>Failed to load models. Please try again.</span>
        </div>
      )}

      {isLoading && (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      )}

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

      {!isLoading && models.length > 0 && (
        <Table className="table-fixed min-w-[60.5rem]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-80">Name</TableHead>
              <TableHead className="w-24">Model Page</TableHead>
              <TableHead className="w-48">Task</TableHead>
              <TableHead className="w-24">License</TableHead>
              <TableHead className="w-14">Gated</TableHead>
              <TableHead className="w-24 text-right">Downloads</TableHead>
              <TableHead className="w-28 text-right"></TableHead>
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
                  <TableCell>
                    {name ? (
                      <a
                        href={`https://huggingface.co/${name}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label={`Open ${name} on Hugging Face`}
                        className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                      >
                        <ExternalLink className="h-4 w-4" />
                        Open
                      </a>
                    ) : (
                      "—"
                    )}
                  </TableCell>
                  <TableCell className="break-words">{task ?? "—"}</TableCell>
                  <TableCell className="break-words">
                    {asString(model.license) ?? "—"}
                  </TableCell>
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
                      <ModelInstallStatusIndicator status="installed" />
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
                        <Download className="mr-2 h-4 w-4" />
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

      {!isLoading && (offsetStack.length > 1 || hasNextPage) && (
        <div className="flex items-center justify-center">
          <Pagination>
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  onClick={() =>
                    setOffsetStack((stack) =>
                      stack.length > 1 ? stack.slice(0, -1) : stack,
                    )
                  }
                  className={
                    offsetStack.length === 1
                      ? "pointer-events-none opacity-50"
                      : "cursor-pointer"
                  }
                />
              </PaginationItem>
              <PaginationItem>
                <PaginationLink isActive>{offsetStack.length}</PaginationLink>
              </PaginationItem>
              <PaginationItem>
                <PaginationNext
                  onClick={() =>
                    setOffsetStack((stack) => [
                      ...stack,
                      nextOffset ?? offset + ITEMS_PER_PAGE,
                    ])
                  }
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
