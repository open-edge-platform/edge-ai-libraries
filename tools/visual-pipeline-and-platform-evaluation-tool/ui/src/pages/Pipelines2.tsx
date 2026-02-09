import { useGetPipelinesQuery } from "@/api/api.generated";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Plus, EllipsisVertical } from "lucide-react";
import { useMemo } from "react";
import { useTheme } from "next-themes";
import { Link } from "react-router";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";

const ELECTRIC_COLORS = [
  "electric-aqua",
  "electric-cobalt",
  "electric-coral",
  "electric-daisy",
  "electric-geode",
  "electric-moss",
  "electric-rust",
] as const;

export const Pipelines2 = () => {
  const { data: pipelines, isLoading, error } = useGetPipelinesQuery();
  const { theme } = useTheme();

  const tagColorMap = useMemo(() => {
    if (!pipelines) return new Map<string, string>();

    const uniqueTags = Array.from(
      new Set(pipelines.flatMap((p) => p.tags || [])),
    ).sort();

    if (uniqueTags.length > ELECTRIC_COLORS.length) {
      throw new Error(
        `Not enough colors for tags. Found ${uniqueTags.length} unique tags but only ${ELECTRIC_COLORS.length} colors available.`,
      );
    }

    return new Map(
      uniqueTags.map((tag, index) => [tag, ELECTRIC_COLORS[index]]),
    );
  }, [pipelines]);

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error loading pipelines</div>;

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-4">
        <div className="grid gap-4 grid-cols-[repeat(auto-fit,minmax(300px,1fr))]">
          <Card className="flex flex-col items-center justify-center min-h-[400px] border-2 border-dashed transition-all duration-200 hover:-translate-y-1 hover:shadow-md cursor-pointer">
            <CardHeader className="flex flex-col items-center justify-center flex-1">
              <Plus className="w-12 h-12 text-muted-foreground mb-2" />
              <CardTitle className="text-center">Create Pipeline</CardTitle>
            </CardHeader>
          </Card>

          {pipelines?.map((pipeline) => (
            <Card
              key={pipeline.id}
              className="flex flex-col pt-0 transition-all duration-200 hover:-translate-y-1 hover:shadow-md overflow-hidden"
            >
              {pipeline.thumbnail && pipeline.variants.length > 0 && (
                <Link
                  to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}`}
                >
                  <img
                    src={pipeline.thumbnail}
                    alt={pipeline.name}
                    className="w-full object-cover"
                  />
                </Link>
              )}
              <CardHeader className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="truncate" title={pipeline.name}>
                    {pipeline.variants.length > 0 ? (
                      <Link
                        to={`/pipelines/${pipeline.id}/${pipeline.variants[0].id}`}
                        className="hover:underline"
                      >
                        {pipeline.name}
                      </Link>
                    ) : (
                      pipeline.name
                    )}
                  </CardTitle>
                  <DropdownMenu>
                    <DropdownMenuTrigger className="shrink-0 p-1 hover:bg-accent rounded">
                      <EllipsisVertical className="h-4 w-4" />
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem>Edit Description</DropdownMenuItem>
                      <DropdownMenuItem>Duplicate Pipeline</DropdownMenuItem>
                      <DropdownMenuItem variant="destructive">
                        Delete
                      </DropdownMenuItem>
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
      </div>
    </div>
  );
};
