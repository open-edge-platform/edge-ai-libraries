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
import { useEffect, useState } from "react";
import { nodeTypes } from "@/features/pipeline-editor/nodes";
import NodeDataPanel from "@/features/pipeline-editor/NodeDataPanel.tsx";
import { type Pipeline } from "@/api/api.generated";
import {
  createGraphLayout,
  LayoutDirection,
} from "@/features/pipeline-editor/utils/graphLayout";

interface PipelineEditorProps {
  pipelineData?: Pipeline;
  onNodesChange?: (nodes: ReactFlowNode[]) => void;
  onEdgesChange?: (edges: ReactFlowEdge[]) => void;
  onViewportChange?: (viewport: Viewport) => void;
  initialNodes?: ReactFlowNode[];
  initialEdges?: ReactFlowEdge[];
  initialViewport?: Viewport;
  shouldFitView?: boolean;
}

const PipelineEditorContent = ({
  pipelineData,
  onNodesChange: onNodesChangeCallback,
  onEdgesChange: onEdgesChangeCallback,
  onViewportChange: onViewportChangeCallback,
  initialNodes,
  initialEdges,
  initialViewport,
  shouldFitView,
}: PipelineEditorProps) => {
  const [selectedNode, setSelectedNode] = useState<ReactFlowNode | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<ReactFlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<ReactFlowEdge>([]);
  const { getViewport, setViewport, fitView } = useReactFlow();
  const [hasInitialized, setHasInitialized] = useState(false);

  const onNodeClick: NodeMouseHandler = (event, node) => {
    event.stopPropagation();
    setSelectedNode(node);
  };

  const onPaneClick = () => {
    setSelectedNode(null);
  };

  const handleNodeDataUpdate = (
    nodeId: string,
    updatedData: Record<string, unknown>,
  ) => {
    setNodes((currentNodes) => {
      const updatedNodes = currentNodes.map((node) =>
        node.id === nodeId ? { ...node, data: updatedData } : node,
      );
      onNodesChangeCallback?.(updatedNodes);
      return updatedNodes;
    });
  };

  useEffect(() => {
    onNodesChangeCallback?.(nodes);
  }, [nodes, onNodesChangeCallback]);

  useEffect(() => {
    onEdgesChangeCallback?.(edges);
  }, [edges, onEdgesChangeCallback]);

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
      } else if (pipelineData?.pipeline_graph) {
        const nodes = pipelineData.pipeline_graph.nodes ?? [];
        const edges = pipelineData.pipeline_graph.edges ?? [];

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
          LayoutDirection.LeftToRight,
        );

        setNodes(nodesWithPositions);
        setEdges(edges);
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
        fitView
      >
        <Controls />
        <Background variant={BackgroundVariant.Dots} gap={12} size={1} />
      </ReactFlow>

      <NodeDataPanel
        selectedNode={selectedNode}
        onNodeDataUpdate={handleNodeDataUpdate}
      />
    </>
  );
};

const PipelineEditor = (props: PipelineEditorProps) => (
  <ReactFlowProvider>
    <PipelineEditorContent {...props} />
  </ReactFlowProvider>
);

export default PipelineEditor;
