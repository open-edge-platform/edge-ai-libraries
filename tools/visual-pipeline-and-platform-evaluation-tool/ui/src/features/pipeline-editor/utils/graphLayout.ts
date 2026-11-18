import dagre from "dagre";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  Position,
} from "@xyflow/react";
import {
  defaultNodeHeight,
  defaultNodeWidth,
  nodeWidths,
} from "@/features/pipeline-editor/nodes";

export const LayoutDirection = {
  TopToBottom: "TB" as const,
  BottomToTop: "BT" as const,
  LeftToRight: "LR" as const,
  RightToLeft: "RL" as const,
} as const;

export type LayoutDirectionType =
  (typeof LayoutDirection)[keyof typeof LayoutDirection];

const getDeclaredWidth = (nodeType: string): number =>
  nodeWidths[nodeType] ?? defaultNodeWidth;

export const createGraphLayout = (
  nodes: ReactFlowNode[],
  edges: ReactFlowEdge[],
  direction: LayoutDirectionType = LayoutDirection.TopToBottom,
  // Per-node width override. When provided, these widths are fed into dagre
  // and used to compute final positions instead of the declared values in
  // `nodeWidths`. Used by PipelineEditor to re-run the layout once React Flow
  // has measured the actual rendered node sizes so sibling spacing matches
  // what the user sees on screen.
  widthByNodeId?: ReadonlyMap<string, number>,
) => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));

  const isHorizontal = direction === "LR" || direction === "RL";
  dagreGraph.setGraph({ rankdir: direction });

  const widthFor = (node: ReactFlowNode): number =>
    widthByNodeId?.get(node.id) ?? getDeclaredWidth(node.type || "default");

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, {
      width: widthFor(node),
      height: defaultNodeHeight,
    });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const currentNodeWidth = widthFor(node);

    return {
      ...node,
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition.x - currentNodeWidth / 2,
        y: nodeWithPosition.y - defaultNodeHeight / 2,
      },
    };
  });
};
