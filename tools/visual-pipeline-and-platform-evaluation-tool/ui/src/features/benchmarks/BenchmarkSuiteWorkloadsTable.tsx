import type { BenchmarkSuite, Pipeline } from "@/api/api.generated.ts";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { extractModelNamesFromNodes } from "@/features/models/modelNames.ts";
import { useMemo } from "react";

const THUMBNAIL_PLACEHOLDER = "/src/assets/thumbnail_placeholder.png";

type BenchmarkSuiteWorkloadsTableProps = {
  benchmark: BenchmarkSuite;
  pipelinesMap: Map<string, Pipeline>;
};

type WorkloadRow = {
  id: number;
  pipeline?: Pipeline;
  pipelineId: string;
  variantNames: string;
  sourceValue?: string;
  modelNames: string[];
  uniqueStreams: string;
};

const truncateModelName = (name: string) => {
  const parts = name.trim().split(/\s+/).filter(Boolean);

  if (parts.length <= 3) {
    return name;
  }

  return `${parts.slice(0, 3).join(" ")}...`;
};

export const BenchmarkSuiteWorkloadsTable = ({
  benchmark,
  pipelinesMap,
}: BenchmarkSuiteWorkloadsTableProps) => {
  const rows = useMemo<WorkloadRow[]>(
    () =>
      benchmark.workloads.map((workload) => {
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
        const advancedGraph = firstVariant?.pipeline_graph;
        const sourceNode = simpleGraph?.nodes.find(
          (node) => node.type === "source",
        );
        const sourceValue =
          sourceNode?.data && typeof sourceNode.data === "object"
            ? String((sourceNode.data as Record<string, unknown>).source ?? "")
            : undefined;

        return {
          id: workload.id,
          pipeline,
          pipelineId: workload.pipeline_id,
          variantNames,
          sourceValue,
          modelNames: extractModelNamesFromNodes(advancedGraph?.nodes),
          uniqueStreams: [
            ...new Set(workload.test_cases.map((tc) => tc.streams)),
          ]
            .sort((a, b) => a - b)
            .join(", "),
        };
      }),
    [benchmark.workloads, pipelinesMap],
  );

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
        {rows.map((row) => (
          <TableRow key={row.id}>
            <TableCell>
              <img
                src={row.pipeline?.thumbnail ?? THUMBNAIL_PLACEHOLDER}
                alt={row.pipeline?.name ?? row.pipelineId}
                className="w-32 h-16 object-cover"
              />
            </TableCell>
            <TableCell className="font-medium whitespace-nowrap">
              {row.pipeline?.name ?? row.pipelineId}
            </TableCell>
            <TableCell className="text-muted-foreground">
              <p className="whitespace-pre-wrap">
                {row.pipeline?.description ?? "-"}
              </p>
            </TableCell>
            <TableCell>
              <p className="whitespace-pre-wrap text-xs">
                {row.variantNames ?? "-"}
              </p>
            </TableCell>
            <TableCell className="text-xs">
              <div className="space-y-1">
                <div>Input: {String(row.sourceValue ?? "-")}</div>
                <div>
                  Models:{" "}
                  {row.modelNames.length > 0
                    ? row.modelNames.map((modelName, index) => (
                        <span
                          key={`${row.id}-${modelName}-${index}`}
                          title={modelName}
                        >
                          {truncateModelName(modelName)}
                          {index < row.modelNames.length - 1 ? ", " : ""}
                        </span>
                      ))
                    : "-"}
                </div>
                <div>Tested stream counts: {row.uniqueStreams ?? "-"}</div>
              </div>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
