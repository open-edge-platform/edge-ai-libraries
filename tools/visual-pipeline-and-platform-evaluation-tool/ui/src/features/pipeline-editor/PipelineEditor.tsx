import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  type NodeMouseHandler,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Viewport,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from "react";
import { defaultNodeWidth, nodeTypes } from "@/features/pipeline-editor/nodes";
import { type Pipeline } from "@/api/api.generated";
import {
  createGraphLayout,
  LayoutDirection,
} from "@/features/pipeline-editor/utils/graphLayout";
import { useTheme } from "next-themes";

export interface PipelineEditorHandle {
  updateNodeData: (
    nodeId: string,
    updatedData: Record<string, unknown>,
  ) => void;
}

interface PipelineEditorProps {
  pipelineData?: Pipeline;
  onNodesChange?: (nodes: ReactFlowNode[]) => void;
  onEdgesChange?: (edges: ReactFlowEdge[]) => void;
  onViewportChange?: (viewport: Viewport) => void;
  onNodeSelect?: (node: ReactFlowNode | null) => void;
  initialNodes?: ReactFlowNode[];
  initialEdges?: ReactFlowEdge[];
  initialViewport?: Viewport;
  shouldFitView?: boolean;
  useSimpleGraph?: boolean;
}

const PipelineEditorContent = forwardRef<
  PipelineEditorHandle,
  PipelineEditorProps
>(
  (
    {
      pipelineData,
      onNodesChange: onNodesChangeCallback,
      onEdgesChange: onEdgesChangeCallback,
      onViewportChange: onViewportChangeCallback,
      onNodeSelect,
      initialNodes,
      initialEdges,
      initialViewport,
      shouldFitView,
      useSimpleGraph,
    },
    ref,
  ) => {
    const [nodes, setNodes, onNodesChange] = useNodesState<ReactFlowNode>([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState<ReactFlowEdge>([]);
    const { getViewport, setViewport, fitView } = useReactFlow();
    const [hasInitialized, setHasInitialized] = useState(false);

    const onNodeClick: NodeMouseHandler = (event, node) => {
      event.stopPropagation();
      onNodeSelect?.(node);
    };

    const onPaneClick = () => {
      onNodeSelect?.(null);
    };

    const handleNodeDataUpdate = useCallback(
      (nodeId: string, updatedData: Record<string, unknown>) => {
        setNodes((currentNodes) =>
          currentNodes.map((node) =>
            node.id === nodeId ? { ...node, data: updatedData } : node,
          ),
        );
      },
      [setNodes],
    );

    const { theme } = useTheme();

    useImperativeHandle(ref, () => ({
      updateNodeData: handleNodeDataUpdate,
    }));

    useEffect(() => {
      onNodesChangeCallback?.(nodes);
    }, [nodes, onNodesChangeCallback]);

    useEffect(() => {
      onEdgesChangeCallback?.(edges);
    }, [edges, onEdgesChangeCallback]);

    useEffect(() => {
      setHasInitialized(false);
    }, [useSimpleGraph]);

    useEffect(() => {
      if (!hasInitialized) {
        if (initialNodes && initialEdges) {
          setNodes(initialNodes);
          setEdges(initialEdges);

          setTimeout(() => {
            if (shouldFitView) {
              fitView();
            } else if (initialViewport) {
              setViewport(initialViewport);
            }
          }, 0);
          setHasInitialized(true);
        } else if (
          pipelineData?.pipeline_graph ||
          pipelineData?.pipeline_graph_simple
        ) {
          const graphToUse =
            useSimpleGraph === true
              ? pipelineData.pipeline_graph_simple
              : pipelineData.pipeline_graph;
          const nodes = graphToUse?.nodes ?? [];
          const edges = graphToUse?.edges ?? [];

          const transformedNodes = nodes.map(
            (node) =>
              ({
                ...node,
                type: node.type,
              }) as ReactFlowNode,
          );

          const nodesWithPositions = createGraphLayout(
            transformedNodes,
            edges,
            LayoutDirection.TopToBottom,
          );

          setNodes(nodesWithPositions);
          setEdges(edges);

          setTimeout(() => {
            if (initialViewport) {
              setViewport(initialViewport);
            } else {
              const viewportX = window.innerWidth / 2 - defaultNodeWidth / 2;
              setViewport({ x: viewportX, y: 50, zoom: 1 });
            }
          }, 0);

          setHasInitialized(true);
        }
      }
    }, [
      pipelineData,
      initialNodes,
      initialEdges,
      initialViewport,
      shouldFitView,
      hasInitialized,
      setNodes,
      setEdges,
      setViewport,
      fitView,
      useSimpleGraph,
    ]);

    return (
      <>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          onMoveEnd={() => {
            const viewport = getViewport();
            onViewportChangeCallback?.(viewport);
          }}
          nodesDraggable={true}
          colorMode={theme === "dark" ? "dark" : "light"}
          className="h-full w-full"
          defaultViewport={{ x: 0, y: 50, zoom: 1 }}
        >
          <Controls />
          <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
        </ReactFlow>
      </>
    );
  },
);

const PipelineEditor = forwardRef<PipelineEditorHandle, PipelineEditorProps>(
  (props, ref) => (
    <ReactFlowProvider>
      <PipelineEditorContent {...props} ref={ref} />
    </ReactFlowProvider>
  ),
);

PipelineEditor.displayName = "PipelineEditor";
PipelineEditorContent.displayName = "PipelineEditorContent";

export default PipelineEditor;
