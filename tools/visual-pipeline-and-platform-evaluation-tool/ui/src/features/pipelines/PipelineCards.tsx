import { type Pipeline } from "@/api/api.generated";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EllipsisVertical, Lock, Plus } from "lucide-react";
import { useState } from "react";
import { useTheme } from "next-themes";
import { Link } from "react-router";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { DeletePipelineDialog } from "./DeletePipelineDialog";
import { EditPipelineDialog } from "./EditPipelineDialog";
import { DuplicatePipelineDialog } from "./DuplicatePipelineDialog";
import { CreatePipelineDialog } from "./CreatePipelineDialog.tsx";
import { usePipelineTagColors } from "@/hooks/usePipelineTagColors";
import thumbnailPlaceholder from "@/assets/thumbnail_placeholder.png";

type PipelineCardsProps = {
  pipelines: Pipeline[];
  maxCards?: number;
  source: "dashboard" | "pipelines";
};

export const PipelineCards = ({
  pipelines,
  maxCards,
  source,
}: PipelineCardsProps) => {
  const { theme } = useTheme();
  const { tagColorMap } = usePipelineTagColors(pipelines);
  const [openDropdownId, setOpenDropdownId] = useState<string | null>(null);
  const [selectedPipeline, setSelectedPipeline] = useState<Pipeline | null>(
    null,
  );
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [duplicateDialogOpen, setDuplicateDialogOpen] = useState(false);

  const handleEditClick = (pipeline: Pipeline) => {
    setSelectedPipeline(pipeline);
    setEditDialogOpen(true);
  };

  const handleDuplicateClick = (pipeline: Pipeline) => {
    setSelectedPipeline(pipeline);
    setDuplicateDialogOpen(true);
  };

  const handleDeleteClick = (pipeline: Pipeline) => {
    setSelectedPipeline(pipeline);
    setDeleteDialogOpen(true);
  };

  const displayedPipelines =
    maxCards !== undefined ? pipelines.slice(0, maxCards) : pipelines;

  return (
    <>
      <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(300px,1fr))]">
        <CreatePipelineDialog>
          <button className="w-full h-full min-h-[200px] border-2 border-dashed border-gray-300 dark:border-gray-700 hover:border-classic-blue dark:hover:border-energy-blue hover:bg-blue-50 dark:hover:bg-energy-blue/5 transition-all flex flex-col items-center justify-center gap-3 text-carbon-tint-1 dark:text-gray-400 hover:text-classic-blue dark:hover:text-energy-blue">
            <Plus className="w-12 h-12" />
            <span className="text-lg font-medium">Create Pipeline</span>
          </button>
        </CreatePipelineDialog>

        {displayedPipelines.map((pipeline) => (
          <Card
            key={pipeline.id}
            className={`flex flex-col pt-0 transition-all duration-200 overflow-hidden ${
              openDropdownId === pipeline.id
                ? "-translate-y-1 shadow-md"
                : "hover:-translate-y-1 hover:shadow-md"
            }`}
          >
            {pipeline.variants.length > 0 && (
              <Link
                to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}?source=${source}`}
              >
                <img
                  src={pipeline.thumbnail ?? thumbnailPlaceholder}
                  alt={pipeline.name}
                  className="w-full object-cover"
                />
              </Link>
            )}
            <CardHeader className="space-y-2">
              <div className="flex items-center justify-between gap-2 min-w-0">
                <CardTitle
                  className="truncate min-w-0 overflow-hidden"
                  title={pipeline.name}
                >
                  {pipeline.variants.length > 0 ? (
                    <Link
                      to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}?source=${source}`}
                      className="hover:underline block truncate"
                    >
                      {pipeline.name}
                    </Link>
                  ) : (
                    <span className="block truncate">{pipeline.name}</span>
                  )}
                </CardTitle>
                <DropdownMenu
                  onOpenChange={(open) =>
                    setOpenDropdownId(open ? pipeline.id : null)
                  }
                >
                  <DropdownMenuTrigger className="shrink-0 p-1 hover:bg-accent rounded w-6 h-6 flex items-center justify-center">
                    <EllipsisVertical className="h-4 w-4" />
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        handleEditClick(pipeline);
                      }}
                    >
                      Edit Pipeline
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDuplicateClick(pipeline);
                      }}
                    >
                      Duplicate Pipeline
                    </DropdownMenuItem>
                    {pipeline.source === "PREDEFINED" ? (
                      <DropdownMenuItem
                        variant="destructive"
                        disabled
                        className="flex items-center justify-between gap-2"
                      >
                        Delete
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="pointer-events-auto">
                              <Lock className="h-4 w-4" />
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="top">
                            Predefined pipeline cannot be deleted.
                          </TooltipContent>
                        </Tooltip>
                      </DropdownMenuItem>
                    ) : (
                      <DropdownMenuItem
                        variant="destructive"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteClick(pipeline);
                        }}
                      >
                        Delete
                      </DropdownMenuItem>
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
              <div className="flex flex-wrap gap-1">
                {pipeline.tags?.map((tag) => (
                  <Badge
                    key={tag}
                    variant="outline"
                    className="rounded border-0"
                    style={{
                      backgroundColor:
                        theme === "dark"
                          ? `var(--${tagColorMap.get(tag)})`
                          : `color-mix(in oklch, var(--${tagColorMap.get(tag)}) 50%, white)`,
                    }}
                  >
                    {tag}
                  </Badge>
                ))}
                {pipeline.variants.map((variant) => (
                  <Link
                    key={variant.id}
                    to={`/pipelines/${pipeline.id}/${variant.id}?source=${source}`}
                  >
                    <Badge
                      variant="secondary"
                      className="cursor-pointer transition-opacity hover:opacity-70"
                    >
                      {variant.name}
                    </Badge>
                  </Link>
                ))}
              </div>
              <CardDescription className="line-clamp-6 text-justify">
                {pipeline.description}
              </CardDescription>
            </CardHeader>
          </Card>
        ))}
      </div>

      {selectedPipeline && (
        <>
          <EditPipelineDialog
            pipeline={selectedPipeline}
            open={editDialogOpen}
            onOpenChange={(isOpen) => {
              setEditDialogOpen(isOpen);
              if (!isOpen) {
                setSelectedPipeline(null);
              }
            }}
            onSuccess={() => setSelectedPipeline(null)}
          />
          <DuplicatePipelineDialog
            pipeline={selectedPipeline}
            open={duplicateDialogOpen}
            onOpenChange={(isOpen) => {
              setDuplicateDialogOpen(isOpen);
              if (!isOpen) {
                setSelectedPipeline(null);
              }
            }}
            onSuccess={() => setSelectedPipeline(null)}
          />
          <DeletePipelineDialog
            open={deleteDialogOpen}
            onOpenChange={setDeleteDialogOpen}
            pipeline={selectedPipeline}
            onSuccess={() => setSelectedPipeline(null)}
          />
        </>
      )}
    </>
  );
};
