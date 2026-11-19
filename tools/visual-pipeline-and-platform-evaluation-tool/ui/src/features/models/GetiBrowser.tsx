import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { Loader2, AlertCircle, Download } from "lucide-react";
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

// The Geti listing has no task filter, so a category is applied client-side
// over the full listing.
const FETCH_ALL_PAGE_SIZE = 200;
const ALL_CATEGORIES = "all";
const CATEGORY_OPTIONS = [
  "detection",
  "classification",
  "instance_segmentation",
] as const;

// Geti task types vary in casing/prefix (e.g. DETECTION, instance_segmentation).
const matchCategory = (task: string | null): ModelCategory | null => {
  const value = task?.toLowerCase() ?? "";
  if (value.includes("keypoint") || value.includes("pose"))
    return "pose_estimation";
  if (value.includes("segmentation")) return "image_segmentation";
  if (value.includes("detection")) return "object_detection";
  if (value.includes("classification")) return "image_classification";
  return null;
};

type GetiBrowserProps = {
  onInstalled?: () => void;
};

// The Geti plugin reports variants as metadata.variants[{ model_format, precision }].
const getOpenVinoPrecisions = (metadata: unknown): string[] => {
  if (typeof metadata !== "object" || metadata === null) return [];
  const variants = (metadata as { variants?: unknown }).variants;
  if (!Array.isArray(variants)) return [];
  const precisions = variants.flatMap((variant: unknown) => {
    const { model_format: format, precision } = (variant ?? {}) as {
      model_format?: unknown;
      precision?: unknown;
    };
    if (typeof format !== "string" || format.toLowerCase() !== "openvino")
      return [];
    return [precision]
      .flat()
      .filter((p): p is string => typeof p === "string" && p !== "");
  });
  return [...new Set(precisions)];
};

const FILTER_FIELDS = [
  { key: "project_name", label: "Project name", placeholder: "detection" },
  { key: "model_name", label: "Model name", placeholder: "yolox-tiny" },
] as const;

type FilterKey = (typeof FILTER_FIELDS)[number]["key"];
type GetiFilters = Record<FilterKey, string>;

const EMPTY_FILTERS: GetiFilters = {
  project_name: "",
  model_name: "",
};

const toPayloadFilters = (filters: GetiFilters): Record<string, string> =>
  Object.fromEntries(
    Object.entries(filters)
      .map(([key, value]) => [key, value.trim()])
      .filter(([, value]) => value !== ""),
  );

