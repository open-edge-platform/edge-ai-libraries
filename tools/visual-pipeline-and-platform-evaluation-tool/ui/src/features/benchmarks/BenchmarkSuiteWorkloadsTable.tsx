import type { BenchmarkSuite, Pipeline } from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

const THUMBNAIL_PLACEHOLDER = "/src/assets/thumbnail_placeholder.png";

type BenchmarkSuiteWorkloadsTableProps = {
  benchmark: BenchmarkSuite;
  pipelinesMap: Map<string, Pipeline>;
};

export const BenchmarkSuiteWorkloadsTable = ({
  benchmark,
  pipelinesMap,
}: BenchmarkSuiteWorkloadsTableProps) => {
  const truncateModelName = (name: string) => {
    const parts = name.trim().split(/\s+/).filter(Boolean);

    if (parts.length <= 3) {
      return name;
    }

    return `${parts.slice(0, 3).join(" ")}...`;
  };

  return (
    <Table className="border rounded-lg">
      <TableHeader className="bg-muted">
        <TableRow>
          <TableHead className="w-32"></TableHead>
          <TableHead className="w-max">Pipeline Name</TableHead>
          <TableHead>Description</TableHead>
          <TableHead className="w-max">Variants</TableHead>
          <TableHead className="w-max">Details</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {benchmark.workloads.map((workload) => {
          const pipeline = pipelinesMap.get(workload.pipeline_id);
          const variantNames = workload.variants
            .split(",")
            .map((variantId) => variantId.trim())
            .filter(Boolean)
            .map(
              (variantId) =>
                pipeline?.variants.find((variant) => variant.id === variantId)
                  ?.name ?? variantId,
            )
            .join("\n");

          // Extract details from first variant's pipeline graph.
          const firstVariantId = workload.variants.split(",")[0]?.trim();
          const firstVariant = firstVariantId
            ? pipeline?.variants.find((v) => v.id === firstVariantId)
            : undefined;

          const simpleGraph = firstVariant?.pipeline_graph_simple;
          const sourceNode = simpleGraph?.nodes.find(
            (node) => node.type === "source",
          );
          const sourceValue =
            sourceNode?.data && typeof sourceNode.data === "object"
              ? String(
                  (sourceNode.data as Record<string, unknown>).source ?? "",
                )
              : undefined;

          const modelNodes = simpleGraph?.nodes.filter(
            (node) =>
              node.data &&
              typeof node.data === "object" &&
              (node.data as Record<string, unknown>).model,
          );
          const modelNames =
            modelNodes && modelNodes.length > 0
              ? modelNodes
                  .map((node) => (node.data as Record<string, unknown>).model)
                  .filter((m): m is string => typeof m === "string" && !!m)
              : [];

          const uniqueStreams = [
            ...new Set(workload.test_cases.map((tc) => tc.streams)),
          ]
            .sort((a, b) => a - b)
            .join(", ");

          return (
            <TableRow key={workload.id}>
              <TableCell>
                <img
                  src={pipeline?.thumbnail ?? THUMBNAIL_PLACEHOLDER}
                  alt={pipeline?.name ?? workload.pipeline_id}
                  className="w-32 h-16 object-cover"
                />
              </TableCell>
              <TableCell className="font-medium whitespace-nowrap">
                {pipeline?.name ?? workload.pipeline_id}
              </TableCell>
              <TableCell className="text-muted-foreground">
                <p className="whitespace-pre-wrap">
                  {pipeline?.description ?? "-"}
                </p>
              </TableCell>
              <TableCell>
                <p className="whitespace-pre-wrap text-xs">
                  {variantNames ?? "-"}
                </p>
              </TableCell>
              <TableCell className="text-xs">
                <div className="space-y-1">
                  <div>Input: {String(sourceValue ?? "-")}</div>
                  <div>
                    Models:{" "}
                    {modelNames.length > 0
                      ? modelNames.map((modelName, index) => (
                          <span
                            key={`${workload.id}-${modelName}-${index}`}
                            title={modelName}
                          >
                            {truncateModelName(modelName)}
                            {index < modelNames.length - 1 ? ", " : ""}
                          </span>
                        ))
                      : "-"}
                  </div>
                  <div>Tested stream counts: {uniqueStreams ?? "-"}</div>
                </div>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
};
