import { useParams } from "react-router";
import {
  useGetPipelineQuery,
  useRunPerformanceTestMutation,
  useStopPerformanceTestJobMutation,
} from "@/api/api.generated";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type Viewport,
} from "@xyflow/react";
import { useState } from "react";
import PipelineEditor from "@/features/pipeline-editor/PipelineEditor.tsx";
import FpsDisplay from "@/features/pipeline-editor/FpsDisplay.tsx";
import { toast } from "sonner";
import RunPerformanceTestButton from "@/features/pipeline-editor/RunPerformanceTestButton.tsx";
import StopPerformanceTestButton from "@/features/pipeline-editor/StopPerformanceTestButton.tsx";
import StatePreviewButton from "@/features/pipeline-editor/StatePreviewButton.tsx";
import ExportPipelineButton from "@/features/pipeline-editor/ExportPipelineButton.tsx";
import OpenPipelineButton from "@/features/pipeline-editor/OpenPipelineButton.tsx";
import ImportPipelineButton from "@/features/pipeline-editor/ImportPipelineButton.tsx";

type UrlParams = {
  id: string;
};

const Pipelines = () => {
  const { id } = useParams<UrlParams>();
  const [performanceTestJobId, setPerformanceTestJobId] = useState<
    string | null
  >(null);
  const [currentNodes, setCurrentNodes] = useState<ReactFlowNode[]>([]);
  const [currentEdges, setCurrentEdges] = useState<ReactFlowEdge[]>([]);
  const [currentViewport, setCurrentViewport] = useState<Viewport>({
    x: 0,
    y: 0,
    zoom: 1,
  });
  const [editorKey, setEditorKey] = useState(0);
  const [shouldFitView, setShouldFitView] = useState(false);

  const { data, isSuccess } = useGetPipelineQuery(
    {
      pipelineId: id ?? "",
    },
    {
      skip: !id,
    },
  );

  const [runPerformanceTest, { isLoading: isRunning }] =
    useRunPerformanceTestMutation();
  const [stopPerformanceTest, { isLoading: isStopping }] =
    useStopPerformanceTestJobMutation();

  const handleNodesChange = (nodes: ReactFlowNode[]) => {
    setCurrentNodes(nodes);
  };

  const handleEdgesChange = (edges: ReactFlowEdge[]) => {
    setCurrentEdges(edges);
  };

  const handleViewportChange = (viewport: Viewport) => {
    setCurrentViewport(viewport);
  };

  const handleRunPipeline = async () => {
    if (!id) return;

    try {
      const response = await runPerformanceTest({
        performanceTestSpec: {
          pipeline_performance_specs: [
            {
              id,
              streams: 20,
            },
          ],
        },
      }).unwrap();

      if (response && typeof response === "object" && "job_id" in response) {
        setPerformanceTestJobId(response.job_id as string);
      }

      toast.success("Pipeline run started", {
        description: new Date().toISOString(),
      });
    } catch (error) {
      toast.error("Failed to start pipeline", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
      console.error("Failed to start pipeline:", error);
    }
  };

  const handleStopPipeline = async () => {
    if (!performanceTestJobId) return;

    try {
      await stopPerformanceTest({
        jobId: performanceTestJobId,
      }).unwrap();

      setPerformanceTestJobId(null);

      toast.success("Pipeline stopped", {
        description: new Date().toISOString(),
      });
    } catch (error) {
      toast.error("Failed to stop pipeline", {
        description: error instanceof Error ? error.message : "Unknown error",
      });
      console.error("Failed to stop pipeline:", error);
    }
  };

  const handleImport = (
    nodes: ReactFlowNode[],
    edges: ReactFlowEdge[],
    viewport: Viewport,
    shouldFitView: boolean,
  ) => {
    setCurrentNodes(nodes);
    setCurrentEdges(edges);
    setCurrentViewport(viewport);
    setShouldFitView(shouldFitView);
    setEditorKey((prev) => prev + 1); // Force PipelineEditor to re-initialize
  };

  if (isSuccess && data) {
    return (
      <div className="w-full h-screen relative">
        <PipelineEditor
          key={editorKey}
          pipelineData={data}
          onNodesChange={handleNodesChange}
          onEdgesChange={handleEdgesChange}
          onViewportChange={handleViewportChange}
          initialNodes={currentNodes.length > 0 ? currentNodes : undefined}
          initialEdges={currentEdges.length > 0 ? currentEdges : undefined}
          initialViewport={
            currentNodes.length > 0 ? currentViewport : undefined
          }
          shouldFitView={shouldFitView}
        />

        <div className="absolute top-4 right-4 flex flex-row gap-2">
          <button
            className="bg-gray-600 text-white p-2 rounded-lg shadow-lg transition-colors disabled:opacity-50"
            title="Optimize Pipeline"
            disabled={true}
          >
            Optimize
          </button>
          <FpsDisplay />
        </div>

        <div className="absolute top-4 left-4 z-10 flex flex-col gap-2 items-end">
          <div className="flex gap-2">
            <OpenPipelineButton onImport={handleImport} />

            <ImportPipelineButton onImport={handleImport} />

            {performanceTestJobId ? (
              <StopPerformanceTestButton
                isStopping={isStopping}
                onStop={handleStopPipeline}
              />
            ) : (
              <RunPerformanceTestButton
                isRunning={isRunning}
                onRun={handleRunPipeline}
              />
            )}

            <ExportPipelineButton
              edges={currentEdges}
              nodes={currentNodes}
              viewport={currentViewport}
              pipelineName={data.name}
            />

            <StatePreviewButton
              edges={currentEdges}
              nodes={currentNodes}
              viewport={currentViewport}
            />
          </div>
        </div>
      </div>
    );
  }

  return <div>Loading pipeline: {id}</div>;
};

export default Pipelines;
