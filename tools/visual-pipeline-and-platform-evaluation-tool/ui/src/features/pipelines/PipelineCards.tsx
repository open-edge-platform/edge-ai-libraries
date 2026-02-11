import { type Pipeline } from "@/api/api.generated";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { EllipsisVertical, Lock } from "lucide-react";
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
import { CreatePipelineButton } from "./CreatePipelineButton.tsx";
import { usePipelineTagColors } from "@/hooks/usePipelineTagColors";

type PipelineCardsProps = {
  pipelines: Pipeline[];
  maxCards?: number;
};

export const PipelineCards = ({ pipelines, maxCards }: PipelineCardsProps) => {
  const { theme } = useTheme();
  const { tagColorMap } = usePipelineTagColors(pipelines);
  const [openDropdownId, setOpenDropdownId] = useState<string | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [pipelineToDelete, setPipelineToDelete] = useState<{
    id: string;
    name: string;
    variantCount: number;
  } | null>(null);

  const handleDeleteClick = (pipeline: {
    id: string;
    name: string;
    variantCount: number;
  }) => {
    setPipelineToDelete(pipeline);
    setDeleteDialogOpen(true);
  };

  const displayedPipelines =
    maxCards !== undefined ? pipelines.slice(0, maxCards) : pipelines;

  return (
    <>
      <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(300px,1fr))]">
        <CreatePipelineButton />

        {displayedPipelines.map((pipeline) => (
          <Card
            key={pipeline.id}
            className={`flex flex-col pt-0 transition-all duration-200 overflow-hidden ${
              openDropdownId === pipeline.id
                ? "-translate-y-1 shadow-md"
                : "hover:-translate-y-1 hover:shadow-md"
            }`}
          >
            {pipeline.thumbnail && pipeline.variants.length > 0 && (
              <Link to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}`}>
                <img
                  src={pipeline.thumbnail}
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
                      to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}`}
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
                    <DropdownMenuItem>Edit Pipeline</DropdownMenuItem>
                    <DropdownMenuItem>Duplicate Pipeline</DropdownMenuItem>
                    {pipeline.source !== "PREDEFINED" ? (
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
                          handleDeleteClick({
                            id: pipeline.id,
                            name: pipeline.name,
                            variantCount: pipeline.variants.length,
                          });
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
                    to={`/pipelines/${pipeline.id}/${variant.id}`}
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

      <DeletePipelineDialog
        open={deleteDialogOpen}
        onOpenChange={setDeleteDialogOpen}
        pipeline={pipelineToDelete}
        onSuccess={() => setPipelineToDelete(null)}
      />
    </>
  );
};
