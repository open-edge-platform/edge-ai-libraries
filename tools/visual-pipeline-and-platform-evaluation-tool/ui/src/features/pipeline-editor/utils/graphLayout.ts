import dagre from "dagre";
import {
  type Edge as ReactFlowEdge,
  type Node as ReactFlowNode,
  Position,
} from "@xyflow/react";
import {
  defaultNodeWidth,
  defaultNodeHeight,
  nodeWidths,
  nodeHeights,
} from "@/features/pipeline-editor/nodes";

export const LayoutDirection = {
  TopToBottom: "TB" as const,
  BottomToTop: "BT" as const,
  LeftToRight: "LR" as const,
  RightToLeft: "RL" as const,
} as const;

export type LayoutDirectionType =
  (typeof LayoutDirection)[keyof typeof LayoutDirection];

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const getNodeWidth = (nodeType: string): number =>
  nodeWidths[nodeType] ?? defaultNodeWidth;

const getNodeHeight = (nodeType: string): number =>
  nodeHeights[nodeType] ?? defaultNodeHeight;

export const createGraphLayout = (
  nodes: ReactFlowNode[],
  edges: ReactFlowEdge[],
  direction: LayoutDirectionType = LayoutDirection.LeftToRight,
) => {
  const isHorizontal = direction === "LR" || direction === "RL";
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    if (dagreGraph.hasNode(node.id)) {
      dagreGraph.removeNode(node.id);
    }
  });

  edges.forEach((edge) => {
    if (dagreGraph.hasEdge(edge.source, edge.target)) {
      dagreGraph.removeEdge(edge.source, edge.target);
    }
  });

  nodes.forEach((node) => {
    const currentNodeWidth = getNodeWidth(node.type || "default");
    const currentNodeHeight = getNodeHeight(node.type || "default");
    dagreGraph.setNode(node.id, {
      width: currentNodeWidth,
      height: currentNodeHeight,
    });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  return nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const currentNodeWidth = getNodeWidth(node.type ?? "default");
    const currentNodeHeight = getNodeHeight(node.type ?? "default");

    return {
      ...node,
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition.x - currentNodeWidth / 2,
        y: nodeWithPosition.y - currentNodeHeight / 2,
      },
    };
  });
};

export const getHandleLeftPosition = (nodeType: string): string => {
  const width = nodeWidths[nodeType] ?? defaultNodeWidth;
  const handleWidth = 12;
  const leftPosition = (width - handleWidth) / 2;
  return `${leftPosition}px`;
};