export const GetiBrowser = ({ onInstalled }: GetiBrowserProps) => {
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

  const [inputFilters, setInputFilters] = useState<GetiFilters>(EMPTY_FILTERS);
  const [filters, setFilters] = useState<GetiFilters>(EMPTY_FILTERS);
  const [category, setCategory] = useState<string>(ALL_CATEGORIES);
  const [categoryMatches, setCategoryMatches] = useState<
    ModelHubListResponse["items"]
  >([]);
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
    const modelCategory = matchCategory(task);
    if (!modelCategory) {
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
        modelDownloadRequest: {
          names: [name],
          hub: "geti",
          category: modelCategory,
        },
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
      setFilters(inputFilters);
      setOffsetStack([0]);
    }, 300);

    return () => clearTimeout(timer);
  }, [inputFilters]);

  const offset = offsetStack[offsetStack.length - 1];

  useEffect(() => {
    if (category !== ALL_CATEGORIES) return;
    let cancelled = false;
    const fetchModels = async () => {
      try {
        const response = await listHubModels({
          modelHubListRequest: {
            hub: "geti",
            filters: toPayloadFilters(filters),
            limit: ITEMS_PER_PAGE,
            offset,
          },
        }).unwrap();
        if (cancelled) return;

        setModels(response.items || []);
        setHasNextPage(
          response.has_more ?? (response.items?.length ?? 0) >= ITEMS_PER_PAGE,
        );
        setNextOffset(response.next_offset ?? offset + ITEMS_PER_PAGE);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to fetch models:", err);
        setModels([]);
        setHasNextPage(false);
        setNextOffset(null);
      }
    };

    fetchModels();
    return () => {
      cancelled = true;
    };
  }, [filters, offset, category, listHubModels]);

  useEffect(() => {
    if (category === ALL_CATEGORIES) return;
    let cancelled = false;
    const fetchCategoryMatches = async () => {
      try {
        const items: ModelHubListResponse["items"] = [];
        let pageOffset = 0;
        for (;;) {
          const response = await listHubModels({
            modelHubListRequest: {
              hub: "geti",
              filters: toPayloadFilters(filters),
              limit: FETCH_ALL_PAGE_SIZE,
              offset: pageOffset,
            },
          }).unwrap();
          const page = response.items || [];
          items.push(...page);
          const hasMore =
            response.has_more ?? page.length >= FETCH_ALL_PAGE_SIZE;
          if (!hasMore || page.length === 0) break;
          pageOffset = response.next_offset ?? pageOffset + FETCH_ALL_PAGE_SIZE;
        }
        if (cancelled) return;
        setCategoryMatches(
          items.filter(
            (item) => asString(item.model_type)?.toLowerCase() === category,
          ),
        );
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to fetch models:", err);
        setCategoryMatches([]);
      }
    };

    fetchCategoryMatches();
    return () => {
      cancelled = true;
    };
  }, [filters, category, listHubModels]);

  useEffect(() => {
    if (category === ALL_CATEGORIES) return;
    setModels(categoryMatches.slice(offset, offset + ITEMS_PER_PAGE));
    setHasNextPage(offset + ITEMS_PER_PAGE < categoryMatches.length);
    setNextOffset(offset + ITEMS_PER_PAGE);
  }, [category, categoryMatches, offset]);

  const hasFilters =
    Object.keys(toPayloadFilters(filters)).length > 0 ||
    category !== ALL_CATEGORIES;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-4">
        {FILTER_FIELDS.map(({ key, label, placeholder }) => (
          <div key={key} className="space-y-2">
            <label className="text-sm font-medium">{label}</label>
            <Input
              type="text"
              placeholder={placeholder}
              value={inputFilters[key]}
              onChange={(e) =>
                setInputFilters((prev) => ({ ...prev, [key]: e.target.value }))
              }
            />
          </div>
        ))}
        <div className="space-y-2">
          <label className="text-sm font-medium">Category</label>
          <Select
            value={category}
            onValueChange={(value) => {
              setCategory(value);
              setOffsetStack([0]);
            }}
          >
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_CATEGORIES}>All</SelectItem>
              {CATEGORY_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {option}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4" />
          <span>
            Failed to load models. Check that the Geti server is configured and
            try again.
          </span>
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
              {hasFilters ? "No models found" : "No models available"}
            </p>
            {hasFilters && (
              <p className="text-xs text-muted-foreground">
                Try adjusting your filters
              </p>
            )}
          </div>
        </div>
      )}

      {!isLoading && models.length > 0 && (
        <Table className="table-fixed min-w-[62rem]">
          <TableHeader>
            <TableRow>
              <TableHead className="w-44">Project name</TableHead>
              <TableHead className="w-72">Model name</TableHead>
              <TableHead className="w-44">Category</TableHead>
              <TableHead className="w-56">Precisions</TableHead>
              <TableHead className="w-40 text-right"></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((model, idx) => {
              const name = asString(model.name);
              const task = asString(model.model_type);
              const project = asString(model.owner);
              const precisions = getOpenVinoPrecisions(model.metadata);
              return (
                <TableRow key={name ?? idx} className="odd:bg-muted/30">
                  <TableCell className="whitespace-normal break-words">
                    {project ?? "—"}
                  </TableCell>
                  <TableCell className="whitespace-normal break-words font-medium">
                    {name ?? "—"}
                  </TableCell>
                  <TableCell className="break-words">{task ?? "—"}</TableCell>
                  <TableCell className="whitespace-normal break-words">
                    {precisions.length > 0 ? (
                      precisions.join(", ")
                    ) : (
                      <span className="italic text-muted-foreground">
                        no precisions available
                      </span>
                    )}
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
                    ) : precisions.length === 0 ? null : (
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
